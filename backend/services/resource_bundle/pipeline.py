from __future__ import annotations

import asyncio
import inspect
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.protocols.v2.models import (
    ArtifactStatus, ArtifactType, BundleStatus, ResourceArtifact, ResourceBundle,
)
from backend.services.resource_bundle.aggregator import aggregate_bundle
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


def _make_failed_bundle(
    bundle_id: str, profile_version: int, learning_state_version: str,
    mode: str, requested_types: list[ArtifactType], topic: str = "规划失败",
    knowledge_sources: list[dict[str, object]] | None = None,
    public_sources: list[dict[str, object]] | None = None,
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
                error_code="PLAN_FAILED",
                quality_score=0,
                quality_issues=["PLAN_FAILED"],
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


async def _emit(on_event, event: dict[str, object]) -> None:
    if on_event is None:
        return
    result = on_event(event)
    if inspect.isawaitable(result):
        await result


async def _complete_or_cancel(gateway, messages, temperature, cancellation) -> str:
    if cancellation.is_cancelled():
        raise BundleCancelled()
    model_task = asyncio.create_task(gateway.complete(messages, temperature=temperature))
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
        return await model_task
    finally:
        cancel_task.cancel()
        with suppress(asyncio.CancelledError):
            await cancel_task


class BundlePipeline:
    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    async def run(
        self, bundle_id: str, mode: str, single_type: ArtifactType | None,
        profile_text: str, learning_context: str, knowledge_context: str,
        user_request: str, source_allowlist: list[str], subject_category_hint: str,
        profile_version: int, learning_state_version: str,
        knowledge_sources: list[dict[str, object]] | None = None,
        public_sources: list[dict[str, object]] | None = None,
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
                plan_raw = await _complete_or_cancel(
                    self._gateway, plan_messages, 0.3, cancellation,
                )
                brief = parse_plan_output(plan_raw, source_allowlist=source_allowlist)
            except BundleCancelled:
                artifacts = [_cancelled_artifact(bundle_id, item) for item in requested_types]
                bundle = aggregate_bundle(
                    bundle_id, "已取消", profile_version, learning_state_version,
                    mode, requested_types, artifacts, True,
                    knowledge_sources, public_sources,
                )
                await _emit(on_event, {"event": "resource_bundle", **bundle.model_dump(mode="json")})
                return PipelineResult(bundle=bundle)
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
                            raw = await _complete_or_cancel(
                                self._gateway, messages, 0.4, cancellation,
                            )
                            result = specialist.parse(
                                raw,
                                f"{bundle_id}-{at.value}",
                                source_allowlist=tuple(brief.source_allowlist),
                                subject_category=brief.subject_category,
                            )
                        except BundleCancelled:
                            result = SpecialistResult(
                                artifact=_cancelled_artifact(bundle_id, at),
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
