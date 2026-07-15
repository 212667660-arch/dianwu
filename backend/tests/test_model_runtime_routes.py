from __future__ import annotations

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import app
import backend.main as main_module


EMPTY_SNAPSHOT = {
    "default_profile_id": None,
    "auto_failover": True,
    "fallback_profile_ids": [],
    "profiles": [],
}

VALID_SNAPSHOT = {
    "default_profile_id": "primary",
    "auto_failover": True,
    "fallback_profile_ids": [],
    "profiles": [{
        "id": "primary",
        "label": "主服务",
        "enabled": True,
        "provider": "openai",
        "base_url": "https://example.test/v1",
        "api_key": "test-secret-key",
        "anthropic_version": "2023-06-01",
        "request_timeout_seconds": 60,
        "default_model_id": "model-a",
        "models": [{
            "id": "model-a",
            "provider_model_name": "model-a-provider",
            "label": "模型 A",
            "max_output_tokens": 4096,
            "supported_reasoning_efforts": ["auto", "off", "low", "medium"],
            "reasoning_adapter": "openai_reasoning_effort",
        }],
    }],
}


def test_internal_runtime_requires_strict_token_and_loopback(monkeypatch) -> None:
    settings = Settings(app_env="production", desktop_token="desktop-test-token")
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        missing = client.get("/internal/model-runtime/status")
        wrong = client.get(
            "/internal/model-runtime/status",
            headers={"X-A3-Desktop-Token": "wrong"},
        )
    with TestClient(app, client=("192.168.1.8", 50000)) as remote:
        nonlocal_response = remote.get(
            "/internal/model-runtime/status",
            headers={"X-A3-Desktop-Token": "desktop-test-token"},
        )
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert nonlocal_response.status_code == 401


def test_bootstrap_controls_ready_and_never_returns_secret(monkeypatch) -> None:
    settings = Settings(app_env="production", desktop_token="desktop-test-token")
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    headers = {"X-A3-Desktop-Token": "desktop-test-token"}
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        empty = client.post("/internal/model-runtime/bootstrap", headers=headers, json=EMPTY_SNAPSHOT)
        not_ready = client.get("/health/ready", headers=headers)
        active = client.post("/internal/model-runtime/bootstrap", headers=headers, json=VALID_SNAPSHOT)
        ready = client.get("/health/ready", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["ready"] is False
    assert not_ready.status_code == 503
    assert active.status_code == 200
    assert active.json()["ready"] is True
    assert ready.status_code == 200
    assert "test-secret-key" not in active.text


def test_internal_runtime_rejects_extra_fields_and_large_body(monkeypatch) -> None:
    settings = Settings(app_env="production", desktop_token="desktop-test-token")
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    headers = {"X-A3-Desktop-Token": "desktop-test-token"}
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        extra = client.post(
            "/internal/model-runtime/bootstrap",
            headers=headers,
            json={**EMPTY_SNAPSHOT, "extra": True},
        )
        oversized = client.post(
            "/internal/model-runtime/bootstrap",
            headers={**headers, "Content-Type": "application/json"},
            content=b"{" + b" " * (128 * 1024) + b"}",
        )
    assert extra.status_code == 422
    assert oversized.status_code == 413
