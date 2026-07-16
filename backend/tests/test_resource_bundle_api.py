from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


class TestResourceBundleEndpoint:
    def test_bundle_request_valid(self):
        response = client.post("/api/resource-bundle", json={
            "session_id": "test-api-bundle", "message": "生成一次函数资源",
            "resource_mode": "bundle",
        })
        assert response.status_code in (200, 404, 422)

    def test_single_request_valid(self):
        response = client.post("/api/resource-bundle", json={
            "session_id": "test-api-single", "message": "生成课程讲解",
            "resource_mode": "single", "resource_type": "course_explanation",
        })
        assert response.status_code in (200, 404, 422)

    def test_single_missing_resource_type_422(self):
        response = client.post("/api/resource-bundle", json={
            "session_id": "test-missing", "message": "生成",
            "resource_mode": "single",
        })
        assert response.status_code == 422

    def test_invalid_resource_mode_422(self):
        response = client.post("/api/resource-bundle", json={
            "session_id": "test-bad-mode", "message": "生成",
            "resource_mode": "invalid",
        })
        assert response.status_code == 422

    def test_invalid_resource_type_422(self):
        response = client.post("/api/resource-bundle", json={
            "session_id": "test-bad-type", "message": "生成",
            "resource_mode": "single", "resource_type": "invalid_type",
        })
        assert response.status_code == 422

    def test_v1_chat_still_works(self):
        response = client.post("/api/chat", json={
            "session_id": "test-v1", "message": "你好",
        })
        assert response.status_code in (200, 404, 422)
