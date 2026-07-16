import uuid
from datetime import datetime, timezone

from sqlalchemy import inspect, text

from backend.database import SessionLocal, engine, init_db
from backend.models.schemas import ResourceArtifactResponse
from backend.protocols.v2.models import (
    ArtifactStatus,
    ArtifactType,
    BundleStatus,
    ResourceArtifact,
    ResourceBundle,
)
from backend.services.content_safety.models import (
    RiskLevel,
    SafetyAction,
    SafetyMetadata,
    SafetyStage,
)
from backend.services.resource_db import get_bundle, save_bundle


def safety() -> SafetyMetadata:
    return SafetyMetadata(
        stage=SafetyStage.ARTIFACT,
        decision=SafetyAction.ALLOW,
        risk_level=RiskLevel.LOW,
        reason_codes=["REVIEWED_SAFE"],
        reviewer_profile_id="reviewer",
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


def make_bundle(bundle_id: str, artifact: ResourceArtifact) -> ResourceBundle:
    return ResourceBundle(
        bundle_id=bundle_id,
        topic="测试",
        profile_version=1,
        learning_state_version="1",
        mode="single",
        status=BundleStatus.COMPLETED,
        requested_types=[artifact.type],
        artifacts=[artifact],
        aggregate_quality=artifact.quality_score,
        created_at="2026-07-17T00:00:00+00:00",
    )


def test_review_metadata_round_trips_through_v2_artifact_and_response():
    init_db()
    bundle_id = f"safety-{uuid.uuid4().hex[:12]}"
    artifact = ResourceArtifact(
        artifact_id=f"{bundle_id}-a1",
        type=ArtifactType.COURSE_EXPLANATION,
        title="讲解",
        status=ArtifactStatus.SUCCEEDED,
        body="安全内容",
        quality_score=90,
        safety=safety(),
    )

    with SessionLocal() as db:
        save_bundle(db, f"session-{bundle_id}", make_bundle(bundle_id, artifact))
        db.commit()
        loaded = get_bundle(db, bundle_id)

    assert loaded["artifacts"][0]["safety"]["policy_version"] == "content-safety/v1"
    response = ResourceArtifactResponse.model_validate(
        artifact.model_dump(mode="json")
    )
    assert response.safety is not None
    assert response.safety.reviewer_profile_id == "reviewer"


def test_legacy_artifact_without_safety_metadata_remains_readable():
    init_db()
    bundle_id = f"legacy-{uuid.uuid4().hex[:12]}"
    artifact = ResourceArtifact(
        artifact_id=f"{bundle_id}-a1",
        type=ArtifactType.COURSE_EXPLANATION,
        title="讲解",
        status=ArtifactStatus.SUCCEEDED,
        body="历史内容",
        quality_score=80,
    )
    with SessionLocal() as db:
        save_bundle(db, f"session-{bundle_id}", make_bundle(bundle_id, artifact))
        db.execute(
            text("UPDATE resource_artifacts SET safety_json = NULL WHERE artifact_id = :aid"),
            {"aid": artifact.artifact_id},
        )
        db.commit()
        loaded = get_bundle(db, bundle_id)

    assert loaded["artifacts"][0]["safety"] is None


def test_migration_adds_optional_safety_columns():
    init_db()
    inspector = inspect(engine)

    resource_columns = {item["name"] for item in inspector.get_columns("resources")}
    artifact_columns = {item["name"] for item in inspector.get_columns("resource_artifacts")}
    assert "safety_json" in resource_columns
    assert "safety_json" in artifact_columns
