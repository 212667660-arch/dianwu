from __future__ import annotations

import pytest

from backend.errors import ProtocolValidationError
from backend.protocols.v2.models import ArtifactType, ResourceBrief, SubjectCategory
from backend.services.resource_bundle.planner import (
    build_planner_messages,
    parse_plan_output,
    validate_brief,
    derive_requested_types,
)


class TestBuildPlannerMessages:
    def test_messages_contain_profile_and_progress(self):
        messages = build_planner_messages(
            profile_text="已验画像：初中数学 基础",
            learning_context="知识点1: 薄弱",
            knowledge_context="资料1: 教材",
            user_request="请生成一次函数资源",
            source_allowlist=["资料1"],
            subject_category_hint="math",
        )
        combined = " ".join(m["content"] for m in messages)
        assert "已验画像" in combined
        assert "知识点1" in combined
        assert "资料1" in combined
        assert "一次函数" in combined


class TestParsePlanOutput:
    def test_valid_brief_parsed(self):
        raw = """[协议 resource-plan/v2]
主题: 一次函数
学习目标: 理解斜率概念|掌握截距计算
目标难度: 基础
薄弱知识点: 函数图像|待定系数法
风格约束: 视觉型优先
来源白名单: 资料1|资料2
学科类别: math
[协议结束]"""
        brief = parse_plan_output(raw, source_allowlist=["资料1", "资料2"])
        assert brief.topic == "一次函数"
        assert brief.learning_objectives == ["理解斜率概念", "掌握截距计算"]
        assert brief.source_allowlist == ["资料1", "资料2"]
        assert brief.subject_category == SubjectCategory.MATH

    def test_empty_optional_lines_stay_empty(self):
        raw = """[协议 resource-plan/v2]
主题：一次函数
学习目标：理解斜率
目标难度：基础
薄弱知识点：
风格约束：
来源白名单：
学科类别：math
[协议结束]"""

        brief = parse_plan_output(raw, source_allowlist=["资料1"])

        assert brief.weak_knowledge_points == []
        assert brief.style_constraints == ""
        assert brief.source_allowlist == []

    def test_model_sources_are_intersected_with_server_allowlist(self):
        raw = """[协议 resource-plan/v2]
主题: 一次函数
学习目标: 理解斜率
目标难度: 基础
薄弱知识点:
风格约束:
来源白名单: 资料1|资料99|资料1
学科类别: math
[协议结束]"""

        brief = parse_plan_output(raw, source_allowlist=["资料1", "资料2"])

        assert brief.source_allowlist == ["资料1"]

    def test_missing_topic_raises(self):
        raw = """[协议 resource-plan/v2]
学习目标: 目标
目标难度: 基础
学科类别: math
[协议结束]"""
        with pytest.raises(ProtocolValidationError):
            parse_plan_output(raw, source_allowlist=[])

    def test_empty_output_rejected(self):
        with pytest.raises(ProtocolValidationError):
            parse_plan_output("", source_allowlist=[])


class TestValidateBrief:
    def test_valid_brief_passes(self):
        brief = ResourceBrief(
            topic="测试", learning_objectives=["目标"],
            target_difficulty="基础", weak_knowledge_points=[],
            style_constraints="", source_allowlist=[],
            subject_category=SubjectCategory.MATH,
        )
        validate_brief(brief)  # should not raise

    def test_brief_with_path_rejected(self):
        brief = ResourceBrief(
            topic="测试", learning_objectives=["目标"],
            target_difficulty="基础", weak_knowledge_points=["C:\\path"],
            style_constraints="", source_allowlist=[],
            subject_category=SubjectCategory.MATH,
        )
        with pytest.raises(ProtocolValidationError):
            validate_brief(brief)

    def test_brief_with_url_rejected(self):
        brief = ResourceBrief(
            topic="测试", learning_objectives=["目标"],
            target_difficulty="基础", weak_knowledge_points=[],
            style_constraints="使用 https://example.com",
            source_allowlist=[],
            subject_category=SubjectCategory.MATH,
        )
        with pytest.raises(ProtocolValidationError):
            validate_brief(brief)


class TestDeriveTypes:
    def test_bundle_returns_all_five(self):
        types = derive_requested_types("bundle")
        assert len(types) == 5
        assert ArtifactType.COURSE_EXPLANATION in types

    def test_single_returns_one(self):
        types = derive_requested_types("single", ArtifactType.MIND_MAP)
        assert types == [ArtifactType.MIND_MAP]
