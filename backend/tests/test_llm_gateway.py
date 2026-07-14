import asyncio

import pytest
import httpx

from backend.errors import ModelAccessError, ModelAuthenticationError, ModelNotFoundError
from openai import NotFoundError, PermissionDeniedError

from backend.config import Settings
from backend.errors import ConfigurationError
from backend.services.llm_service import ModelGateway


def test_openai_compatible_settings_prefer_generic_variables() -> None:
    app_settings = Settings(
        model_provider="openai",
        model_api_key="test-key",
        model_base_url="https://example.test/v1",
        model_name="custom-model",
        openai_api_key="legacy-key",
    )
    assert app_settings.is_model_configured is True
    assert app_settings.resolved_provider == "openai"
    assert app_settings.resolved_api_key == "test-key"
    assert app_settings.resolved_base_url == "https://example.test/v1"
    assert app_settings.resolved_model_name == "custom-model"


def test_anthropic_payload_separates_system_message() -> None:
    gateway = ModelGateway(Settings(
        model_provider="anthropic",
        model_api_key="test-key",
        model_base_url="https://example.test/anthropic",
        model_name="custom-anthropic-model",
    ))
    payload = gateway._anthropic_payload([
        {"role": "system", "content": "system instruction"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ], 0.3)
    assert payload["model"] == "custom-anthropic-model"
    assert payload["system"] == "system instruction"
    assert payload["messages"] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_anthropic_payload_requires_conversation() -> None:
    gateway = ModelGateway(Settings(
        model_provider="anthropic",
        model_api_key="test-key",
        model_base_url="https://example.test/anthropic",
        model_name="custom-anthropic-model",
    ))
    with pytest.raises(Exception) as exc_info:
        gateway._anthropic_payload([{"role": "system", "content": "only system"}], 0.2)
    assert getattr(exc_info.value, "code", None) == "MODEL_BAD_RESPONSE"


def test_unsupported_provider_is_not_ready() -> None:
    app_settings = Settings(
        model_provider="unknown",
        model_api_key="test-key",
        model_base_url="https://example.test",
        model_name="custom-model",
    )
    assert app_settings.is_model_configured is False
    with pytest.raises(ConfigurationError):
        ModelGateway(app_settings)._validate_settings()


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, ModelAuthenticationError),
        (403, ModelAccessError),
        (404, ModelNotFoundError),
    ],
)
def test_anthropic_error_statuses_have_distinct_safe_codes(status_code, expected_error) -> None:
    response = httpx.Response(status_code, request=httpx.Request("POST", "https://example.test/v1/messages"))
    with pytest.raises(expected_error):
        ModelGateway._raise_anthropic_response(response)


def test_gateway_close_releases_openai_client() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    gateway = ModelGateway(Settings(
        model_provider="openai",
        model_api_key="test-key",
        model_base_url="https://example.test/v1",
        model_name="custom-model",
    ))
    client = FakeClient()
    gateway._openai_client = client
    gateway._client_signature = ("test-key", "https://example.test/v1", 60.0)
    asyncio.run(gateway.aclose())
    assert client.closed is True
    assert gateway._openai_client is None
    assert gateway._client_signature is None


def test_openai_permission_and_not_found_errors_are_safe(monkeypatch) -> None:
    response = httpx.Response(403, request=httpx.Request("POST", "https://example.test/v1/chat/completions"))
    gateway = ModelGateway(Settings(
        model_provider="openai",
        model_api_key="test-key",
        model_base_url="https://example.test/v1",
        model_name="custom-model",
    ))

    class FakeCompletions:
        async def create(self, *args, **kwargs):
            raise PermissionDeniedError("denied", response=response, body=None)

    class FakeClient:
        class Chat:
            completions = FakeCompletions()

        chat = Chat()

    monkeypatch.setattr(gateway, "_openai_client_or_raise", lambda: FakeClient())
    with pytest.raises(ModelAccessError):
        asyncio.run(gateway.complete([{"role": "user", "content": "hello"}]))

    class MissingCompletions:
        async def create(self, *args, **kwargs):
            raise NotFoundError("missing", response=response, body=None)

    class MissingClient:
        class Chat:
            completions = MissingCompletions()

        chat = Chat()

    monkeypatch.setattr(gateway, "_openai_client_or_raise", lambda: MissingClient())
    with pytest.raises(ModelNotFoundError):
        asyncio.run(gateway.complete([{"role": "user", "content": "hello"}]))


def test_openai_stream_permission_and_not_found_errors_are_safe(monkeypatch) -> None:
    response = httpx.Response(403, request=httpx.Request("POST", "https://example.test/v1/chat/completions"))
    gateway = ModelGateway(Settings(
        model_provider="openai",
        model_api_key="test-key",
        model_base_url="https://example.test/v1",
        model_name="custom-model",
    ))

    class DeniedCompletions:
        async def create(self, *args, **kwargs):
            raise PermissionDeniedError("denied", response=response, body=None)

    class DeniedClient:
        class Chat:
            completions = DeniedCompletions()

        chat = Chat()

    async def first_delta() -> str:
        async for delta in gateway.stream([{"role": "user", "content": "hello"}]):
            return delta
        return ""

    monkeypatch.setattr(gateway, "_openai_client_or_raise", lambda: DeniedClient())
    with pytest.raises(ModelAccessError):
        asyncio.run(first_delta())

    class MissingCompletions:
        async def create(self, *args, **kwargs):
            raise NotFoundError("missing", response=response, body=None)

    class MissingClient:
        class Chat:
            completions = MissingCompletions()

        chat = Chat()

    monkeypatch.setattr(gateway, "_openai_client_or_raise", lambda: MissingClient())
    with pytest.raises(ModelNotFoundError):
        asyncio.run(first_delta())
