import asyncio

import pytest
import httpx

from backend.errors import ModelAccessError, ModelAuthenticationError, ModelBadResponseError, ModelNotFoundError
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


def test_model_http_client_ignores_system_proxy() -> None:
    gateway = ModelGateway(Settings(
        model_provider="openai",
        model_api_key="test-key",
        model_base_url="https://example.test/v1",
        model_name="custom-model",
    ))

    client = gateway._new_http_client()
    try:
        assert client._trust_env is False
    finally:
        asyncio.run(client.aclose())


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


def test_openai_payload_uses_selected_model_and_reasoning_without_mutating_messages() -> None:
    gateway = ModelGateway(Settings(
        model_provider="openai",
        model_api_key="test-key",
        model_base_url="https://example.test/v1",
        model_name="default-model",
    ))
    messages = [{"role": "user", "content": "hello"}]

    payload = gateway._openai_payload(
        messages,
        0.2,
        "reasoning-model",
        {"reasoning_effort": "high"},
    )

    assert payload == {
        "model": "reasoning-model",
        "messages": [{"role": "user", "content": "hello"}],
        "reasoning_effort": "high",
    }
    assert messages == [{"role": "user", "content": "hello"}]


def test_anthropic_thinking_payload_omits_temperature_and_expands_token_budget() -> None:
    gateway = ModelGateway(Settings(
        model_provider="anthropic",
        model_api_key="test-key",
        model_base_url="https://example.test/anthropic",
        model_name="default-model",
    ))
    payload = gateway._anthropic_payload(
        [{"role": "user", "content": "hello"}],
        0.3,
        "thinking-model",
        {"thinking": {"type": "enabled", "budget_tokens": 8192}},
        4096,
    )

    assert payload["model"] == "thinking-model"
    assert payload["thinking"] == {"type": "enabled", "budget_tokens": 8192}
    assert payload["max_tokens"] == 10240
    assert "temperature" not in payload


def test_plain_payloads_keep_temperature_and_reject_arbitrary_reasoning_fields() -> None:
    gateway = ModelGateway(Settings(
        model_provider="openai",
        model_api_key="test-key",
        model_base_url="https://example.test/v1",
        model_name="default-model",
    ))
    payload = gateway._openai_payload(
        [{"role": "user", "content": "hello"}],
        0.4,
        "plain-model",
        {},
    )
    assert payload["temperature"] == 0.4
    with pytest.raises(ModelBadResponseError):
        gateway._openai_payload(
            [{"role": "user", "content": "hello"}],
            0.4,
            "plain-model",
            {"temperature": 2},
        )


def test_openai_client_reuses_signature_disables_sdk_retries_and_resets_on_close(monkeypatch) -> None:
    created = []

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.closed = False
            created.append(self)

        async def close(self) -> None:
            self.closed = True

    gateway = ModelGateway(Settings(
        model_provider="openai",
        model_api_key="test-secret-key",
        model_base_url="https://example.test/v1",
        model_name="default-model",
        request_timeout_seconds=30,
    ))
    monkeypatch.setattr("backend.services.llm_service.AsyncOpenAI", FakeClient)
    monkeypatch.setattr(gateway, "_validate_settings", lambda: None)
    monkeypatch.setattr(gateway, "_new_http_client", lambda: object())

    first = gateway._openai_client_or_raise()
    second = gateway._openai_client_or_raise()

    assert first is second
    assert created[0].kwargs["max_retries"] == 0
    assert "test-secret-key" not in repr(created[0].kwargs.keys())
    asyncio.run(gateway.aclose())
    assert created[0].closed is True
    assert gateway._client_signature is None
