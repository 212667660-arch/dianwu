from __future__ import annotations

import asyncio
import inspect
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.errors import AppError, SafetyReviewUnavailableError
from backend.protocols.v2.models import (
    ArtifactStatus, ArtifactType, BundleStatus, ResourceArtifact, ResourceBundle,
)
from backend.services.content_safety.models import (
    RiskLevel,
    SafetyAction,
    SafetyMetadata,
    SafetyStage,
)
from backend.services.content_safety.prompt_boundary import untrusted_json_block
from backend.services.content_safety.reviewer import ReviewContext
from backend.services.resource_bundle.aggregator import aggregate_bundle
from backend.services.resource_bundle.answer_reviewer import AnswerReviewerAgent
from backend.services.resource_bundle.cancel import (
    cleanup_cancellation, get_or_create_cancellation,
)
from backend.services.resource_bundle.planner import (
    build_planner_messages, derive_requested_types, parse_plan_output,
)
from backend.services.resource_bundle.specialists.base import SpecialistResult, specialist_for_type

logger = logging.getLogger(__name__)
_MAX_CONCURRENT = 2


class BundleCancelled(Exception):
    pass


@dataclass
class PipelineResult:
    bundle: ResourceBundle
    plan_raw: str = ""
    error: str | None = None


@dataclass(frozen=True)
class CompletionOutput:
    text: str
    profile_id: str | None = None


def _make_failed_bundle(
    bundle_id: str, profile_version: int, learning_state_version: str,
    mode: str, requested_types: list[ArtifactType], topic: str = "规划失败",
    knowledge_sources: list[dict[str, object]] | None = None,
    public_sources: list[dict[str, object]] | None = None,
    error_code: str = "PLAN_FAILED",
) -> ResourceBundle:
    return ResourceBundle(
        bundle_id=bundle_id,
        topic=topic,
        profile_version=profile_version,
        learning_state_version=learning_state_version,
        mode=mode,
        status=BundleStatus.FAILED,
        requested_types=requested_types,
        artifacts=[
            ResourceArtifact(
                artifact_id=f"{bundle_id}-{artifact_type.value}",
                type=artifact_type,
                title="规划失败",
                status=ArtifactStatus.FAILED,
                error_code=error_code,
                quality_score=0,
                quality_issues=[error_code],
                retryable=error_code == "SAFETY_REVIEW_UNAVAILABLE",
            )
            for artifact_type in requested_types
        ],
        aggregate_quality=0.0,
        created_at=datetime.now(timezone.utc).isoformat(),
        knowledge_sources=knowledge_sources or [],
        public_sources=public_sources or [],
    )


def _cancelled_artifact(bundle_id: str, artifact_type: ArtifactType) -> ResourceArtifact:
    return ResourceArtifact(
        artifact_id=f"{bundle_id}-{artifact_type.value}",
        type=artifact_type,
        title=artifact_type.value,
        status=ArtifactStatus.CANCELLED,
        body="",
        quality_score=0,
        quality_issues=["CANCELLED"],
        error_code="CANCELLED",
        retryable=True,
    )


def _blocked_artifact(
    bundle_id: str,
    artifact_type: ArtifactType,
    *,
    metadata: SafetyMetadata | None,
    error_code: str = "CONTENT_ARTIFACT_BLOCKED",
    reason_codes: list[str] | None = None,
) -> ResourceArtifact:
    return ResourceArtifact(
        artifact_id=f"{bundle_id}-{artifact_type.value}",
        type=artifact_type,
        title=artifact_type.value,
        status=ArtifactStatus.FAILED,
        body="",
        quality_score=0,
        quality_issues=list(reason_codes or [error_code]),
        error_code=error_code,
        retryable=True,
        safety=metadata,
    )


