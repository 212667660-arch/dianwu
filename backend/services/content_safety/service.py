from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.errors import (
    ContentArtifactBlockedError,
    ContentSafetyInputBlockedError,
    ContentSecretDetectedError,
    SafetyReviewUnavailableError,
)
from backend.protocols.v2.models import ResourceArtifact
from backend.services.content_safety.citations import validate_citations
from backend.services.content_safety.audit import safety_audit_payload
from backend.services.content_safety.detectors import detect_structures, redact_personal_data
from backend.services.content_safety.models import (
    RiskCategory,
    RiskLevel,
    SafetyAction,
    SafetyMetadata,
    SafetyStage,
)
from backend.services.content_safety.policy import evaluate_context, evaluate_request
from backend.services.content_safety.reviewer import ReviewContext, SafetyReviewer


_AUDIT_LOGGER = logging.getLogger("backend.content_safety.audit")


class SafeRequestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    safe_text: str
    metadata: SafetyMetadata


class SafeTextResult(BaseModel):
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


def _redact_publishable_value(
    value: Any,
    reason_codes: list[str],
) -> Any:
    if isinstance(value, str):
        redaction = redact_personal_data(value)
        reason_codes.extend(redaction.reason_codes)
        return redaction.text
    if isinstance(value, list):
        return [
            _redact_publishable_value(item, reason_codes)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: _redact_publishable_value(item, reason_codes)
            for key, item in value.items()
        }
    return value


def _audit_safety_decision(
    *,
    metadata: SafetyMetadata,
    started_at: float,
    request_id: str,
    session_tag: str,
    redacted: bool,
    regenerated: bool,
    blocked: bool,
) -> None:
    payload = safety_audit_payload(
        request_id=request_id or "unassigned",
        session_tag=session_tag or "unassigned",
        metadata=metadata,
        duration_ms=round((time.perf_counter() - started_at) * 1000),
        redacted=redacted,
        regenerated=regenerated,
        blocked=blocked,
    )
    _AUDIT_LOGGER.info(
        "content_safety_audit %s",
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )


def _safe_reviewer_intent(intent: str, fallback: str) -> str:
    decision = evaluate_request(intent or fallback)
    if decision.action == SafetyAction.BLOCK:
        return fallback
    return decision.safe_text[:500] or fallback


