from __future__ import annotations

from backend.protocols.v2.models import (
    ArtifactStatus, ArtifactType, BundleStatus, ResourceArtifact, ResourceBundle,
)
from backend.services.resource_bundle.aggregator import aggregate_bundle, compute_bundle_status


def _make_artifact(artifact_type: ArtifactType, status: ArtifactStatus, score: int = 80) -> ResourceArtifact:
    return ResourceArtifact(
        artifact_id=f"a-{artifact_type.value}", type=artifact_type,
        title=f"资源：{artifact_type.value}", status=status,
        body="内容" if status == ArtifactStatus.SUCCEEDED else "",
        quality_score=score if status == ArtifactStatus.SUCCEEDED else 0,
        quality_issues=[] if status == ArtifactStatus.SUCCEEDED else ["FAILED"],
        error_code=None if status == ArtifactStatus.SUCCEEDED else "SPECIALIST_FAILED",
        retryable=status == ArtifactStatus.FAILED,
    )


class TestComputeBundleStatus:
    def test_all_succeeded_is_completed(self):
        assert compute_bundle_status(5, 5, 0, False) == BundleStatus.COMPLETED

    def test_mixed_is_partial(self):
        assert compute_bundle_status(5, 3, 2, False) == BundleStatus.PARTIAL

    def test_all_failed_is_failed(self):
        assert compute_bundle_status(5, 0, 5, False) == BundleStatus.FAILED

    def test_cancelled(self):
        assert compute_bundle_status(5, 2, 1, True) == BundleStatus.CANCELLED


class TestAggregateBundle:
    def test_completed_bundle(self):
        artifacts = [
            _make_artifact(ArtifactType.COURSE_EXPLANATION, ArtifactStatus.SUCCEEDED, 85),
            _make_artifact(ArtifactType.MIND_MAP, ArtifactStatus.SUCCEEDED, 90),
            _make_artifact(ArtifactType.QUESTION_BANK, ArtifactStatus.SUCCEEDED, 80),
            _make_artifact(ArtifactType.EXTENDED_READING, ArtifactStatus.SUCCEEDED, 75),
            _make_artifact(ArtifactType.ADAPTIVE_PRACTICE, ArtifactStatus.SUCCEEDED, 85),
        ]
        bundle = aggregate_bundle("b-test", "一次函数", 1, "v1", "bundle",
                                  list(ArtifactType), artifacts, False)
        assert bundle.status == BundleStatus.COMPLETED
        assert bundle.aggregate_quality == 83.0
        assert len(bundle.artifacts) == 5

    def test_partial_bundle_quality_avg(self):
        artifacts = [
            _make_artifact(ArtifactType.COURSE_EXPLANATION, ArtifactStatus.SUCCEEDED, 80),
            _make_artifact(ArtifactType.MIND_MAP, ArtifactStatus.FAILED, 0),
        ]
        bundle = aggregate_bundle("b-partial", "test", 1, "v1", "bundle",
                                  [ArtifactType.COURSE_EXPLANATION, ArtifactType.MIND_MAP],
                                  artifacts, False)
        assert bundle.status == BundleStatus.PARTIAL
        assert bundle.aggregate_quality == 40.0

    def test_artifact_ordering(self):
        artifacts = [
            _make_artifact(ArtifactType.QUESTION_BANK, ArtifactStatus.SUCCEEDED),
            _make_artifact(ArtifactType.COURSE_EXPLANATION, ArtifactStatus.SUCCEEDED),
            _make_artifact(ArtifactType.MIND_MAP, ArtifactStatus.SUCCEEDED),
        ]
        bundle = aggregate_bundle("b-order", "test", 1, "v1", "bundle",
                                  [ArtifactType.COURSE_EXPLANATION, ArtifactType.MIND_MAP,
                                   ArtifactType.QUESTION_BANK],
                                  artifacts, False)
        ordered = [a.type for a in bundle.artifacts]
        assert ordered[0] == ArtifactType.COURSE_EXPLANATION
        assert ordered[1] == ArtifactType.MIND_MAP
        assert ordered[2] == ArtifactType.QUESTION_BANK
