from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.database import init_db
from backend.main import app
from backend.protocols.v2.models import (
    ArtifactStatus,
    ArtifactType,
    BundleStatus,
    ResourceArtifact,
    ResourceBundle,
)
from backend.routers import chat, resource
from backend.services.orchestrator import ChatResult

client = TestClient(app)


@pytest.fixture(autouse=True)
def _initialize_database() -> None:
    init_db()


def _completed_bundle(bundle_id: str = "bundle-shared-service") -> ResourceBundle:
    artifact = ResourceArtifact(
        artifact_id=f"{bundle_id}-course",
        type=ArtifactType.COURSE_EXPLANATION,
        title="课程讲解",
        status=ArtifactStatus.SUCCEEDED,
        body="讲解内容",
        quality_score=90,
    )
    return ResourceBundle(
        bundle_id=bundle_id,
        topic="一次函数",
        profile_version=1,
        learning_state_version="1",
        mode="bundle",
        status=BundleStatus.COMPLETED,
        requested_types=[ArtifactType.COURSE_EXPLANATION],
        artifacts=[artifact],
        aggregate_quality=90,
        created_at="2026-07-17T00:00:00Z",
    )


class TestResourceBundleEndpoint:
    def test_bundle_endpoint_delegates_to_shared_service(self, monkeypatch):
        calls = []

        class FakeService:
            async def generate(self, db, session_id, message, selection, **kwargs):
                calls.append((session_id, message, selection, kwargs))
                return _completed_bundle()

        monkeypatch.setattr(resource, "resource_bundle_service", FakeService(), raising=False)
        response = client.post("/api/resource-bundle", json={
            "session_id": "shared-service-api",
            "message": "生成一次函数资源",
            "resource_mode": "bundle",
        })

        assert response.status_code == 200
        assert response.json()["bundle_id"] == "bundle-shared-service"
        assert len(calls) == 1
        assert calls[0][0:2] == ("shared-service-api", "生成一次函数资源")
        assert calls[0][2].mode.value == "bundle"

    def test_bundle_request_requires_profiled_session(self):
        response = client.post("/api/resource-bundle", json={
            "session_id": "test-api-bundle", "message": "生成一次函数资源",
            "resource_mode": "bundle",
        })
        assert response.status_code == 409
        assert response.json()["code"] == "RESOURCE_NOT_READY"

    def test_single_request_requires_profiled_session(self):
        response = client.post("/api/resource-bundle", json={
            "session_id": "test-api-single", "message": "生成课程讲解",
            "resource_mode": "single", "resource_type": "course_explanation",
        })
        assert response.status_code == 409
        assert response.json()["code"] == "RESOURCE_NOT_READY"

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

    def test_v1_chat_still_returns_text_without_bundle(self, monkeypatch):
        async def handle_message(_db, _session_id, _message, **_kwargs):
            return ChatResult("诊断问题", "diagnosis", "DIAGNOSING")

        monkeypatch.setattr(chat, "handle_message", handle_message)
        response = client.post("/api/chat", json={
            "session_id": "test-v1", "message": "你好",
        })
        assert response.status_code == 200
        assert response.json()["reply"] == "诊断问题"
        assert response.json()["phase"] == "diagnosis"
        assert response.json()["bundle"] is None
