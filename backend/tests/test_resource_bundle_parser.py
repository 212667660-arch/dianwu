from __future__ import annotations

import json

import pytest

from backend.errors import ProtocolValidationError
from backend.protocols.v2.models import (
    ArtifactStatus,
    ArtifactType,
    BundleStatus,
    ResourceArtifact,
    ResourceBundle,
)
from backend.protocols.v2.parser import (
    bundle_to_json,
    bundle_to_sse_payload,
    parse_bundle_from_json,
    validate_bundle,
)


class TestBundleJsonRoundTrip:
    def test_full_bundle_round_trip(self):
        original = ResourceBundle(
            bundle_id="b-test",
            protocol_version="learning-resource-bundle/v2",
            topic="一次函数",
            profile_version=2,
            learning_state_version="v1",
            mode="bundle",
            status=BundleStatus.COMPLETED,
            requested_types=[ArtifactType.COURSE_EXPLANATION, ArtifactType.MIND_MAP],
            artifacts=[
                ResourceArtifact(
                    artifact_id="a-1",
                    type=ArtifactType.COURSE_EXPLANATION,
                    title="课程讲解",
                    status=ArtifactStatus.SUCCEEDED,
                    body="## 正文\n内容",
                    quality_score=85,
                    quality_issues=[],
                ),
                ResourceArtifact(
                    artifact_id="a-2",
                    type=ArtifactType.MIND_MAP,
                    title="思维导图",
                    status=ArtifactStatus.SUCCEEDED,
                    body="flowchart TD\n  A-->B",
                    quality_score=90,
                    quality_issues=[],
                    type_specific_data={"mermaid_syntax": "flowchart", "outline": "- A\n  - B"},
                ),
            ],
            aggregate_quality=87.5,
            created_at="2026-07-16T10:00:00Z",
            knowledge_sources=[{"reference_id": "资料1", "document_name": "教材第一章"}],
            public_sources=[{"title": "百度百科", "url": "https://baike.baidu.com"}],
        )
        json_str = bundle_to_json(original)
        parsed = parse_bundle_from_json(json_str)
        assert parsed.bundle_id == original.bundle_id
        assert parsed.status == BundleStatus.COMPLETED
        assert len(parsed.artifacts) == 2
        assert parsed.artifacts[0].type == ArtifactType.COURSE_EXPLANATION
        assert parsed.mode == "bundle"

    def test_invalid_json_raises(self):
        with pytest.raises(ProtocolValidationError) as exc_info:
            parse_bundle_from_json("not json")
        assert exc_info.value.code == "BUNDLE_PARSE_ERROR"

    def test_missing_fields_raises(self):
        with pytest.raises(ProtocolValidationError):
            parse_bundle_from_json('{"bundle_id": "x"}')


class TestBundleValidation:
    def test_valid_bundle_passes(self):
        bundle = ResourceBundle(
            bundle_id="b1", protocol_version="learning-resource-bundle/v2",
            topic="test", profile_version=1, learning_state_version="v1",
            mode="bundle", status=BundleStatus.COMPLETED,
            requested_types=[ArtifactType.COURSE_EXPLANATION],
            artifacts=[ResourceArtifact(artifact_id="a1", type=ArtifactType.COURSE_EXPLANATION,
                       title="讲解", status=ArtifactStatus.SUCCEEDED, body="内容",
                       quality_score=80, quality_issues=[])],
            aggregate_quality=80.0, created_at="2026-07-16T10:00:00Z",
        )
        validate_bundle(bundle)  # should not raise

    def test_bundle_missing_requested_type(self):
        bundle = ResourceBundle(
            bundle_id="b1", protocol_version="learning-resource-bundle/v2",
            topic="test", profile_version=1, learning_state_version="v1",
            mode="bundle", status=BundleStatus.COMPLETED,
            requested_types=[ArtifactType.COURSE_EXPLANATION, ArtifactType.MIND_MAP],
            artifacts=[ResourceArtifact(artifact_id="a1", type=ArtifactType.COURSE_EXPLANATION,
                       title="讲解", status=ArtifactStatus.SUCCEEDED, body="内容",
                       quality_score=80, quality_issues=[])],
            aggregate_quality=80.0, created_at="2026-07-16T10:00:00Z",
        )
        with pytest.raises(ProtocolValidationError):
            validate_bundle(bundle)


class TestSSEPayload:
    def test_bundle_event_payload(self):
        bundle = ResourceBundle(
            bundle_id="b1", protocol_version="learning-resource-bundle/v2",
            topic="test", profile_version=1, learning_state_version="v1",
            mode="single", status=BundleStatus.COMPLETED,
            requested_types=[ArtifactType.COURSE_EXPLANATION],
            artifacts=[ResourceArtifact(artifact_id="a1", type=ArtifactType.COURSE_EXPLANATION,
                       title="讲解", status=ArtifactStatus.SUCCEEDED, body="内容",
                       quality_score=80, quality_issues=[])],
            aggregate_quality=80.0, created_at="2026-07-16T10:00:00Z",
        )
        payload = bundle_to_sse_payload(bundle)
        data = json.loads(payload)
        assert data["protocol_version"] == "learning-resource-bundle/v2"
        assert data["status"] == "COMPLETED"

    def test_plan_event_payload(self):
        from backend.protocols.v2.sse_events import plan_event
        payload = plan_event("b1", "一次函数", ["course_explanation", "mind_map"])
        data = json.loads(payload)
        assert data["event"] == "resource_plan"
        assert data["topic"] == "一次函数"
        assert len(data["requested_types"]) == 2

    def test_progress_event_payload(self):
        from backend.protocols.v2.sse_events import progress_event
        payload = progress_event("course_explanation", 2, 5, "GENERATING")
        data = json.loads(payload)
        assert data["event"] == "resource_progress"
        assert data["current_type"] == "course_explanation"
        assert data["completed_count"] == 2

    def test_artifact_event_payload(self):
        from backend.protocols.v2.sse_events import artifact_event
        artifact = ResourceArtifact(
            artifact_id="a1", type=ArtifactType.MIND_MAP, title="导图",
            status=ArtifactStatus.SUCCEEDED, body="flowchart TD\n  A-->B",
            quality_score=90, quality_issues=[],
        )
        payload = artifact_event(artifact)
        data = json.loads(payload)
        assert data["event"] == "resource_artifact"
        assert data["type"] == "mind_map"
