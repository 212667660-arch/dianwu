import asyncio
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import app
from backend.routers import model_settings as model_settings_router
from backend.models.schemas import ModelRuntimeSnapshotInput, ModelSettingsResponse, ModelSettingsUpdate
from backend.errors import ModelSettingsAccessError
from backend.errors import ModelCredentialStoreRequiredError
from backend.services import model_settings
from backend.services.model_runtime import model_runtime_router


def test_current_model_settings_masks_api_key(monkeypatch) -> None:
    class FakeSettings:
        resolved_provider = "openai"
        resolved_base_url = "https://example.test/v1"
        resolved_model_name = "custom-model"
        resolved_api_key = "sk-1234567890"
        is_model_configured = True
        anthropic_version = "2023-06-01"
        request_timeout_seconds = 30.0

    monkeypatch.setattr(model_settings, "get_settings", lambda: FakeSettings())
    response = model_settings.current_model_settings()
    assert response.api_key_configured is True
    assert response.api_key_hint == "sk-1...7890"
    assert "1234567890" not in response.model_dump_json()


def test_current_model_settings_prefers_explicit_environment_over_stale_runtime(monkeypatch) -> None:
    class ConfiguredEnvironmentSettings:
        resolved_provider = "anthropic"
        resolved_base_url = "https://environment.example.test/v1"
        resolved_model_name = "environment-model"
        resolved_api_key = "environment-secret-key"
        is_model_configured = True
        anthropic_version = "2023-06-01"
        request_timeout_seconds = 30.0

    monkeypatch.setattr(model_settings, "get_settings", lambda: ConfiguredEnvironmentSettings())
    monkeypatch.setattr(model_settings.model_runtime_router, "legacy_model_settings", lambda: ModelSettingsResponse(
        provider="openai",
        base_url="https://stale-runtime.example.test/v1",
        model_name="stale-runtime-model",
        api_key_configured=True,
        api_key_hint="configured",
        anthropic_version="2023-06-01",
        request_timeout_seconds=60,
    ))

    response = model_settings.current_model_settings()

    assert response.provider == "anthropic"
    assert response.base_url == "https://environment.example.test/v1"
    assert response.model_name == "environment-model"


def test_current_model_settings_uses_bootstrapped_runtime_after_cold_start(monkeypatch) -> None:
    class EmptyEnvironmentSettings:
        resolved_provider = "openai"
        resolved_base_url = "https://unused.example.test/v1"
        resolved_model_name = "unused-model"
        resolved_api_key = ""
        is_model_configured = False
        anthropic_version = "2023-06-01"
        request_timeout_seconds = 60.0

    monkeypatch.setattr(model_settings, "get_settings", lambda: EmptyEnvironmentSettings())
    asyncio.run(model_runtime_router.apply_snapshot(ModelRuntimeSnapshotInput.model_validate({
        "default_profile_id": "primary",
        "auto_failover": True,
        "fallback_profile_ids": [],
        "profiles": [{
            "id": "primary",
            "label": "Primary",
            "enabled": True,
            "provider": "openai",
            "base_url": "https://runtime.example.test/v1",
            "api_key": "runtime-secret-key",
            "anthropic_version": "2023-06-01",
            "request_timeout_seconds": 45,
            "default_model_id": "model-a",
            "models": [{
                "id": "model-a",
                "provider_model_name": "runtime-model",
                "label": "Runtime Model",
                "max_output_tokens": 4096,
                "supported_reasoning_efforts": ["auto", "off"],
                "reasoning_adapter": "none",
            }],
        }],
    })))
    try:
        response = model_settings.current_model_settings()
    finally:
        asyncio.run(model_runtime_router.apply_snapshot(ModelRuntimeSnapshotInput()))

    assert response.api_key_configured is True
    assert response.api_key_hint == "configured"
    assert response.base_url == "https://runtime.example.test/v1"
    assert response.model_name == "runtime-model"
    assert "runtime-secret-key" not in response.model_dump_json()


def test_save_model_settings_writes_generic_variables(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("CORS_ORIGINS=http://localhost:5173\nDESKTOP_TOKEN=local-token\n", encoding="utf-8")
    expected = ModelSettingsResponse(
        provider="anthropic",
        base_url="https://example.test/anthropic",
        model_name="custom-model",
        api_key_configured=True,
        api_key_hint="test...key",
        anthropic_version="2023-06-01",
        request_timeout_seconds=45.0,
    )
    monkeypatch.setattr(model_settings, "_ENV_PATH", env_path)
    monkeypatch.setattr(model_settings, "current_model_settings", lambda: expected)
    cleared = []
    monkeypatch.setattr(model_settings.get_settings, "cache_clear", lambda: cleared.append(True))
    result = model_settings.save_model_settings(ModelSettingsUpdate(
        provider="anthropic",
        api_key="test-secret-key",
        base_url="https://example.test/anthropic/",
        model_name="custom-model",
        request_timeout_seconds=45,
    ))
    content = env_path.read_text(encoding="utf-8")
    assert "MODEL_PROVIDER=anthropic" in content
    assert "MODEL_BASE_URL=https://example.test/anthropic" in content
    assert "MODEL_API_KEY=test-secret-key" in content
    assert "CORS_ORIGINS=http://localhost:5173" in content
    assert "DESKTOP_TOKEN=local-token" in content
    assert cleared == [True]
    assert result == expected


def test_model_settings_route_never_returns_raw_key(monkeypatch) -> None:
    expected = ModelSettingsResponse(
        provider="openai",
        base_url="https://example.test/v1",
        model_name="custom-model",
        api_key_configured=True,
        api_key_hint="sk-a...cdef",
        anthropic_version="2023-06-01",
        request_timeout_seconds=60.0,
    )
    monkeypatch.setattr(model_settings_router, "current_model_settings", lambda: expected)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.get("/api/settings/model")
    assert response.status_code == 200
    assert response.json()["api_key_hint"] == "sk-a...cdef"
    assert "api_key" not in response.json()



def test_model_settings_rejects_non_local_client_without_token(monkeypatch) -> None:
    class FakeSettings:
        desktop_token = ""

    monkeypatch.setattr(model_settings, "get_settings", lambda: FakeSettings())
    with pytest.raises(ModelSettingsAccessError):
        model_settings.verify_desktop_token(None, "192.168.1.20")


def test_model_settings_accepts_matching_desktop_token(monkeypatch) -> None:
    class FakeSettings:
        desktop_token = "local-secret"

    monkeypatch.setattr(model_settings, "get_settings", lambda: FakeSettings())
    model_settings.verify_desktop_token("local-secret", "192.168.1.20")


def test_production_model_settings_never_write_plaintext_key(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("EXISTING=value\n", encoding="utf-8")
    production = Settings(app_env="production", desktop_token="desktop-token")
    monkeypatch.setattr(model_settings, "_ENV_PATH", env_path)
    monkeypatch.setattr(model_settings, "get_settings", lambda: production)
    with pytest.raises(ModelCredentialStoreRequiredError):
        model_settings.save_model_settings(ModelSettingsUpdate(
            provider="openai",
            api_key="test-secret-key",
            base_url="https://8.8.8.8",
            model_name="custom-model",
        ))
    assert env_path.read_text(encoding="utf-8") == "EXISTING=value\n"
