from fastapi.testclient import TestClient

from backend.config import Settings
from backend.errors import ConfigurationError
from backend.main import app
from backend.routers import chat
from backend.tests.error_assertions import assert_error


def test_app_error_uses_structured_non_200_response(monkeypatch) -> None:
    async def fail(*args, **kwargs):
        raise ConfigurationError()

    monkeypatch.setattr(chat, "handle_message", fail)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "测试", "session_id": "error_case"})
    assert_error(response, 503, "CONFIGURATION_ERROR")


def test_unknown_session_history_returns_404() -> None:
    with TestClient(app) as client:
        response = client.get("/api/sessions/no_such_session")
    assert_error(response, 404, "SESSION_NOT_FOUND")


def test_unknown_generation_uses_generation_not_found_code(monkeypatch) -> None:
    monkeypatch.setattr(chat, "cancel_generation", lambda *_args: False)
    with TestClient(app) as client:
        response = client.delete("/api/generations/missing?session_id=student_01")
    assert_error(response, 404, "GENERATION_NOT_FOUND")


def test_request_validation_uses_safe_envelope() -> None:
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "", "session_id": "bad/id"})
    assert_error(response, 422, "REQUEST_VALIDATION_ERROR")


def test_not_ready_health_uses_safe_envelope(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.main.get_settings",
        lambda: Settings(model_api_key="", openai_api_key="", hy_api_key=""),
    )
    with TestClient(app) as client:
        response = client.get("/health/ready", headers={"X-Request-ID": "trace-ready"})
    assert_error(response, 503, "MODEL_NOT_READY")
    assert response.json()["request_id"] == "trace-ready"


def test_unexpected_failure_does_not_expose_exception_text(monkeypatch) -> None:
    async def fail(*_args, **_kwargs):
        raise RuntimeError("private database path and token")

    monkeypatch.setattr(chat, "handle_message", fail)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/chat", json={"message": "测试", "session_id": "error_case"})
    assert_error(response, 500, "BACKEND_UNEXPECTED_ERROR", retryable=True)
    assert "private database" not in response.text


def test_unknown_route_and_method_use_safe_framework_envelopes() -> None:
    with TestClient(app) as client:
        missing = client.get("/api/does-not-exist")
        method = client.put("/health/live")
    assert_error(missing, 404, "HTTP_NOT_FOUND")
    assert_error(method, 405, "HTTP_METHOD_NOT_ALLOWED")


def test_disallowed_cors_preflight_uses_safe_error_envelope() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/health/live",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "PATCH",
                "X-Request-ID": "cors-preflight",
            },
        )
    assert_error(response, 400, "HTTP_REQUEST_ERROR")
    assert response.json()["request_id"] == "cors-preflight"
