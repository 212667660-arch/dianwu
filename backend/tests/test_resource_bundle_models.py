from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.protocols.v2.models import (
    ArtifactStatus,
    ArtifactType,
    BundleStatus,
    ResourceArtifact,
    ResourceBrief,
    ResourceBundle,
    SubjectCategory,
)


class TestArtifactType:
    def test_valid_types(self):
        assert ArtifactType("course_explanation") == ArtifactType.COURSE_EXPLANATION
        assert ArtifactType("mind_map") == ArtifactType.MIND_MAP
        assert ArtifactType("question_bank") == ArtifactType.QUESTION_BANK
        assert ArtifactType("extended_reading") == ArtifactType.EXTENDED_READING
        assert ArtifactType("adaptive_practice") == ArtifactType.ADAPTIVE_PRACTICE

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError):
            ArtifactType("invalid_type")


class TestBundleStatus:
    def test_valid_statuses(self):
        assert BundleStatus("COMPLETED") == BundleStatus.COMPLETED
        assert BundleStatus("PARTIAL") == BundleStatus.PARTIAL
        assert BundleStatus("FAILED") == BundleStatus.FAILED
        assert BundleStatus("CANCELLED") == BundleStatus.CANCELLED


class TestResourceBrief:
    def test_valid_brief(self):
        brief = ResourceBrief(
            topic="一次函数",
            learning_objectives=["理解斜率概念", "掌握截距计算"],
            target_difficulty="基础",
            weak_knowledge_points=["函数图像", "待定系数法"],
            style_constraints="视觉型优先",
            source_allowlist=["资料1", "资料2"],
            subject_category=SubjectCategory.MATH,
        )
        assert brief.topic == "一次函数"
        assert len(brief.learning_objectives) >= 1

    def test_empty_topic_raises(self):
        with pytest.raises(ValidationError):
            ResourceBrief(
                topic="",
                learning_objectives=["目标"],
                target_difficulty="基础",
                weak_knowledge_points=[],
                style_constraints="",
                source_allowlist=[],
                subject_category=SubjectCategory.MATH,
            )

    def test_subject_category_values(self):
        valid = {"math", "physics", "chemistry", "biology", "cs", "literature",
                 "history", "geography", "english", "politics", "other"}
        for cat in valid:
            sc = SubjectCategory(cat)
            assert sc.value == cat


class TestResourceArtifact:
    def test_successful_artifact(self):
        artifact = ResourceArtifact(
            artifact_id="a1",
            type=ArtifactType.COURSE_EXPLANATION,
            title="一次函数课程讲解",
            status=ArtifactStatus.SUCCEEDED,
            body="## 学习目标\n...",
            quality_score=85,
            quality_issues=[],
        )
        assert artifact.status == ArtifactStatus.SUCCEEDED

    def test_failed_artifact(self):
        artifact = ResourceArtifact(
            artifact_id="a2",
            type=ArtifactType.MIND_MAP,
            title="思维导图",
            status=ArtifactStatus.FAILED,
            body="",
            quality_score=0,
            quality_issues=["MERMAID_INVALID"],
            error_code="SPECIALIST_FAILED",
            retryable=True,
        )
        assert artifact.retryable == True

    def test_artifact_type_specific_data(self):
        artifact = ResourceArtifact(
            artifact_id="a3",
            type=ArtifactType.COURSE_EXPLANATION,
            title="讲解",
            status=ArtifactStatus.SUCCEEDED,
            body="## 正文",
            quality_score=80,
            quality_issues=[],
            type_specific_data={
                "has_learning_objectives": True,
                "has_core_concepts": True,
                "has_explanation": True,
                "has_misconceptions": True,
                "has_personalized_advice": True,
            },
        )
        assert artifact.type_specific_data["has_learning_objectives"] is True

        qb = ResourceArtifact(
            artifact_id="a4",
            type=ArtifactType.QUESTION_BANK,
            title="题库",
            status=ArtifactStatus.SUCCEEDED,
            body="## 题目",
            quality_score=90,
            quality_issues=[],
            type_specific_data={
                "basic_count": 3,
                "intermediate_count": 2,
                "challenge_count": 1,
            },
        )
        assert qb.type_specific_data["basic_count"] == 3


class TestResourceBundle:
    def test_completed_bundle(self):
        artifacts = [
            ResourceArtifact(
                artifact_id=f"a{i}",
                type=t,
                title=f"资源{i}",
                status=ArtifactStatus.SUCCEEDED,
                body="内容",
                quality_score=80,
                quality_issues=[],
            )
            for i, t in enumerate(ArtifactType, start=1)
        ]
        bundle = ResourceBundle(
            bundle_id="b1",
            protocol_version="learning-resource-bundle/v2",
            topic="一次函数",
            profile_version=1,
            learning_state_version="abc",
            mode="bundle",
            status=BundleStatus.COMPLETED,
            requested_types=list(ArtifactType),
            artifacts=artifacts,
            aggregate_quality=82.0,
            created_at="2026-07-16T10:00:00Z",
        )
        assert bundle.status == BundleStatus.COMPLETED
        assert len(bundle.artifacts) == 5
        assert bundle.aggregate_quality == 82.0

    def test_partial_bundle(self):
        artifacts = [
            ResourceArtifact(
                artifact_id="a1",
                type=ArtifactType.COURSE_EXPLANATION,
                title="讲解",
                status=ArtifactStatus.SUCCEEDED,
                body="内容",
                quality_score=85,
                quality_issues=[],
            ),
            ResourceArtifact(
                artifact_id="a2",
                type=ArtifactType.MIND_MAP,
                title="导图",
                status=ArtifactStatus.FAILED,
                body="",
                quality_score=0,
                quality_issues=["MERMAID_PARSE_ERROR"],
                error_code="SPECIALIST_FAILED",
                retryable=True,
            ),
        ]
        bundle = ResourceBundle(
            bundle_id="b2",
            protocol_version="learning-resource-bundle/v2",
            topic="一次函数",
            profile_version=1,
            learning_state_version="abc",
            mode="single",
            status=BundleStatus.PARTIAL,
            requested_types=[ArtifactType.COURSE_EXPLANATION, ArtifactType.MIND_MAP],
            artifacts=artifacts,
            aggregate_quality=42.5,
            created_at="2026-07-16T10:00:00Z",
        )
        assert bundle.status == BundleStatus.PARTIAL
        assert len([a for a in bundle.artifacts if a.status == ArtifactStatus.SUCCEEDED]) == 1
        assert len([a for a in bundle.artifacts if a.status == ArtifactStatus.FAILED]) == 1

    def test_bundle_requires_non_empty_artifacts(self):
        with pytest.raises(ValidationError):
            ResourceBundle(
                bundle_id="b3",
                protocol_version="learning-resource-bundle/v2",
                topic="test",
                profile_version=1,
                learning_state_version="abc",
                mode="bundle",
                status=BundleStatus.FAILED,
                requested_types=[],
                artifacts=[],
                aggregate_quality=0.0,
                created_at="2026-07-16T10:00:00Z",
            )
