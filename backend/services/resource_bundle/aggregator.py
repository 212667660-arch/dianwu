from __future__ import annotations

from datetime import datetime, timezone

from backend.protocols.v2.models import (
    ArtifactStatus, ArtifactType, BundleStatus, ResourceArtifact, ResourceBundle,
)

_CATALOG_ORDER: dict[ArtifactType, int] = {
    ArtifactType.COURSE_EXPLANATION: 0,
    ArtifactType.MIND_MAP: 1,
    ArtifactType.QUESTION_BANK: 2,
    ArtifactType.EXTENDED_READING: 3,
    ArtifactType.ADAPTIVE_PRACTICE: 4,
}


def compute_bundle_status(total: int, succeeded: int, failed: int, is_cancelled: bool) -> BundleStatus:
    if is_cancelled:
        return BundleStatus.CANCELLED
    if succeeded == total:
        return BundleStatus.COMPLETED
    if succeeded > 0:
        return BundleStatus.PARTIAL
    return BundleStatus.FAILED


def aggregate_bundle(
    bundle_id: str, topic: str, profile_version: int, learning_state_version: str,
    mode: str, requested_types: list[ArtifactType], artifacts: list[ResourceArtifact],
    is_cancelled: bool, knowledge_sources: list[dict] | None = None,
    public_sources: list[dict] | None = None,
) -> ResourceBundle:
    sorted_artifacts = sorted(artifacts, key=lambda a: _CATALOG_ORDER.get(a.type, 99))
    succeeded = sum(1 for a in sorted_artifacts if a.status == ArtifactStatus.SUCCEEDED)
    failed = sum(1 for a in sorted_artifacts if a.status == ArtifactStatus.FAILED)
    total = len(sorted_artifacts)
    status = compute_bundle_status(total, succeeded, failed, is_cancelled)
    scores = [a.quality_score for a in sorted_artifacts]
    aggregate_quality = round(sum(scores) / len(scores), 1) if scores else 0.0

    return ResourceBundle(
        bundle_id=bundle_id, protocol_version="learning-resource-bundle/v2",
        topic=topic, profile_version=profile_version,
        learning_state_version=learning_state_version, mode=mode,
        status=status, requested_types=requested_types,
        artifacts=sorted_artifacts, aggregate_quality=aggregate_quality,
        created_at=datetime.now(timezone.utc).isoformat(),
        knowledge_sources=knowledge_sources or [],
        public_sources=public_sources or [],
    )
