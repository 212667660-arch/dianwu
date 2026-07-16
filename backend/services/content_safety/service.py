from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from backend.errors import (
    ContentArtifactBlockedError,
    ContentSafetyInputBlockedError,
    ContentSecretDetectedError,
)
from backend.protocols.v2.models import ResourceArtifact
from backend.services.content_safety.citations import validate_citations
from backend.services.content_safety.detectors import detect_structures, redact_personal_data
from backend.services.content_safety.models import (
    RiskCategory,
    RiskLevel,
    SafetyAction,
    SafetyMetadata,
    SafetyStage,
)
from backend.services.content_safety.policy import evaluate_request
from backend.services.content_safety.reviewer import ReviewContext, SafetyReviewer


class SafeRequestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    safe_text: str
    metadata: SafetyMetadata


class ArtifactSafetyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    action: SafetyAction
    artifact: ResourceArtifact | None = None
    metadata: SafetyMetadata
    reason_codes: list[str] = Field(default_factory=list)


def _local_metadata(
    *,
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
        categories=list(dict.fromkeys(categories)),
        reason_codes=list(dict.fromkeys(reason_codes)),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


class ContentSafetyService:
    def __init__(self, *, reviewer: SafetyReviewer | None = None) -> None:
        self._reviewer = reviewer or SafetyReviewer()

    async def gate_request(
        self,
        text: str,
        *,
        intent: str | None = None,
        subject_category: str = "other",
        generation_profile_id: str | None = None,
    ) -> SafeRequestResult:
        deterministic = evaluate_request(text)
        if deterministic.action == SafetyAction.BLOCK:
            if deterministic.public_error_code == "CONTENT_SECRET_DETECTED":
                raise ContentSecretDetectedError()
            raise ContentSafetyInputBlockedError()
        reviewed = await self._reviewer.review(
            candidate=deterministic.safe_text,
            generation_profile_id=generation_profile_id,
            context=ReviewContext(
                stage=SafetyStage.REQUEST,
                intent=(intent or deterministic.safe_text)[:500] or "学习请求",
                subject_category=subject_category or "other",
                audience="student",
            ),
        )
        if reviewed.metadata.decision not in {SafetyAction.ALLOW, SafetyAction.REDACT}:
            raise ContentSafetyInputBlockedError()
        if (
            reviewed.metadata.decision == SafetyAction.REDACT
            and deterministic.action != SafetyAction.REDACT
        ):
            raise ContentSafetyInputBlockedError()
        metadata = reviewed.metadata
        if deterministic.action == SafetyAction.REDACT:
            metadata = metadata.model_copy(update={
                "decision": SafetyAction.REDACT,
                "risk_level": max(
                    (metadata.risk_level, RiskLevel.MEDIUM),
                    key=lambda item: list(RiskLevel).index(item),
                ),
                "categories": list(dict.fromkeys([
                    *metadata.categories,
                    RiskCategory.PERSONAL_DATA,
                ])),
                "reason_codes": list(dict.fromkeys([
                    *metadata.reason_codes,
                    *deterministic.metadata.reason_codes,
                ])),
            })
        return SafeRequestResult(
            safe_text=deterministic.safe_text,
            metadata=metadata,
        )

    async def review_plan(
        self,
        plan_text: str,
        *,
        intent: str,
        subject_category: str,
        generation_profile_id: str | None,
    ) -> SafetyMetadata:
        structural = detect_structures(plan_text)
        if structural.blocking:
            raise ContentArtifactBlockedError()
        reviewed = await self._reviewer.review(
            candidate=plan_text,
            generation_profile_id=generation_profile_id,
            context=ReviewContext(
                stage=SafetyStage.PLAN,
                intent=intent[:500] or "学习资源规划",
                subject_category=subject_category or "other",
                audience="student",
            ),
        )
        if reviewed.metadata.decision != SafetyAction.ALLOW:
            raise ContentArtifactBlockedError()
        return reviewed.metadata

    async def review_artifact(
        self,
        artifact: ResourceArtifact,
        *,
        source_allowlist: set[str],
        intent: str,
        subject_category: str,
        generation_profile_id: str | None = None,
    ) -> ArtifactSafetyResult:
        structural = detect_structures(artifact.body)
        citations = validate_citations(artifact.body, allowed=source_allowlist)
        if structural.blocking or not citations.allowed:
            reasons = [*structural.reason_codes, *citations.reason_codes]
            categories = list(structural.categories)
            if not citations.allowed:
                categories.append(RiskCategory.FABRICATED_OR_UNTRUSTED_CITATION)
            metadata = _local_metadata(
                stage=SafetyStage.ARTIFACT,
                action=SafetyAction.REGENERATE,
                risk_level=RiskLevel.HIGH,
                categories=categories,
                reason_codes=reasons,
            )
            return ArtifactSafetyResult(
                action=SafetyAction.REGENERATE,
                metadata=metadata,
                reason_codes=metadata.reason_codes,
            )

        redaction = redact_personal_data(artifact.body)
        candidate = redaction.text
        reviewed = await self._reviewer.review(
            candidate=candidate,
            generation_profile_id=generation_profile_id,
            context=ReviewContext(
                stage=SafetyStage.ARTIFACT,
                intent=intent[:500] or "学习资源生成",
                subject_category=subject_category or "other",
                artifact_type=artifact.type.value,
                audience="student",
            ),
        )
        metadata = reviewed.metadata
        if metadata.decision == SafetyAction.ALLOW:
            if redaction.changed:
                metadata = metadata.model_copy(update={
                    "decision": SafetyAction.REDACT,
                    "risk_level": RiskLevel.MEDIUM,
                    "categories": list(dict.fromkeys([
                        *metadata.categories,
                        RiskCategory.PERSONAL_DATA,
                    ])),
                    "reason_codes": list(dict.fromkeys([
                        *metadata.reason_codes,
                        *redaction.reason_codes,
                    ])),
                })
            safe_artifact = artifact.model_copy(update={
                "body": candidate,
                "safety": metadata,
            })
            return ArtifactSafetyResult(
                action=metadata.decision,
                artifact=safe_artifact,
                metadata=metadata,
                reason_codes=metadata.reason_codes,
            )
        if metadata.decision == SafetyAction.REDACT and redaction.changed:
            safe_artifact = artifact.model_copy(update={
                "body": candidate,
                "safety": metadata,
            })
            return ArtifactSafetyResult(
                action=SafetyAction.REDACT,
                artifact=safe_artifact,
                metadata=metadata,
                reason_codes=metadata.reason_codes,
            )
        return ArtifactSafetyResult(
            action=metadata.decision,
            metadata=metadata,
            reason_codes=metadata.reason_codes,
        )


content_safety_service = ContentSafetyService()
