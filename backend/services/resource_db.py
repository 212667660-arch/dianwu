from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.protocols.v2.models import ResourceArtifact, ResourceBundle


def save_bundle(db: Session, session_id: str, bundle: ResourceBundle) -> None:
    artifacts_json = json.dumps(
        [artifact.model_dump(mode="json") for artifact in bundle.artifacts],
        ensure_ascii=False,
    )
    knowledge_json = json.dumps(bundle.knowledge_sources, ensure_ascii=False)
    public_json = json.dumps(bundle.public_sources, ensure_ascii=False)
    requested_json = json.dumps([t.value for t in bundle.requested_types], ensure_ascii=False)
    db.execute(
        text("""
            INSERT INTO resource_bundles (bundle_id, session_id, protocol_version, topic, profile_version,
                learning_state_version, mode, status, requested_types, artifacts_json,
                aggregate_quality, created_at, knowledge_sources_json, public_sources_json)
            VALUES (:bid, :sid, :pv, :topic, :profile_v, :lsv, :mode, :status, :rt, :artifacts,
                :aq, :cat, :ks, :ps)
            ON CONFLICT(bundle_id) DO UPDATE SET
                session_id = excluded.session_id,
                protocol_version = excluded.protocol_version,
                topic = excluded.topic,
                profile_version = excluded.profile_version,
                learning_state_version = excluded.learning_state_version,
                mode = excluded.mode,
                status = excluded.status,
                requested_types = excluded.requested_types,
                artifacts_json = excluded.artifacts_json,
                aggregate_quality = excluded.aggregate_quality,
                knowledge_sources_json = excluded.knowledge_sources_json,
                public_sources_json = excluded.public_sources_json
        """),
        {"bid": bundle.bundle_id, "sid": session_id, "pv": bundle.protocol_version,
         "topic": bundle.topic, "profile_v": bundle.profile_version,
         "lsv": bundle.learning_state_version, "mode": bundle.mode,
         "status": bundle.status.value, "rt": requested_json,
         "artifacts": artifacts_json, "aq": bundle.aggregate_quality,
         "cat": bundle.created_at, "ks": knowledge_json, "ps": public_json},
    )
    db.execute(
        text("DELETE FROM resource_artifacts WHERE bundle_id = :bid"),
        {"bid": bundle.bundle_id},
    )
    for artifact in bundle.artifacts:
        save_artifact(db, bundle.bundle_id, artifact)


def save_artifact(db: Session, bundle_id: str, artifact: ResourceArtifact) -> None:
    tsd = json.dumps(artifact.type_specific_data, ensure_ascii=False)
    qi = json.dumps(artifact.quality_issues, ensure_ascii=False)
    safety = (
        json.dumps(artifact.safety.model_dump(mode="json"), ensure_ascii=False)
        if artifact.safety is not None
        else None
    )
    db.execute(
        text("""
            INSERT INTO resource_artifacts (artifact_id, bundle_id, type, title, status,
                body, type_specific_data_json, quality_score, quality_issues_json,
                error_code, retryable, safety_json)
            VALUES (:aid, :bid, :type, :title, :status, :body, :tsd, :qs, :qi, :ec, :retry, :safety)
            ON CONFLICT(artifact_id) DO UPDATE SET
                bundle_id = excluded.bundle_id,
                title = excluded.title, status = excluded.status,
                body = excluded.body,
                type_specific_data_json = excluded.type_specific_data_json,
                quality_score = excluded.quality_score,
                quality_issues_json = excluded.quality_issues_json,
                error_code = excluded.error_code, retryable = excluded.retryable,
                safety_json = excluded.safety_json
        """),
        {"aid": artifact.artifact_id, "bid": bundle_id,
         "type": artifact.type.value, "title": artifact.title,
         "status": artifact.status.value, "body": artifact.body,
         "tsd": tsd, "qs": artifact.quality_score, "qi": qi,
         "ec": artifact.error_code, "retry": 1 if artifact.retryable else 0,
         "safety": safety},
    )


def get_bundle(db: Session, bundle_id: str) -> Optional[dict[str, Any]]:
    row = db.execute(
        text("SELECT * FROM resource_bundles WHERE bundle_id = :bid"), {"bid": bundle_id}
    ).mappings().first()
    if row is None:
        return None
    result = dict(row)
    artifact_rows = db.execute(
        text("SELECT * FROM resource_artifacts WHERE bundle_id = :bid"), {"bid": bundle_id}
    ).mappings().all()
    artifacts: list[dict[str, Any]] = []
    for artifact_row in artifact_rows:
        artifact = dict(artifact_row)
        artifact["type_specific_data"] = json.loads(
            artifact.get("type_specific_data_json") or "{}"
        )
        artifact["quality_issues"] = json.loads(
            artifact.get("quality_issues_json") or "[]"
        )
        artifact["retryable"] = bool(artifact.get("retryable"))
        artifact["safety"] = (
            json.loads(artifact["safety_json"])
            if artifact.get("safety_json")
            else None
        )
        artifacts.append(artifact)
    result["artifacts"] = artifacts
    result["requested_types"] = json.loads(result.get("requested_types") or "[]")
    result["knowledge_sources"] = json.loads(result.get("knowledge_sources_json", "[]"))
    result["public_sources"] = json.loads(result.get("public_sources_json", "[]"))
    return result


def get_bundle_for_session(
    db: Session,
    session_id: str,
    bundle_id: str,
) -> Optional[dict[str, Any]]:
    owner = db.execute(
        text(
            "SELECT 1 FROM resource_bundles "
            "WHERE bundle_id = :bid AND session_id = :sid"
        ),
        {"bid": bundle_id, "sid": session_id},
    ).first()
    return get_bundle(db, bundle_id) if owner is not None else None


def list_bundles(db: Session, session_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            "SELECT bundle_id FROM resource_bundles "
            "WHERE session_id = :sid ORDER BY created_at DESC"
        ),
        {"sid": session_id},
    ).all()
    return [
        bundle
        for row in rows
        if (bundle := get_bundle_for_session(db, session_id, str(row[0]))) is not None
    ]


def delete_bundles_for_session(db: Session, session_id: str) -> None:
    rows = db.execute(
        text("SELECT bundle_id FROM resource_bundles WHERE session_id = :sid"),
        {"sid": session_id},
    ).all()
    for row in rows:
        delete_bundle(db, str(row[0]))


def delete_bundle(db: Session, bundle_id: str) -> None:
    db.execute(text("DELETE FROM resource_artifacts WHERE bundle_id = :bid"), {"bid": bundle_id})
    db.execute(text("DELETE FROM resource_bundles WHERE bundle_id = :bid"), {"bid": bundle_id})
