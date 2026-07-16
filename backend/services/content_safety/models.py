from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SafetyStage(str, Enum):
    REQUEST = "REQUEST"
    CONTEXT = "CONTEXT"
    PLAN = "PLAN"
    ARTIFACT = "ARTIFACT"
    RENDER = "RENDER"


class SafetyAction(str, Enum):
    ALLOW = "ALLOW"
    REDACT = "REDACT"
    REGENERATE = "REGENERATE"
    BLOCK = "BLOCK"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskCategory(str, Enum):
    PROMPT_INJECTION = "PROMPT_INJECTION"
    SECRET_OR_CREDENTIAL = "SECRET_OR_CREDENTIAL"
    PERSONAL_DATA = "PERSONAL_DATA"
    MINOR_SAFETY = "MINOR_SAFETY"
    SELF_HARM = "SELF_HARM"
    VIOLENCE_OR_WEAPONS = "VIOLENCE_OR_WEAPONS"
    ILLEGAL_WRONGDOING = "ILLEGAL_WRONGDOING"
    CYBER_ABUSE = "CYBER_ABUSE"
    FRAUD_OR_DECEPTION = "FRAUD_OR_DECEPTION"
    HATE_OR_HARASSMENT = "HATE_OR_HARASSMENT"
    DRUG_OR_DANGEROUS_EXPERIMENT = "DRUG_OR_DANGEROUS_EXPERIMENT"
    ACADEMIC_INTEGRITY = "ACADEMIC_INTEGRITY"
    HIGH_STAKES_ADVICE = "HIGH_STAKES_ADVICE"
    FABRICATED_OR_UNTRUSTED_CITATION = "FABRICATED_OR_UNTRUSTED_CITATION"
    ACTIVE_CONTENT_OR_UNSAFE_RENDERING = "ACTIVE_CONTENT_OR_UNSAFE_RENDERING"


class SafetyMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: SafetyStage
    decision: SafetyAction
    risk_level: RiskLevel
    categories: list[RiskCategory] = Field(default_factory=list, max_length=20)
    reason_codes: list[str] = Field(default_factory=list, max_length=20)
    policy_version: Literal["content-safety/v1"] = "content-safety/v1"
    reviewer_profile_id: str | None = Field(default=None, max_length=64)
    checked_at: str = Field(min_length=1, max_length=64)

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("reason_codes must be unique")
        if any(
            not item
            or len(item) > 128
            or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:.-" for character in item)
            for item in value
        ):
            raise ValueError("reason_codes must use bounded stable identifiers")
        return value
