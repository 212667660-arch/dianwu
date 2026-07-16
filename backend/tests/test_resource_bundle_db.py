from __future__ import annotations

import uuid

import pytest

from backend.database import SessionLocal, init_db
from backend.services.resource_db import (
    delete_bundle,
    get_bundle,
    save_artifact,
    save_bundle,
)
from backend.services import resource_db
from backend.protocols.v2.models import (
    ArtifactStatus,
    ArtifactType,
    BundleStatus,
    ResourceArtifact,
    ResourceBundle,
)


@pytest.fixture(autouse=True)
def _init_db():
    init_db()


def _make_bundle_id() -> str:
    return f"test-{uuid.uuid4().hex[:12]}"


def test_save_and_retrieve_bundle():
    bundle_id = _make_bundle_id()
    artifact = ResourceArtifact(
        artifact_id="a1", type=ArtifactType.COURSE_EXPLANATION,
        title="讲解", status=ArtifactStatus.SUCCEEDED, body="内容",
        quality_score=85, quality_issues=[],
    )
    bundle = ResourceBundle(
        bundle_id=bundle_id, topic="测试", profile_version=1,
        learning_state_version="v1", mode="bundle",
        status=BundleStatus.COMPLETED,
        requested_types=[ArtifactType.COURSE_EXPLANATION],
        artifacts=[artifact], aggregate_quality=85.0,
        created_at="2026-07-16T10:00:00Z",
    )
    with SessionLocal() as db:
        save_bundle(db, f"session-{bundle_id}", bundle)
        db.commit()
    with SessionLocal() as db:
        loaded = get_bundle(db, bundle_id)
        assert loaded is not None
        assert loaded["bundle_id"] == bundle_id
        assert loaded["status"] == "COMPLETED"


def test_save_partial_and_retry_artifact():
    bundle_id = _make_bundle_id()
    aid = f"af-{uuid.uuid4().hex[:8]}"
    artifact = ResourceArtifact(
        artifact_id=aid, type=ArtifactType.MIND_MAP, title="导图",
        status=ArtifactStatus.FAILED, body="", quality_score=0,
        quality_issues=["MERMAID_PARSE_ERROR"],
        error_code="SPECIALIST_FAILED", retryable=True,
    )
    bundle = ResourceBundle(
        bundle_id=bundle_id, topic="测试", profile_version=1,
        learning_state_version="v1", mode="bundle",
        status=BundleStatus.PARTIAL,
        requested_types=[ArtifactType.MIND_MAP],
        artifacts=[artifact], aggregate_quality=0.0,
        created_at="2026-07-16T10:00:00Z",
    )
    with SessionLocal() as db:
        save_bundle(db, f"session-{bundle_id}", bundle)
        db.commit()
    retry_artifact = ResourceArtifact(
        artifact_id=aid, type=ArtifactType.MIND_MAP,
        title="导图（重试）", status=ArtifactStatus.SUCCEEDED,
        body="flowchart TD\n  A-->B", quality_score=90, quality_issues=[],
    )
    with SessionLocal() as db:
        save_artifact(db, bundle_id, retry_artifact)
        db.commit()
    with SessionLocal() as db:
        loaded = get_bundle(db, bundle_id)
        artifacts = loaded.get("artifacts", [])
        assert len(artifacts) == 1
        assert artifacts[0]["status"] == "SUCCEEDED"


def test_delete_bundle():
    bundle_id = _make_bundle_id()
    artifact = ResourceArtifact(
        artifact_id="a1", type=ArtifactType.COURSE_EXPLANATION,
        title="讲解", status=ArtifactStatus.SUCCEEDED, body="内容",
        quality_score=80, quality_issues=[],
    )
    bundle = ResourceBundle(
        bundle_id=bundle_id, topic="测试", profile_version=1,
        learning_state_version="v1", mode="single",
        status=BundleStatus.COMPLETED,
        requested_types=[ArtifactType.COURSE_EXPLANATION],
        artifacts=[artifact], aggregate_quality=80.0,
        created_at="2026-07-16T10:00:00Z",
    )
    with SessionLocal() as db:
        save_bundle(db, f"session-{bundle_id}", bundle)
        db.commit()
    with SessionLocal() as db:
        delete_bundle(db, bundle_id)
        db.commit()
    with SessionLocal() as db:
        assert get_bundle(db, bundle_id) is None


def test_v1_tables_unchanged():
    from backend.services import db as repo
    sid = f"test-v1-{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        session = repo.get_or_create_session(db, sid)
        assert session is not None
        assert session.session_id == sid
        repo.delete_session(db, sid)
        db.commit()


def test_save_bundle_writes_session_and_all_artifacts():
    bundle_id = _make_bundle_id()
    session_id = f"owner-{uuid.uuid4().hex[:8]}"
    artifacts = [
        ResourceArtifact(
            artifact_id=f"{bundle_id}-course",
            type=ArtifactType.COURSE_EXPLANATION,
            title="讲解",
            status=ArtifactStatus.SUCCEEDED,
            body="内容",
            quality_score=85,
        ),
        ResourceArtifact(
            artifact_id=f"{bundle_id}-mind",
            type=ArtifactType.MIND_MAP,
            title="导图",
            status=ArtifactStatus.SUCCEEDED,
            body="flowchart TD\nA-->B",
            quality_score=90,
        ),
    ]
    bundle = ResourceBundle(
        bundle_id=bundle_id,
        topic="测试",
        profile_version=1,
        learning_state_version="1",
        mode="bundle",
        status=BundleStatus.COMPLETED,
        requested_types=[ArtifactType.COURSE_EXPLANATION, ArtifactType.MIND_MAP],
        artifacts=artifacts,
        aggregate_quality=87.5,
        created_at="2026-07-17T00:00:00Z",
    )
    with SessionLocal() as db:
        save_bundle(db, session_id, bundle)
        db.commit()
        loaded = resource_db.get_bundle_for_session(db, session_id, bundle_id)
        assert loaded is not None
        assert loaded["session_id"] == session_id
        assert len(loaded["artifacts"]) == 2
        assert resource_db.get_bundle_for_session(db, "other", bundle_id) is None
        delete_bundle(db, bundle_id)
        db.commit()


def test_delete_session_removes_owned_bundles():
    from backend.services import db as repo

    bundle_id = _make_bundle_id()
    session_id = f"bundle-session-{uuid.uuid4().hex[:8]}"
    artifact = ResourceArtifact(
        artifact_id=f"{bundle_id}-artifact",
        type=ArtifactType.COURSE_EXPLANATION,
        title="讲解",
        status=ArtifactStatus.SUCCEEDED,
        body="内容",
        quality_score=80,
    )
    bundle = ResourceBundle(
        bundle_id=bundle_id,
        topic="测试",
        profile_version=1,
        learning_state_version="1",
        mode="single",
        status=BundleStatus.COMPLETED,
        requested_types=[ArtifactType.COURSE_EXPLANATION],
        artifacts=[artifact],
        aggregate_quality=80,
        created_at="2026-07-17T00:00:00Z",
    )
    with SessionLocal() as db:
        repo.get_or_create_session(db, session_id)
        save_bundle(db, session_id, bundle)
        db.commit()
        assert len(resource_db.list_bundles(db, session_id)) == 1
        repo.delete_session(db, session_id)
        assert resource_db.list_bundles(db, session_id) == []
