from __future__ import annotations

import asyncio
import logging
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


@dataclass
class PipelineResult:
    bundle: ResourceBundle
    plan_raw: str = ""
    error: str | None = None


def _make_failed_bundle(
    bundle_id: str, profile_version: int, learning_state_version: str,
    mode: str, requested_types: list[ArtifactType], topic: str = "规划失败",
) -> ResourceBundle:
    return ResourceBundle(
        bundle_id=bundle_id,
        topic=topic,
        profile_version=profile_version,
        learning_state_version=learning_state_version,
        mode=mode,
        status=BundleStatus.FAILED,
        requested_types=requested_types,
        artifacts=[ResourceArtifact(
            artifact_id=f"{bundle_id}-placeholder",
            type=requested_types[0] if requested_types else ArtifactType.COURSE_EXPLANATION,
            title="规划失败",
            status=ArtifactStatus.FAILED,
            error_code="PLAN_FAILED",
            quality_score=0,
        )],
        aggregate_quality=0.0,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


class BundlePipeline:
    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    async def run(
        self, bundle_id: str, mode: str, single_type: ArtifactType | None,
        profile_text: str, learning_context: str, knowledge_context: str,
        user_request: str, source_allowlist: list[str], subject_category_hint: str,
        profile_version: int, learning_state_version: str,
    ) -> PipelineResult:
        cancellation = get_or_create_cancellation(bundle_id)
        requested_types = derive_requested_types(mode, single_type)

        # Phase 1: Planning
        plan_messages = build_planner_messages(
            profile_text, learning_context, knowledge_context,
            user_request, source_allowlist, subject_category_hint,
        )
        try:
            plan_raw = await self._gateway.complete(plan_messages, temperature=0.3)
            brief = parse_plan_output(plan_raw, source_allowlist=source_allowlist)
        except Exception as exc:
            cleanup_cancellation(bundle_id)
            return PipelineResult(
                bundle=_make_failed_bundle(bundle_id, profile_version,
                    learning_state_version, mode, requested_types),
                error=f"Planning failed: {exc}",
            )

        if cancellation.is_cancelled():
            cleanup_cancellation(bundle_id)
            return PipelineResult(
                bundle=aggregate_bundle(bundle_id, brief.topic, profile_version,
                    learning_state_version, mode, requested_types, [], True),
            )

        # Phase 2: Specialist execution with semaphore
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

        async def _run_specialist(at: ArtifactType) -> SpecialistResult:
            async with semaphore:
                if cancellation.is_cancelled():
                    return SpecialistResult(
                        artifact=ResourceArtifact(
                            artifact_id=f"{bundle_id}-{at.value}", type=at,
                            title=at.value, status=ArtifactStatus.CANCELLED, body="",
                            quality_score=0, quality_issues=["CANCELLED"],
                            error_code="CANCELLED", retryable=True,
                        ), raw_output="",
                    )
                specialist = specialist_for_type(at)
                messages = specialist.build_prompt(brief, profile_text, learning_context, knowledge_context)
                try:
                    raw = await self._gateway.complete(messages, temperature=0.4)
                    return specialist.parse(
                        raw,
                        f"{bundle_id}-{at.value}",
                        source_allowlist=tuple(brief.source_allowlist),
                        subject_category=brief.subject_category,
                    )
                except Exception as exc:
                    logger.warning("Specialist %s failed: %s", at.value, exc)
                    return SpecialistResult(
                        artifact=ResourceArtifact(
                            artifact_id=f"{bundle_id}-{at.value}", type=at,
                            title=at.value, status=ArtifactStatus.FAILED, body="",
                            quality_score=0, quality_issues=[str(exc)],
                            error_code="SPECIALIST_FAILED", retryable=True,
                        ), raw_output="",
                    )

        tasks = [_run_specialist(t) for t in requested_types]
        results = await asyncio.gather(*tasks)
        artifacts = [r.artifact for r in results]
        was_cancelled = cancellation.is_cancelled()

        bundle = aggregate_bundle(bundle_id, brief.topic, profile_version,
            learning_state_version, mode, requested_types, artifacts, was_cancelled)
        cleanup_cancellation(bundle_id)
        return PipelineResult(bundle=bundle, plan_raw=plan_raw)
