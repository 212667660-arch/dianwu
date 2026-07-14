from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
from openai import AsyncOpenAI
from openai import APIConnectionError, APITimeoutError, AuthenticationError, BadRequestError, InternalServerError, NotFoundError, PermissionDeniedError, RateLimitError

from backend.config import Settings, get_settings
from backend.errors import ConfigurationError, ModelAccessError, ModelAuthenticationError, ModelBadResponseError, ModelNotFoundError, ModelRateLimitError, ModelTimeoutError, ModelUnavailableError
from backend.services.security import validate_model_base_url


class ModelGateway:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self._app_settings = app_settings
        self._openai_client: AsyncOpenAI | None = None
        self._client_signature: tuple[str, str, float] | None = None

    @property
    def settings(self) -> Settings:
        return self._app_settings or get_settings()

    async def aclose(self) -> None:
        if self._openai_client is not None:
            await self._openai_client.close()
            self._openai_client = None
            self._client_signature = None

    def _validate_settings(self) -> None:
        if not self.settings.is_model_configured:
            raise ConfigurationError()
        validate_model_base_url(self.settings.resolved_base_url, self.settings)

    def _openai_client_or_raise(self) -> AsyncOpenAI:
        self._validate_settings()
        signature = (self.settings.resolved_api_key, self.settings.resolved_base_url, self.settings.request_timeout_seconds)
        if self._openai_client is None or self._client_signature != signature:
            self._openai_client = AsyncOpenAI(
                api_key=self.settings.resolved_api_key,
                base_url=self.settings.resolved_base_url,
                timeout=self.settings.request_timeout_seconds,
            )
            self._client_signature = signature
        return self._openai_client

    def _anthropic_url(self) -> str:
        return f"{self.settings.resolved_base_url.rstrip('/')}/v1/messages"

    def _anthropic_payload(self, messages: list[dict[str, str]], temperature: float) -> dict[str, object]:
        system_parts = [message["content"] for message in messages if message.get("role") == "system"]
        conversation = [
            {"role": message["role"], "content": message["content"]}
            for message in messages
            if message.get("role") in {"user", "assistant"}
        ]
        if not conversation:
            raise ModelBadResponseError("模型请求缺少用户消息。")
        payload: dict[str, object] = {
            "model": self.settings.resolved_model_name,
            "max_tokens": 2048,
            "temperature": temperature,
            "messages": conversation,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        return payload

    def _anthropic_headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.settings.resolved_api_key,
            "anthropic-version": self.settings.anthropic_version,
            "content-type": "application/json",
        }

    @staticmethod
    def _anthropic_text(payload: dict[str, object]) -> str:
        content = payload.get("content", [])
        if not isinstance(content, list):
            return ""
        return "".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ).strip()

    @staticmethod
    def _raise_anthropic_response(response: httpx.Response) -> None:
        if response.status_code == 401:
            raise ModelAuthenticationError()
        if response.status_code == 403:
            raise ModelAccessError()
        if response.status_code == 404:
            raise ModelNotFoundError()
        if response.status_code == 429:
            raise ModelRateLimitError()
        if response.status_code == 408 or response.status_code == 504:
            raise ModelTimeoutError()
        if response.status_code >= 500:
            raise ModelUnavailableError()
        if response.status_code >= 400:
            raise ModelBadResponseError("模型请求参数无效。")

    async def complete(self, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        for attempt in range(2):
            try:
                if self.settings.resolved_provider == "anthropic":
                    return await self._complete_anthropic(messages, temperature)
                if self.settings.resolved_provider == "openai":
                    return await self._complete_openai(messages, temperature)
                raise ConfigurationError("MODEL_PROVIDER 仅支持 openai 或 anthropic。")
            except (ConfigurationError, ModelBadResponseError, ModelAuthenticationError, ModelAccessError, ModelNotFoundError):
                raise
            except ModelRateLimitError:
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                raise
            except ModelTimeoutError:
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                raise
            except ModelUnavailableError:
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                raise

    async def _complete_openai(self, messages: list[dict[str, str]], temperature: float) -> str:
        try:
            response = await self._openai_client_or_raise().chat.completions.create(
                model=self.settings.resolved_model_name,
                messages=messages,
                temperature=temperature,
            )
            content = response.choices[0].message.content or ""
            if not content.strip():
                raise ModelBadResponseError("模型未返回有效文本。")
            return content.strip()
        except AuthenticationError as exc:
            raise ModelAuthenticationError() from exc
        except PermissionDeniedError as exc:
            raise ModelAccessError() from exc
        except NotFoundError as exc:
            raise ModelNotFoundError() from exc
        except RateLimitError as exc:
            raise ModelRateLimitError() from exc
        except (APITimeoutError, TimeoutError) as exc:
            raise ModelTimeoutError() from exc
        except BadRequestError as exc:
            raise ModelBadResponseError("模型请求参数无效。", "MODEL_REQUEST_INVALID") from exc
        except (APIConnectionError, InternalServerError) as exc:
            raise ModelUnavailableError() from exc

    async def _complete_anthropic(self, messages: list[dict[str, str]], temperature: float) -> str:
        self._validate_settings()
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                response = await client.post(self._anthropic_url(), headers=self._anthropic_headers(), json=self._anthropic_payload(messages, temperature))
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError() from exc
        except httpx.HTTPError as exc:
            raise ModelUnavailableError() from exc
        self._raise_anthropic_response(response)
        try:
            content = self._anthropic_text(response.json())
        except ValueError as exc:
            raise ModelBadResponseError("模型返回不是有效 JSON。") from exc
        if not content:
            raise ModelBadResponseError("模型未返回有效文本。")
        return content

    async def stream(self, messages: list[dict[str, str]], temperature: float = 0.2) -> AsyncIterator[str]:
        if self.settings.resolved_provider == "anthropic":
            async for delta in self._stream_anthropic(messages, temperature):
                yield delta
            return
        if self.settings.resolved_provider != "openai":
            raise ConfigurationError("MODEL_PROVIDER 仅支持 openai 或 anthropic。")
        try:
            stream = await self._openai_client_or_raise().chat.completions.create(
                model=self.settings.resolved_model_name,
                messages=messages,
                temperature=temperature,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        yield content
        except AuthenticationError as exc:
            raise ModelAuthenticationError() from exc
        except PermissionDeniedError as exc:
            raise ModelAccessError() from exc
        except NotFoundError as exc:
            raise ModelNotFoundError() from exc
        except RateLimitError as exc:
            raise ModelRateLimitError() from exc
        except (APITimeoutError, TimeoutError) as exc:
            raise ModelTimeoutError() from exc
        except (APIConnectionError, InternalServerError) as exc:
            raise ModelUnavailableError() from exc
        except BadRequestError as exc:
            raise ModelBadResponseError("模型请求参数无效。") from exc

    async def _stream_anthropic(self, messages: list[dict[str, str]], temperature: float) -> AsyncIterator[str]:
        self._validate_settings()
        payload = self._anthropic_payload(messages, temperature)
        payload["stream"] = True
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                async with client.stream("POST", self._anthropic_url(), headers=self._anthropic_headers(), json=payload) as response:
                    self._raise_anthropic_response(response)
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        try:
                            event = json.loads(line[6:])
                        except json.JSONDecodeError as exc:
                            raise ModelBadResponseError("模型流事件格式无效。") from exc
                        if event.get("type") == "content_block_delta":
                            text = event.get("delta", {}).get("text", "")
                            if text:
                                yield str(text)
                        elif event.get("type") == "error":
                            raise ModelBadResponseError("模型流返回错误。")
        except (ModelAuthenticationError, ModelAccessError, ModelNotFoundError, ModelRateLimitError, ModelTimeoutError, ModelUnavailableError, ModelBadResponseError):
            raise
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError() from exc
        except httpx.HTTPError as exc:
            raise ModelUnavailableError() from exc


def user_block(text: str) -> str:
    return f"【用户数据开始】\n{text}\n【用户数据结束】"
