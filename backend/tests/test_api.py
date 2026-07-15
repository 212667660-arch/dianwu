from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import chat
from backend.tests.error_assertions import assert_error


def test_live_health_check() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}


def test_browser_test_console_is_available() -> None:
    with TestClient(app) as client:
        response = client.get("/test")
    assert response.status_code == 200
    assert "A3 backend test console" in response.text


def test_trailing_slash_redirect_is_not_rewritten_as_error() -> None:
    with TestClient(app) as client:
        response = client.get("/test/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers.get("content-type") != "application/json"
    assert response.headers["location"].endswith("/test")


def test_chat_rejects_empty_message() -> None:
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "   ", "session_id": "student_01"})
    assert_error(response, 422, "REQUEST_VALIDATION_ERROR")


def test_chat_rejects_unsafe_session_id() -> None:
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "你好", "session_id": "../unsafe"})
    assert_error(response, 422, "REQUEST_VALIDATION_ERROR")


def test_generation_cancel_requires_its_session_id(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def cancel(generation_id: str, session_id: str) -> bool:
        captured["generation_id"] = generation_id
        captured["session_id"] = session_id
        return True

    monkeypatch.setattr(chat, "cancel_generation", cancel)
    with TestClient(app) as client:
        missing = client.delete("/api/generations/generation-001")
        response = client.delete("/api/generations/generation-001?session_id=student_01")
    assert_error(missing, 422, "REQUEST_VALIDATION_ERROR")
    assert response.status_code == 200
    assert captured == {"generation_id": "generation-001", "session_id": "student_01"}



def test_model_settings_put_is_allowed_by_cors() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/settings/model",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "PUT",
            },
        )
    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]
