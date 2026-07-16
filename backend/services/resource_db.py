from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.protocols.v2.models import ResourceArtifact, ResourceBundle


def save_bundle(db: Session, bundle: ResourceBundle) -> None:
    artifacts_json = json.dumps([a.model_dump() for a in bundle.artifacts], ensure_ascii=False)
    knowledge_json = json.dumps(bundle.knowledge_sources, ensure_ascii=False)
    public_json = json.dumps(bundle.public_sources, ensure_ascii=False)
    requested_json = json.dumps([t.value for t in bundle.requested_types], ensure_ascii=False)
    db.execute(
        text("""
            INSERT INTO resource_bundles (bundle_id, protocol_version, topic, profile_version,
                learning_state_version, mode, status, requested_types, artifacts_json,
                aggregate_quality, created_at, knowledge_sources_json, public_sources_json)
            VALUES (:bid, :pv, :topic, :profile_v, :lsv, :mode, :status, :rt, :artifacts,
                :aq, :cat, :ks, :ps)
            ON CONFLICT(bundle_id) DO UPDATE SET
                status = excluded.status,
                artifacts_json = excluded.artifacts_json,
                aggregate_quality = excluded.aggregate_quality
        """),
        {"bid": bundle.bundle_id, "pv": bundle.protocol_version,
         "topic": bundle.topic, "profile_v": bundle.profile_version,
         "lsv": bundle.learning_state_version, "mode": bundle.mode,
         "status": bundle.status.value, "rt": requested_json,
         "artifacts": artifacts_json, "aq": bundle.aggregate_quality,
         "cat": bundle.created_at, "ks": knowledge_json, "ps": public_json},
    )


def save_artifact(db: Session, bundle_id: str, artifact: ResourceArtifact) -> None:
    tsd = json.dumps(artifact.type_specific_data, ensure_ascii=False)
    qi = json.dumps(artifact.quality_issues, ensure_ascii=False)
    db.execute(
        text("""
            INSERT INTO resource_artifacts (artifact_id, bundle_id, type, title, status,
                body, type_specific_data_json, quality_score, quality_issues_json,
                error_code, retryable)
            VALUES (:aid, :bid, :type, :title, :status, :body, :tsd, :qs, :qi, :ec, :retry)
            ON CONFLICT(artifact_id) DO UPDATE SET
                bundle_id = excluded.bundle_id,
                title = excluded.title, status = excluded.status,
                body = excluded.body,
                type_specific_data_json = excluded.type_specific_data_json,
                quality_score = excluded.quality_score,
                quality_issues_json = excluded.quality_issues_json,
                error_code = excluded.error_code, retryable = excluded.retryable
        """),
        {"aid": artifact.artifact_id, "bid": bundle_id,
         "type": artifact.type.value, "title": artifact.title,
         "status": artifact.status.value, "body": artifact.body,
         "tsd": tsd, "qs": artifact.quality_score, "qi": qi,
         "ec": artifact.error_code, "retry": 1 if artifact.retryable else 0},
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
    result["artifacts"] = [dict(ar) for ar in artifact_rows]
    result["knowledge_sources"] = json.loads(result.get("knowledge_sources_json", "[]"))
    result["public_sources"] = json.loads(result.get("public_sources_json", "[]"))
    return result


def delete_bundle(db: Session, bundle_id: str) -> None:
    db.execute(text("DELETE FROM resource_artifacts WHERE bundle_id = :bid"), {"bid": bundle_id})
    db.execute(text("DELETE FROM resource_bundles WHERE bundle_id = :bid"), {"bid": bundle_id})