def _review_unavailable_metadata() -> SafetyMetadata:
    return SafetyMetadata(
        stage=SafetyStage.ARTIFACT,
        decision=SafetyAction.BLOCK,
        risk_level=RiskLevel.HIGH,
        reason_codes=["SAFETY_REVIEW_UNAVAILABLE"],
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


async def _emit(on_event, event: dict[str, object]) -> None:
    if on_event is None:
        return
    result = on_event(event)
    if inspect.isawaitable(result):
        await result


async def _complete_or_cancel(gateway, messages, temperature, cancellation) -> CompletionOutput:
    if cancellation.is_cancelled():
        raise BundleCancelled()

    async def _complete():
        return await gateway.complete(messages, temperature=temperature)

    model_task = asyncio.create_task(_complete())
    cancel_task = asyncio.create_task(cancellation.event.wait())
    try:
        done, _ = await asyncio.wait(
            {model_task, cancel_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_task in done:
            model_task.cancel()
            with suppress(asyncio.CancelledError):
                await model_task
            raise BundleCancelled()
        value = await model_task
        if isinstance(value, str):
            return CompletionOutput(text=value)
        text = getattr(value, "text", None)
        if not isinstance(text, str):
            return CompletionOutput(text=str(value))
        return CompletionOutput(
            text=text,
            profile_id=getattr(value, "profile_id", None),
        )
    finally:
        cancel_task.cancel()
        with suppress(asyncio.CancelledError):
            await cancel_task


class BundlePipeline:
    def __init__(self, gateway: Any, *, safety_service: Any | None = None, answer_reviewer: Any | None = None) -> None:
        self._gateway = gateway
        self._safety_service = safety_service
        self._answer_reviewer = answer_reviewer or AnswerReviewerAgent()

    async def run(
        self, bundle_id: str, mode: str, single_type: ArtifactType | None,
        profile_text: str, learning_context: str, knowledge_context: str,
        user_request: str, source_allowlist: list[str], subject_category_hint: str,
        profile_version: int, learning_state_version: str,
        knowledge_sources: list[dict[str, object]] | None = None,
        public_sources: list[dict[str, object]] | None = None,
        audit_session_tag: str = "",
        evidence_status: str = "unavailable",
        knowledge_scope: dict[str, object] | None = None,
        recovery_actions: list[str] | None = None,
        on_event=None,
    ) -> PipelineResult:
        cancellation = get_or_create_cancellation(bundle_id)
        requested_types = derive_requested_types(mode, single_type)
        try:
            plan_messages = build_planner_messages(
                profile_text, learning_context, knowledge_context,
                user_request, source_allowlist, subject_category_hint,
            )
            try:
                plan_completion = await _complete_or_cancel(
                    self._gateway, plan_messages, 0.3, cancellation,
                )
                plan_raw = plan_completion.text
                brief = parse_plan_output(plan_raw, source_allowlist=source_allowlist)
                if self._safety_service is not None:
                    await self._safety_service.review_plan(
                        plan_raw,
                        intent=user_request,
                        subject_category=brief.subject_category.value,
                        generation_profile_id=plan_completion.profile_id,
                        request_id=bundle_id,
                        session_tag=audit_session_tag or bundle_id,
                    )
            except BundleCancelled:
                artifacts = [_cancelled_artifact(bundle_id, item) for item in requested_types]
                bundle = aggregate_bundle(
                    bundle_id, "已取消", profile_version, learning_state_version,
                    mode, requested_types, artifacts, True,
                    knowledge_sources, public_sources,
                )
                await _emit(on_event, {"event": "resource_bundle", **bundle.model_dump(mode="json")})
                return PipelineResult(bundle=bundle)
            except AppError as exc:
                logger.warning("Resource plan safety failed: %s", exc.code)
                bundle = _make_failed_bundle(
                    bundle_id, profile_version, learning_state_version, mode, requested_types,
                    knowledge_sources=knowledge_sources,
                    public_sources=public_sources,
                    error_code=exc.code,
                )
                await _emit(on_event, {"event": "resource_bundle", **bundle.model_dump(mode="json")})
                return PipelineResult(bundle=bundle, error=exc.code)
            except Exception as exc:
                logger.warning("Resource plan failed: %s", type(exc).__name__)
                bundle = _make_failed_bundle(
                    bundle_id, profile_version, learning_state_version, mode, requested_types,
                    knowledge_sources=knowledge_sources,
                    public_sources=public_sources,
                )
                await _emit(on_event, {"event": "resource_bundle", **bundle.model_dump(mode="json")})
                return PipelineResult(bundle=bundle, error="PLAN_FAILED")

            await _emit(on_event, {
                "event": "resource_plan",
                "bundle_id": bundle_id,
                "topic": brief.topic,
                "requested_types": [item.value for item in requested_types],
                "evidence_status": evidence_status,
                "knowledge_scope": knowledge_scope,
                "recovery_actions": recovery_actions or [],
            })

            semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
            counter_lock = asyncio.Lock()
            completed_count = 0

            async def _run_specialist(at: ArtifactType) -> SpecialistResult:
                nonlocal completed_count
                async with semaphore:
                    await _emit(on_event, {
                        "event": "resource_progress",
                        "current_type": at.value,
                        "completed_count": completed_count,
                        "total_count": len(requested_types),
                        "status": "GENERATING",
                    })
                    if cancellation.is_cancelled():
                        result = SpecialistResult(
                            artifact=_cancelled_artifact(bundle_id, at),
                            raw_output="",
                        )
                    else:
                        specialist = specialist_for_type(at)
                        messages = specialist.build_prompt(
                            brief, profile_text, learning_context, knowledge_context,
                        )
                        try:
                            completion = await _complete_or_cancel(
                                self._gateway, messages, 0.4, cancellation,
                            )
                            result = specialist.parse(
                                completion.text,
                                f"{bundle_id}-{at.value}",
                                source_allowlist=tuple(brief.source_allowlist),
                                subject_category=brief.subject_category,
                            )
                            if (
                                result.artifact.status == ArtifactStatus.SUCCEEDED
                                and self._answer_reviewer.applies_to(at)
                            ):
                                await _emit(on_event, {
                                    "event": "answer_review",
                                    "artifact_type": at.value,
                                    "status": "STARTED",
                                })
                                verdict = self._answer_reviewer.review(
                                    result.artifact,
                                    source_allowlist=set(brief.source_allowlist),
                                    textbook_source_ids={
                                        str(item.get("reference_id"))
                                        for item in knowledge_sources or []
                                        if item.get("reference_id")
                                    },
                                    subject_category=brief.subject_category,
                                    require_textbook_sections=bool(knowledge_scope or knowledge_sources),
                                )
                                if verdict.approved:
                                    result = SpecialistResult(
                                        artifact=self._answer_reviewer.attach(
                                            result.artifact,
                                            verdict,
                                            status="PASSED",
                                            repair_attempted=False,
                                        ),
                                        raw_output=result.raw_output,
                                    )
                                    review_status = "PASSED"
                                else:
                                    repaired_completion = await _complete_or_cancel(
                                        self._gateway,
                                        self._answer_reviewer.repair_messages(messages, result.artifact, verdict),
                                        0.2,
                                        cancellation,
                                    )
                                    repaired = specialist.parse(
                                        repaired_completion.text,
                                        f"{bundle_id}-{at.value}",
                                        source_allowlist=tuple(brief.source_allowlist),
                                        subject_category=brief.subject_category,
                                    )
                                    repaired_verdict = (
                                        self._answer_reviewer.review(
                                            repaired.artifact,
                                            source_allowlist=set(brief.source_allowlist),
                                            textbook_source_ids={
                                                str(item.get("reference_id"))
                                                for item in knowledge_sources or []
                                                if item.get("reference_id")
                                            },
                                            subject_category=brief.subject_category,
                                            require_textbook_sections=bool(knowledge_scope or knowledge_sources),
                                        )
                                        if repaired.artifact.status == ArtifactStatus.SUCCEEDED
                                        else verdict
                                    )
                                    if repaired.artifact.status == ArtifactStatus.SUCCEEDED and repaired_verdict.approved:
                                        completion = repaired_completion
                                        result = SpecialistResult(
                                            artifact=self._answer_reviewer.attach(
                                                repaired.artifact,
                                                repaired_verdict,
                                                status="REPAIRED",
                                                repair_attempted=True,
                                            ),
                                            raw_output=repaired.raw_output,
                                        )
                                        review_status = "REPAIRED"
                                    else:
                                        result = SpecialistResult(
                                            artifact=self._answer_reviewer.attach(
                                                result.artifact,
                                                repaired_verdict,
                                                status="WARNING",
                                                repair_attempted=True,
                                                warning=True,
                                            ),
                                            raw_output=result.raw_output,
                                        )
                                        review_status = "WARNING"
                                await _emit(on_event, {
                                    "event": "answer_review",
                                    "artifact_type": at.value,
                                    "status": review_status,
                                    "issues": result.artifact.type_specific_data["answer_review"]["issues"],
                                })
                            if (
                                self._safety_service is not None
                                and result.artifact.status == ArtifactStatus.SUCCEEDED
                            ):
                                review = await self._safety_service.review_artifact(
                                    result.artifact,
                                    source_allowlist=set(brief.source_allowlist),
                                    intent=user_request,
                                    subject_category=brief.subject_category.value,
                                    generation_profile_id=completion.profile_id,
                                    request_id=bundle_id,
                                    session_tag=audit_session_tag or bundle_id,
                                )
                                if review.action in {SafetyAction.ALLOW, SafetyAction.REDACT}:
                                    result = SpecialistResult(
                                        artifact=review.artifact,
                                        raw_output="",
                                    )
                                elif review.action == SafetyAction.REGENERATE:
                                    regeneration = untrusted_json_block(
                                        "safety_regeneration",
                                        {"reason_codes": review.reason_codes},
                                        field_limit=128,
                                        total_limit=2_000,
                                    )
                                    regeneration_messages = [
                                        *messages,
                                        {
                                            "role": "user",
                                            "content": (
                                                f"{regeneration}\n"
                                                "上一版未通过安全检查。只依据原 resource_specialist_data 和上述受控原因码重新生成完整资源，不要复述或引用上一版内容。"
                                            ),
                                        },
                                    ]
                                    repaired_completion = await _complete_or_cancel(
                                        self._gateway,
                                        regeneration_messages,
                                        0.2,
                                        cancellation,
                                    )
                                    repaired = specialist.parse(
                                        repaired_completion.text,
                                        f"{bundle_id}-{at.value}",
                                        source_allowlist=tuple(brief.source_allowlist),
                                        subject_category=brief.subject_category,
                                    )
                                    if repaired.artifact.status == ArtifactStatus.SUCCEEDED:
                                        second_review = await self._safety_service.review_artifact(
                                            repaired.artifact,
                                            source_allowlist=set(brief.source_allowlist),
                                            intent=user_request,
                                            subject_category=brief.subject_category.value,
                                            generation_profile_id=repaired_completion.profile_id,
                                            request_id=bundle_id,
                                            session_tag=audit_session_tag or bundle_id,
                                        )
                                    else:
                                        second_review = None
                                    if (
                                        second_review is not None
                                        and second_review.action in {SafetyAction.ALLOW, SafetyAction.REDACT}
                                    ):
                                        result = SpecialistResult(
                                            artifact=second_review.artifact,
                                            raw_output="",
                                        )
                                    else:
                                        metadata = (
                                            second_review.metadata
                                            if second_review is not None
                                            else review.metadata
                                        )
                                        reasons = list(dict.fromkeys([
                                            *review.reason_codes,
                                            *(second_review.reason_codes if second_review is not None else []),
                                        ]))
                                        result = SpecialistResult(
                                            artifact=_blocked_artifact(
                                                bundle_id,
                                                at,
                                                metadata=metadata,
                                                reason_codes=reasons,
                                            ),
                                            raw_output="",
                                        )
                                else:
                                    result = SpecialistResult(
                                        artifact=_blocked_artifact(
                                            bundle_id,
                                            at,
                                            metadata=review.metadata,
                                            reason_codes=review.reason_codes,
                                        ),
                                        raw_output="",
                                    )
                        except BundleCancelled:
                            result = SpecialistResult(
                                artifact=_cancelled_artifact(bundle_id, at),
                                raw_output="",
                            )
                        except SafetyReviewUnavailableError:
                            result = SpecialistResult(
                                artifact=_blocked_artifact(
                                    bundle_id,
                                    at,
                                    metadata=_review_unavailable_metadata(),
                                    error_code="SAFETY_REVIEW_UNAVAILABLE",
                                    reason_codes=["SAFETY_REVIEW_UNAVAILABLE"],
                                ),
                                raw_output="",
                            )
                        except Exception as exc:
                            logger.warning(
                                "Specialist %s failed with %s",
                                at.value,
                                type(exc).__name__,
                            )
                            result = SpecialistResult(
                                artifact=ResourceArtifact(
                                    artifact_id=f"{bundle_id}-{at.value}",
                                    type=at,
                                    title=at.value,
                                    status=ArtifactStatus.FAILED,
                                    body="",
                                    quality_score=0,
                                    quality_issues=["SPECIALIST_FAILED"],
                                    error_code="SPECIALIST_FAILED",
                                    retryable=True,
                                ),
                                raw_output="",
                            )

                    async with counter_lock:
                        completed_count += 1
                        await _emit(on_event, {
                            "event": "resource_artifact",
                            **result.artifact.model_dump(mode="json"),
                        })
                        await _emit(on_event, {
                            "event": "resource_progress",
                            "current_type": at.value,
                            "completed_count": completed_count,
                            "total_count": len(requested_types),
                            "status": result.artifact.status.value,
                        })
                    return result

            results = await asyncio.gather(*[_run_specialist(item) for item in requested_types])
            artifacts = [result.artifact for result in results]
            bundle = aggregate_bundle(
                bundle_id, brief.topic, profile_version, learning_state_version,
                mode, requested_types, artifacts, cancellation.is_cancelled(),
                knowledge_sources, public_sources,
            )
            await _emit(on_event, {"event": "resource_bundle", **bundle.model_dump(mode="json")})
            return PipelineResult(bundle=bundle, plan_raw=plan_raw)
        finally:
            cleanup_cancellation(bundle_id)
