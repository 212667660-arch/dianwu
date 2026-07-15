def assert_error(response, status: int, code: str, retryable: bool = False) -> None:
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert body["retryable"] is retryable
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["request_id"], str) and body["request_id"]
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert "detail" not in body
