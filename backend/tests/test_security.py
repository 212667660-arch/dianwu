import socket

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.errors import DesktopAuthRequiredError, ModelSettingsValidationError
from backend.main import app
from backend.routers import chat
from backend.services import security
from backend.services import orchestrator
from backend.services.rate_limit import rate_limiter
import backend.main as main_module


def test_production_protects_business_routes_with_desktop_token(monkeypatch) -> None:
    settings = Settings(app_env="production", desktop_token="desktop-test-token")
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/api/sessions/missing").status_code == 401
        assert client.get("/health/ready").status_code == 401
        response = client.get("/api/sessions/missing", headers={"X-A3-Desktop-Token": "desktop-test-token"})
        assert response.status_code == 404
        ready = client.get("/health/ready", headers={"X-A3-Desktop-Token": "desktop-test-token"})
        assert ready.status_code in {200, 503}


def test_production_without_token_fails_closed(monkeypatch) -> None:
    settings = Settings(app_env="production", desktop_token="")
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post("/api/chat", json={"session_id": "secured", "message": "学习一次函数"})
    assert response.status_code == 401
    assert response.json()["code"] == "DESKTOP_AUTH_REQUIRED"


def test_production_rejects_nonlocal_client_even_with_correct_token(monkeypatch) -> None:
    settings = Settings(app_env="production", desktop_token="desktop-test-token")
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    with TestClient(app, client=("192.168.1.8", 50000)) as client:
        response = client.get("/api/sessions/missing", headers={"X-A3-Desktop-Token": "desktop-test-token"})
    assert response.status_code == 401


def test_desktop_token_rejects_non_local_client() -> None:
    settings = Settings(app_env="production", desktop_token="desktop-test-token")
    assert security.is_local_client("192.168.1.8") is False
    with pytest.raises(DesktopAuthRequiredError):
        security.require_desktop_token("wrong-token", "192.168.1.8", settings)


def test_production_rejects_private_or_unresolved_model_gateway(monkeypatch) -> None:
    settings = Settings(app_env="production", desktop_token="desktop-test-token")
    with pytest.raises(ModelSettingsValidationError):
        security.validate_model_base_url("https://127.0.0.1", settings)

    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 443))])
    with pytest.raises(ModelSettingsValidationError):
        security.validate_model_base_url("https://localhost", settings)

    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 443))])
    assert security.validate_model_base_url("https://gateway.example", settings) == "https://gateway.example"


def test_development_allows_explicit_nonproduction_gateway_address() -> None:
    settings = Settings(app_env="development")
    assert security.validate_model_base_url("https://example.test/v1/", settings) == "https://example.test/v1"


def test_token_protected_high_cost_routes_are_rate_limited(monkeypatch) -> None:
    settings = Settings(app_env="production", desktop_token="desktop-test-token", api_rate_limit_per_minute=1)

    async def diagnosis_reply(*args, **kwargs):
        return orchestrator.ChatResult("继续说明你的学习情况。", "diagnosis", "DIAGNOSING")

    rate_limiter.clear()
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(chat, "handle_message", diagnosis_reply)
    try:
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            headers = {"X-A3-Desktop-Token": "desktop-test-token"}
            first = client.post("/api/chat", headers=headers, json={"session_id": "limited", "message": "学习一次函数"})
            second = client.post("/api/chat", headers=headers, json={"session_id": "limited", "message": "继续学习"})
        assert first.status_code == 200
        assert second.status_code == 429
        assert second.json()["code"] == "REQUEST_RATE_LIMITED"
        assert int(second.headers["Retry-After"]) >= 1
    finally:
        rate_limiter.clear()
