from __future__ import annotations

import json

from backend.protocols.v2.models import (
    ArtifactStatus, ArtifactType, BundleStatus, ResourceArtifact, ResourceBundle,
)
from backend.protocols.v2.sse_events import (
    artifact_event, bundle_event, plan_event, progress_event,
)


class TestSSEEventFormats:
    def test_plan_event_schema(self):
        payload = json.loads(plan_event("b1", "主题", ["course_explanation"]))
        assert payload["event"] == "resource_plan"
        assert payload["bundle_id"] == "b1"
        assert "requested_types" in payload

    def test_progress_event_schema(self):
        payload = json.loads(progress_event("mind_map", 2, 5))
        assert payload["event"] == "resource_progress"
        assert payload["completed_count"] == 2
        assert payload["total_count"] == 5

    def test_artifact_event_schema(self):
        artifact = ResourceArtifact(
            artifact_id="a1", type=ArtifactType.COURSE_EXPLANATION,
            title="讲解", status=ArtifactStatus.SUCCEEDED,
            body="内容", quality_score=85, quality_issues=[],
        )
        payload = json.loads(artifact_event(artifact))
        assert payload["event"] == "resource_artifact"
        assert payload["type"] == "course_explanation"

    def test_bundle_event_schema(self):
        bundle = ResourceBundle(
            bundle_id="b1", protocol_version="learning-resource-bundle/v2",
            topic="主题", profile_version=1, learning_state_version="v1",
            mode="bundle", status=BundleStatus.COMPLETED,
            requested_types=[ArtifactType.COURSE_EXPLANATION],
            artifacts=[ResourceArtifact(artifact_id="a1", type=ArtifactType.COURSE_EXPLANATION,
                       title="讲解", status=ArtifactStatus.SUCCEEDED, body="内容",
                       quality_score=80, quality_issues=[])],
            aggregate_quality=80.0, created_at="2026-07-16T10:00:00Z",
        )
        payload = json.loads(bundle_event(bundle))
        assert payload["event"] == "resource_bundle"
        assert payload["status"] == "COMPLETED"
