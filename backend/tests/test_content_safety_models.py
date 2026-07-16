from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.services.content_safety.models import (
    RiskCategory,
    RiskLevel,
    SafetyAction,
    SafetyMetadata,
    SafetyStage,
)


def test_safety_metadata_uses_fixed_policy_and_controlled_values():
    metadata = SafetyMetadata(
        stage=SafetyStage.REQUEST,
        decision=SafetyAction.ALLOW,
        risk_level=RiskLevel.LOW,
        categories=[RiskCategory.PROMPT_INJECTION],
        reason_codes=["EDUCATIONAL_CONTEXT"],
        checked_at=datetime.now(timezone.utc).isoformat(),
    )

    assert metadata.policy_version == "content-safety/v1"
    assert metadata.reviewer_profile_id is None


def test_safety_metadata_rejects_unknown_fields_and_categories():
    with pytest.raises(ValidationError):
        SafetyMetadata(
            stage="REQUEST",
            decision="ALLOW",
            risk_level="LOW",
            categories=["UNKNOWN_RISK"],
            reason_codes=[],
            checked_at="2026-07-17T00:00:00+00:00",
            explanation="free text is forbidden",
        )
