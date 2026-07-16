from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from backend.services.content_safety.models import RiskCategory, RiskLevel
from backend.services.content_safety.normalization import normalize_for_scan


class DetectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[RiskCategory] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    blocking: bool = False

    def has(self, category: RiskCategory) -> bool:
        return category in self.categories


class RedactionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    changed: bool = False
    reason_codes: list[str] = Field(default_factory=list)


_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "SECRET_PRIVATE_KEY",
        re.compile(r"-----begin (?:rsa |ec |openssh |dsa )?private key-----", re.IGNORECASE),
    ),
    (
        "SECRET_AUTHORIZATION_BEARER",
        re.compile(r"\bauthorization\s*:\s*bearer\s+[a-z0-9._~+/=-]{8,}", re.IGNORECASE),
    ),
    (
        "SECRET_OPENAI_STYLE_KEY",
        re.compile(r"\bsk-[a-z0-9_-]{20,}\b", re.IGNORECASE),
    ),
    (
        "SECRET_AWS_ACCESS_KEY",
        re.compile(r"\b(?:akia|asia)[a-z0-9]{16}\b", re.IGNORECASE),
    ),
    (
        "SECRET_ASSIGNMENT",
        re.compile(
            r"\b(?:api[_ -]?key|access[_ -]?token|client[_ -]?secret|password)\s*[:=]\s*[a-z0-9._~+/=-]{12,}",
            re.IGNORECASE,
        ),
    ),
)

_ACTIVE_CONTENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ACTIVE_SCRIPT_TAG", re.compile(r"<\s*script(?:\s|>)", re.IGNORECASE)),
    ("ACTIVE_EVENT_HANDLER", re.compile(r"\son[a-z]{3,}\s*=", re.IGNORECASE)),
    ("ACTIVE_DANGEROUS_SCHEME", re.compile(r"\b(?:javascript|data|file|vbscript)\s*:", re.IGNORECASE)),
    ("ACTIVE_EMBEDDED_OBJECT", re.compile(r"<\s*(?:iframe|object|embed|foreignobject)(?:\s|>)", re.IGNORECASE)),
)

_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}(?![\w.-])", re.IGNORECASE)
_IDENTITY = re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")


def detect_structures(text: str) -> DetectionResult:
    scan = normalize_for_scan(text)
    categories: list[RiskCategory] = []
    reason_codes: list[str] = []

    for code, pattern in _SECRET_PATTERNS:
        if pattern.search(scan):
            categories.append(RiskCategory.SECRET_OR_CREDENTIAL)
            reason_codes.append(code)
    for code, pattern in _ACTIVE_CONTENT_PATTERNS:
        if pattern.search(scan):
            categories.append(RiskCategory.ACTIVE_CONTENT_OR_UNSAFE_RENDERING)
            reason_codes.append(code)

    categories = list(dict.fromkeys(categories))
    reason_codes = list(dict.fromkeys(reason_codes))
    blocking = bool(categories)
    return DetectionResult(
        categories=categories,
        reason_codes=reason_codes,
        risk_level=RiskLevel.CRITICAL if blocking else RiskLevel.LOW,
        blocking=blocking,
    )


def redact_personal_data(text: str) -> RedactionResult:
    redacted = text
    reason_codes: list[str] = []
    for pattern, replacement, reason_code in (
        (_IDENTITY, "[身份证号已隐藏]", "PERSONAL_ID_REDACTED"),
        (_PHONE, "[手机号已隐藏]", "PERSONAL_PHONE_REDACTED"),
        (_EMAIL, "[邮箱已隐藏]", "PERSONAL_EMAIL_REDACTED"),
    ):
        redacted, count = pattern.subn(replacement, redacted)
        if count:
            reason_codes.append(reason_code)
    return RedactionResult(
        text=redacted,
        changed=redacted != text,
        reason_codes=reason_codes,
    )
