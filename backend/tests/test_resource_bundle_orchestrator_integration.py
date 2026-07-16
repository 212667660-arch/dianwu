from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.database import SessionLocal, init_db
from backend.main import app
from backend.protocols.v2.models import (
    ArtifactStatus,
    ArtifactType,
    BundleStatus,
    ResourceArtifact,
    ResourceBundle,
)
from backend.routers import resource
from backend.services import db as repo
from backend.services import orchestrator
from backend.services.resource_db import save_bundle


client = TestClient(app)


@pytest.fixture(autouse=True)
def _initialize_database() -> None:
    init_db()


def _profiled_session(session_id: str) -> None:
    with SessionLocal() as db:
        session = repo.get_or_create_session(db, session_id)
        session.state = repo.SessionState.PROFILED.value
        session.last_stable_state = repo.SessionState.PROFILED.value
        session.profile_text = "[协议 learning-profile/v1]\n学科: 数学\n[协议结束]"
        session.profile_version = 1
        repo.commit(db)


def _bundle(bundle_id: str = "bundle-contract") -> ResourceBundle:
    artifact = ResourceArtifact(
        artifact_id=f"{bundle_id}-course",
        type=ArtifactType.COURSE_EXPLANATION,
        title="课程讲解",
        status=ArtifactStatus.SUCCEEDED,
        body="内容",
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


def test_nonstream_chat_returns_typed_bundle(monkeypatch) -> None:
    session_id = f"chat-bundle-{uuid.uuid4().hex[:10]}"
    _profiled_session(session_id)
    bundle = _bundle()

    class FakeService:
        async def generate(self, _db, _session_id, _message, _selection, **_kwargs):
            return bundle

    monkeypatch.setattr(orchestrator, "resource_bundle_service", FakeService())
    response = client.post("/api/chat", json={
        "session_id": session_id,
        "message": "生成资源包",
        "resource_mode": "bundle",
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == "resource"
    assert payload["state"] == repo.SessionState.PROFILED.value
    assert payload["bundle"]["protocol_version"] == "learning-resource-bundle/v2"
    assert payload["bundle"]["status"] == "COMPLETED"


def test_chat_request_rejects_extra_fields() -> None:
    response = client.post("/api/chat", json={
        "session_id": "strict-chat",
        "message": "生成",
        "resource_mode": "bundle",
        "model_profile": "must-not-cross-renderer-boundary",
    })

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"


def test_session_history_contains_owned_resource_bundles() -> None:
    session_id = f"history-bundle-{uuid.uuid4().hex[:10]}"
    _profiled_session(session_id)
    bundle = _bundle(f"bundle-history-{uuid.uuid4().hex[:8]}")
    with SessionLocal() as db:
        save_bundle(db, session_id, bundle)
        repo.commit(db)

    response = client.get(f"/api/sessions/{session_id}")

    assert response.status_code == 200
    payload = response.json()
    assert [item["bundle_id"] for item in payload["resource_bundles"]] == [bundle.bundle_id]
    assert payload["resource_bundles"][0]["artifacts"][0]["type"] == "course_explanation"


def test_retry_route_replaces_only_requested_artifact(monkeypatch) -> None:
    bundle = _bundle("bundle-retry-route")
    calls = []

    class FakeService:
        async def retry_artifact(
            self, db, session_id, bundle_id, artifact_type, *, generation_id
        ):
            calls.append((session_id, bundle_id, artifact_type, generation_id))
            return bundle

    monkeypatch.setattr(resource, "resource_bundle_service", FakeService())
    response = client.post(
        "/api/resource-bundles/bundle-retry-route/artifacts/course_explanation/retry",
        json={"session_id": "retry-session"},
    )

    assert response.status_code == 200
    assert response.json()["bundle"]["bundle_id"] == bundle.bundle_id
    assert len(calls) == 1
    assert calls[0][0:3] == (
        "retry-session",
        "bundle-retry-route",
        ArtifactType.COURSE_EXPLANATION,
    )


def test_stream_forwards_each_artifact_and_finishes_profiled(monkeypatch) -> None:
    session_id = f"stream-five-{uuid.uuid4().hex[:10]}"
    _profiled_session(session_id)
    bundle = _bundle("bundle-stream-five")

    class FakeService:
        async def generate(self, _db, _sid, _message, _selection, *, on_event, **_kwargs):
            for artifact_type in ArtifactType:
                await on_event({
                    "event": "resource_artifact",
                    "artifact_id": f"bundle-stream-five-{artifact_type.value}",
                    "type": artifact_type.value,
                    "title": artifact_type.value,
                    "status": "SUCCEEDED",
                    "body": "内容",
                    "type_specific_data": {},
                    "quality_score": 80,
                    "quality_issues": [],
                    "error_code": None,
                    "retryable": False,
                })
            await on_event({"event": "resource_bundle", **bundle.model_dump(mode="json")})
            return bundle

    async def connected() -> bool:
        return False

    monkeypatch.setattr(orchestrator, "resource_bundle_service", FakeService())
    with SessionLocal() as db:
        async def collect():
            return [event async for event in orchestrator.stream_message(
                db,
                session_id,
                "生成五类资源",
                connected,
                resource_mode="bundle",
            )]

        events = asyncio.run(collect())

    assert sum(event["event"] == "resource_artifact" for event in events) == 5
    assert events[-1]["event"] == "done"
    assert events[-1]["state"] == repo.SessionState.PROFILED.value
