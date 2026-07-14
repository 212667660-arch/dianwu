from fastapi.testclient import TestClient

from backend.errors import ConfigurationError
from backend.main import app
from backend.routers import chat


def test_app_error_uses_structured_non_200_response(monkeypatch) -> None:
    async def fail(*args, **kwargs):
        raise ConfigurationError()

    monkeypatch.setattr(chat, "handle_message", fail)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "测试", "session_id": "error_case"})
    assert response.status_code == 503
    assert response.json()["code"] == "CONFIGURATION_ERROR"
    assert response.json()["retryable"] is False


def test_unknown_session_history_returns_404() -> None:
    with TestClient(app) as client:
        response = client.get("/api/sessions/no_such_session")
    assert response.status_code == 404
