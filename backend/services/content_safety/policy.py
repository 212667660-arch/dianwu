from __future__ import annotations

import re
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from backend.services.content_safety.detectors import (
    detect_structures,
    redact_personal_data,
)
from backend.services.content_safety.models import (
    RiskCategory,
    RiskLevel,
    SafetyAction,
    SafetyMetadata,
    SafetyStage,
)
from backend.services.content_safety.normalization import normalize_for_scan


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: SafetyAction
    safe_text: str
    metadata: SafetyMetadata
    public_error_code: str | None = None


_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"(?:忽略|无视|覆盖|绕过).{0,20}(?:系统|提示|规则|指令)"),
    re.compile(r"(?:你现在是|现在扮演).{0,20}(?:系统|开发者|无限制|不受限)"),
    re.compile(
        r"ignore\s+(?:all\s+|the\s+)?(?:(?:previous|above)(?:\s+system)?|system)\s+instructions?",
        re.IGNORECASE,
    ),
    re.compile(r"(?:reveal|print|output).{0,20}(?:system prompt|secret|api key)", re.IGNORECASE),
)


def _metadata(
    stage: SafetyStage,
    action: SafetyAction,
    risk_level: RiskLevel,
    categories: list[RiskCategory],
    reason_codes: list[str],
) -> SafetyMetadata:
    return SafetyMetadata(
        stage=stage,
        decision=action,
        risk_level=risk_level,
        categories=categories,
        reason_codes=list(dict.fromkeys(reason_codes)),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


def evaluate_request(text: str) -> PolicyDecision:
    structural = detect_structures(text)
    if structural.has(RiskCategory.SECRET_OR_CREDENTIAL):
        return PolicyDecision(
            action=SafetyAction.BLOCK,
            safe_text="",
            public_error_code="CONTENT_SECRET_DETECTED",
            metadata=_metadata(
                SafetyStage.REQUEST,
                SafetyAction.BLOCK,
                RiskLevel.CRITICAL,
                structural.categories,
                structural.reason_codes,
            ),
        )
    if structural.blocking:
        return PolicyDecision(
            action=SafetyAction.BLOCK,
            safe_text="",
            public_error_code="CONTENT_SAFETY_INPUT_BLOCKED",
            metadata=_metadata(
                SafetyStage.REQUEST,
                SafetyAction.BLOCK,
                structural.risk_level,
                structural.categories,
                structural.reason_codes,
            ),
        )

    redaction = redact_personal_data(text)
    if redaction.changed:
        return PolicyDecision(
            action=SafetyAction.REDACT,
            safe_text=redaction.text,
            public_error_code="CONTENT_PERSONAL_DATA_REDACTED",
            metadata=_metadata(
                SafetyStage.REQUEST,
                SafetyAction.REDACT,
                RiskLevel.MEDIUM,
                [RiskCategory.PERSONAL_DATA],
                redaction.reason_codes,
            ),
        )
    return PolicyDecision(
        action=SafetyAction.ALLOW,
        safe_text=text,
        metadata=_metadata(
            SafetyStage.REQUEST,
            SafetyAction.ALLOW,
            RiskLevel.LOW,
            [],
            [],
        ),
    )


def evaluate_context(text: str) -> PolicyDecision:
    structural = detect_structures(text)
    normalized = normalize_for_scan(text)
    injection_codes = [
        f"PROMPT_INJECTION_PATTERN_{index}"
        for index, pattern in enumerate(_PROMPT_INJECTION_PATTERNS, start=1)
        if pattern.search(normalized)
    ]
    categories = list(structural.categories)
    reason_codes = list(structural.reason_codes)
    if injection_codes:
        categories.append(RiskCategory.PROMPT_INJECTION)
        reason_codes.extend(injection_codes)
    if structural.blocking or injection_codes:
        return PolicyDecision(
            action=SafetyAction.BLOCK,
            safe_text="",
            public_error_code="CONTENT_SAFETY_INPUT_BLOCKED",
            metadata=_metadata(
                SafetyStage.CONTEXT,
                SafetyAction.BLOCK,
                RiskLevel.HIGH,
                list(dict.fromkeys(categories)),
                reason_codes,
            ),
        )
    redaction = redact_personal_data(text)
    if redaction.changed:
        return PolicyDecision(
            action=SafetyAction.REDACT,
            safe_text=redaction.text,
            public_error_code="CONTENT_PERSONAL_DATA_REDACTED",
            metadata=_metadata(
                SafetyStage.CONTEXT,
                SafetyAction.REDACT,
                RiskLevel.MEDIUM,
                [RiskCategory.PERSONAL_DATA],
                redaction.reason_codes,
            ),
        )
    return PolicyDecision(
        action=SafetyAction.ALLOW,
        safe_text=text,
        metadata=_metadata(
            SafetyStage.CONTEXT,
            SafetyAction.ALLOW,
            RiskLevel.LOW,
            [],
            [],
        ),
    )