class ContentSafetyService:
    def __init__(self, *, reviewer: SafetyReviewer | None = None) -> None:
        self._reviewer = reviewer or SafetyReviewer()

    def filter_context(self, text: str) -> SafeTextResult:
        decision = evaluate_context(text)
        return SafeTextResult(
            safe_text=decision.safe_text,
            metadata=decision.metadata,
        )

    async def _review_with_unavailable_audit(
        self,
        *,
        candidate: str,
        generation_profile_id: str | None,
        context: ReviewContext,
        started_at: float,
        request_id: str,
        session_tag: str,
    ):
        try:
            return await self._reviewer.review(
                candidate=candidate,
                generation_profile_id=generation_profile_id,
                context=context,
            )
        except SafetyReviewUnavailableError:
            metadata = _local_metadata(
                stage=context.stage,
                action=SafetyAction.BLOCK,
                risk_level=RiskLevel.HIGH,
                categories=[],
                reason_codes=["SAFETY_REVIEW_UNAVAILABLE"],
            )
            _audit_safety_decision(
                metadata=metadata,
                started_at=started_at,
                request_id=request_id,
                session_tag=session_tag,
                redacted=False,
                regenerated=False,
                blocked=True,
            )
            raise

    async def gate_request(
        self,
        text: str,
        *,
        intent: str | None = None,
        subject_category: str = "other",
        generation_profile_id: str | None = None,
        request_id: str = "",
        session_tag: str = "",
    ) -> SafeRequestResult:
        started_at = time.perf_counter()
        deterministic = evaluate_request(text)
        if deterministic.action == SafetyAction.BLOCK:
            _audit_safety_decision(
                metadata=deterministic.metadata,
                started_at=started_at,
                request_id=request_id,
                session_tag=session_tag,
                redacted=False,
                regenerated=False,
                blocked=True,
            )
            if deterministic.public_error_code == "CONTENT_SECRET_DETECTED":
                raise ContentSecretDetectedError()
            raise ContentSafetyInputBlockedError()
        safe_reviewer_intent = _safe_reviewer_intent(
            intent or deterministic.safe_text,
            "学习请求",
        )
        reviewed = await self._review_with_unavailable_audit(
            candidate=deterministic.safe_text,
            generation_profile_id=generation_profile_id,
            context=ReviewContext(
                stage=SafetyStage.REQUEST,
                intent=safe_reviewer_intent,
                subject_category=subject_category or "other",
                audience="student",
            ),
            started_at=started_at,
            request_id=request_id,
            session_tag=session_tag,
        )
        if reviewed.metadata.decision not in {SafetyAction.ALLOW, SafetyAction.REDACT}:
            _audit_safety_decision(
                metadata=reviewed.metadata,
                started_at=started_at,
                request_id=request_id,
                session_tag=session_tag,
                redacted=False,
                regenerated=reviewed.metadata.decision == SafetyAction.REGENERATE,
                blocked=True,
            )
            raise ContentSafetyInputBlockedError()
        if (
            reviewed.metadata.decision == SafetyAction.REDACT
            and deterministic.action != SafetyAction.REDACT
        ):
            _audit_safety_decision(
                metadata=reviewed.metadata,
                started_at=started_at,
                request_id=request_id,
                session_tag=session_tag,
                redacted=False,
                regenerated=False,
                blocked=True,
            )
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
        _audit_safety_decision(
            metadata=metadata,
            started_at=started_at,
            request_id=request_id,
            session_tag=session_tag,
            redacted=metadata.decision == SafetyAction.REDACT,
            regenerated=False,
            blocked=False,
        )
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
        request_id: str = "",
        session_tag: str = "",
    ) -> SafetyMetadata:
        started_at = time.perf_counter()
        structural = detect_structures(plan_text)
        if structural.blocking:
            metadata = _local_metadata(
                stage=SafetyStage.PLAN,
                action=SafetyAction.BLOCK,
                risk_level=structural.risk_level,
                categories=structural.categories,
                reason_codes=structural.reason_codes,
            )
            _audit_safety_decision(
                metadata=metadata,
                started_at=started_at,
                request_id=request_id,
                session_tag=session_tag,
                redacted=False,
                regenerated=False,
                blocked=True,
            )
            raise ContentArtifactBlockedError()
        reviewed = await self._review_with_unavailable_audit(
            candidate=plan_text,
            generation_profile_id=generation_profile_id,
            context=ReviewContext(
                stage=SafetyStage.PLAN,
                intent=_safe_reviewer_intent(intent, "学习资源规划"),
                subject_category=subject_category or "other",
                audience="student",
            ),
            started_at=started_at,
            request_id=request_id,
            session_tag=session_tag,
        )
        if reviewed.metadata.decision != SafetyAction.ALLOW:
            _audit_safety_decision(
                metadata=reviewed.metadata,
                started_at=started_at,
                request_id=request_id,
                session_tag=session_tag,
                redacted=False,
                regenerated=reviewed.metadata.decision == SafetyAction.REGENERATE,
                blocked=True,
            )
            raise ContentArtifactBlockedError()
        _audit_safety_decision(
            metadata=reviewed.metadata,
            started_at=started_at,
            request_id=request_id,
            session_tag=session_tag,
            redacted=False,
            regenerated=False,
            blocked=False,
        )
        return reviewed.metadata

    async def review_text(
        self,
        text: str,
        *,
        stage: SafetyStage = SafetyStage.ARTIFACT,
        intent: str,
        subject_category: str = "other",
        artifact_type: str | None = None,
        generation_profile_id: str | None = None,
        request_id: str = "",
        session_tag: str = "",
    ) -> SafeTextResult:
        started_at = time.perf_counter()
        structural = detect_structures(text)
        if structural.blocking:
            metadata = _local_metadata(
                stage=stage,
                action=SafetyAction.BLOCK,
                risk_level=structural.risk_level,
                categories=structural.categories,
                reason_codes=structural.reason_codes,
            )
            _audit_safety_decision(
                metadata=metadata,
                started_at=started_at,
                request_id=request_id,
                session_tag=session_tag,
                redacted=False,
                regenerated=False,
                blocked=True,
            )
            raise ContentArtifactBlockedError()
        redaction = redact_personal_data(text)
        reviewed = await self._review_with_unavailable_audit(
            candidate=redaction.text,
            generation_profile_id=generation_profile_id,
            context=ReviewContext(
                stage=stage,
                intent=_safe_reviewer_intent(intent, "学习内容"),
                subject_category=subject_category or "other",
                artifact_type=artifact_type,
                audience="student",
            ),
            started_at=started_at,
            request_id=request_id,
            session_tag=session_tag,
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
            _audit_safety_decision(
                metadata=metadata,
                started_at=started_at,
                request_id=request_id,
                session_tag=session_tag,
                redacted=redaction.changed,
                regenerated=False,
                blocked=False,
            )
            return SafeTextResult(safe_text=redaction.text, metadata=metadata)
        if metadata.decision == SafetyAction.REDACT and redaction.changed:
            _audit_safety_decision(
                metadata=metadata,
                started_at=started_at,
                request_id=request_id,
                session_tag=session_tag,
                redacted=True,
                regenerated=False,
                blocked=False,
            )
            return SafeTextResult(safe_text=redaction.text, metadata=metadata)
        _audit_safety_decision(
            metadata=metadata,
            started_at=started_at,
            request_id=request_id,
            session_tag=session_tag,
            redacted=False,
            regenerated=metadata.decision == SafetyAction.REGENERATE,
            blocked=True,
        )
        raise ContentArtifactBlockedError()

    async def review_artifact(
        self,
        artifact: ResourceArtifact,
        *,
        source_allowlist: set[str],
        intent: str,
        subject_category: str,
        generation_profile_id: str | None = None,
        request_id: str = "",
        session_tag: str = "",
    ) -> ArtifactSafetyResult:
        started_at = time.perf_counter()
        publishable_text = "\n".join([
            artifact.body,
            json.dumps(artifact.type_specific_data, ensure_ascii=False, sort_keys=True),
        ])
        structural = detect_structures(publishable_text)
        citations = validate_citations(publishable_text, allowed=source_allowlist)
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
            _audit_safety_decision(
                metadata=metadata,
                started_at=started_at,
                request_id=request_id,
                session_tag=session_tag,
                redacted=False,
                regenerated=True,
                blocked=False,
            )
            return ArtifactSafetyResult(
                action=SafetyAction.REGENERATE,
                metadata=metadata,
                reason_codes=metadata.reason_codes,
            )
        redaction = redact_personal_data(artifact.body)
        redaction_codes = list(redaction.reason_codes)
        safe_type_specific_data = _redact_publishable_value(
            artifact.type_specific_data,
            redaction_codes,
        )
        redaction_changed = (
            redaction.changed
            or safe_type_specific_data != artifact.type_specific_data
        )
        candidate = "\n".join([
            redaction.text,
            json.dumps(safe_type_specific_data, ensure_ascii=False, sort_keys=True),
        ])
        reviewed = await self._review_with_unavailable_audit(
            candidate=candidate,
            generation_profile_id=generation_profile_id,
            context=ReviewContext(
                stage=SafetyStage.ARTIFACT,
                intent=_safe_reviewer_intent(intent, "学习资源生成"),
                subject_category=subject_category or "other",
                artifact_type=artifact.type.value,
                audience="student",
            ),
            started_at=started_at,
            request_id=request_id,
            session_tag=session_tag,
        )
        metadata = reviewed.metadata
        if metadata.decision == SafetyAction.ALLOW:
            if redaction_changed:
                metadata = metadata.model_copy(update={
                    "decision": SafetyAction.REDACT,
                    "risk_level": RiskLevel.MEDIUM,
                    "categories": list(dict.fromkeys([
                        *metadata.categories,
                        RiskCategory.PERSONAL_DATA,
                    ])),
                    "reason_codes": list(dict.fromkeys([
                        *metadata.reason_codes,
                        *redaction_codes,
                    ])),
                })
            safe_artifact = artifact.model_copy(update={
                "body": redaction.text,
                "type_specific_data": safe_type_specific_data,
                "safety": metadata,
            })
            _audit_safety_decision(
                metadata=metadata,
                started_at=started_at,
                request_id=request_id,
                session_tag=session_tag,
                redacted=redaction_changed,
                regenerated=False,
                blocked=False,
            )
            return ArtifactSafetyResult(
                action=metadata.decision,
                artifact=safe_artifact,
                metadata=metadata,
                reason_codes=metadata.reason_codes,
            )
        if metadata.decision == SafetyAction.REDACT and redaction_changed:
            safe_artifact = artifact.model_copy(update={
                "body": redaction.text,
                "type_specific_data": safe_type_specific_data,
                "safety": metadata,
            })
            _audit_safety_decision(
                metadata=metadata,
                started_at=started_at,
                request_id=request_id,
                session_tag=session_tag,
                redacted=True,
                regenerated=False,
                blocked=False,
            )
            return ArtifactSafetyResult(
                action=SafetyAction.REDACT,
                artifact=safe_artifact,
                metadata=metadata,
                reason_codes=metadata.reason_codes,
            )
        _audit_safety_decision(
            metadata=metadata,
            started_at=started_at,
            request_id=request_id,
            session_tag=session_tag,
            redacted=False,
            regenerated=metadata.decision == SafetyAction.REGENERATE,
            blocked=metadata.decision == SafetyAction.BLOCK,
        )
        return ArtifactSafetyResult(
            action=metadata.decision,
            metadata=metadata,
            reason_codes=metadata.reason_codes,
        )


content_safety_service = ContentSafetyService()
