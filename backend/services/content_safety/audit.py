from __future__ import annotations

from typing import Any

from backend.services.content_safety.models import SafetyMetadata


def safety_audit_payload(
    *,
    request_id: str,
    session_tag: str,
    metadata: SafetyMetadata,
    duration_ms: int,
    redacted: bool,
    regenerated: bool,
    blocked: bool,
) -> dict[str, Any]:
    return {
        "request_id": request_id[:64],
        "session_tag": session_tag[:64],
        "stage": metadata.stage.value,
        "decision": metadata.decision.value,
        "risk_level": metadata.risk_level.value,
        "categories": [item.value for item in metadata.categories],
        "reason_codes": list(metadata.reason_codes),
        "policy_version": metadata.policy_version,
        "reviewer_profile_id": metadata.reviewer_profile_id,
        "duration_ms": max(0, min(int(duration_ms), 3_600_000)),
        "redacted": bool(redacted),
        "regenerated": bool(regenerated),
        "blocked": bool(blocked),
    }
