import inspect

from backend.services.content_safety.audit import safety_audit_payload
from backend.services.content_safety.models import (
    RiskLevel,
    SafetyAction,
    SafetyMetadata,
    SafetyStage,
)


def test_audit_api_cannot_accept_candidate_or_raw_output():
    parameters = inspect.signature(safety_audit_payload).parameters

    assert "candidate" not in parameters
    assert "raw_output" not in parameters
    assert "text" not in parameters


def test_audit_payload_contains_only_controlled_metadata():
    metadata = SafetyMetadata(
        stage=SafetyStage.REQUEST,
        decision=SafetyAction.REDACT,
        risk_level=RiskLevel.MEDIUM,
        reason_codes=["PERSONAL_PHONE_REDACTED"],
        checked_at="2026-07-17T00:00:00+00:00",
    )
    payload = safety_audit_payload(
        request_id="req-1",
        session_tag="session-safe-tag",
        metadata=metadata,
        duration_ms=12,
        redacted=True,
        regenerated=False,
        blocked=False,
    )

    assert payload == {
        "request_id": "req-1",
        "session_tag": "session-safe-tag",
        "stage": "REQUEST",
        "decision": "REDACT",
        "risk_level": "MEDIUM",
        "categories": [],
        "reason_codes": ["PERSONAL_PHONE_REDACTED"],
        "policy_version": "content-safety/v1",
        "reviewer_profile_id": None,
        "duration_ms": 12,
        "redacted": True,
        "regenerated": False,
        "blocked": False,
    }
