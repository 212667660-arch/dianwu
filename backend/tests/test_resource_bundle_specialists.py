from __future__ import annotations

from backend.protocols.v2.models import ArtifactType, ResourceBrief, SubjectCategory
from backend.services.resource_bundle.specialists.base import (
    SpecialistResult,
    build_specialist_messages,
    specialist_for_type,
)
from backend.services.resource_bundle.specialists.course_explanation import CourseExplanationSpecialist
from backend.services.resource_bundle.specialists.mind_map import MindMapSpecialist
from backend.services.resource_bundle.specialists.question_bank import QuestionBankSpecialist
from backend.services.resource_bundle.specialists.extended_reading import ExtendedReadingSpecialist
from backend.services.resource_bundle.specialists.adaptive_practice import AdaptivePracticeSpecialist


BRIEF = ResourceBrief(
    topic="一次函数", learning_objectives=["理解斜率", "计算截距"],
    target_difficulty="基础", weak_knowledge_points=["函数图像", "待定系数法"],
    style_constraints="视觉型优先", source_allowlist=["资料1"],
    subject_category=SubjectCategory.MATH,
)


class TestSpecialistBase:
    def test_build_messages_contains_brief_fields(self):
        messages = build_specialist_messages(
            ArtifactType.COURSE_EXPLANATION, BRIEF, "已验画像文本", "学习上下文", "知识上下文",
        )
        combined = " ".join(m["content"] for m in messages)
        assert "一次函数" in combined
        assert "理解斜率" in combined
        assert "基础" in combined

    def test_specialist_for_type_returns_correct(self):
        assert isinstance(specialist_for_type(ArtifactType.COURSE_EXPLANATION), CourseExplanationSpecialist)
        assert isinstance(specialist_for_type(ArtifactType.MIND_MAP), MindMapSpecialist)
        assert isinstance(specialist_for_type(ArtifactType.QUESTION_BANK), QuestionBankSpecialist)
        assert isinstance(specialist_for_type(ArtifactType.EXTENDED_READING), ExtendedReadingSpecialist)
        assert isinstance(specialist_for_type(ArtifactType.ADAPTIVE_PRACTICE), AdaptivePracticeSpecialist)


class TestCourseExplanationSpecialist:
    def test_prompt_requires_five_sections(self):
        spec = CourseExplanationSpecialist()
        messages = spec.build_prompt(BRIEF, "画像", "", "")
        combined = " ".join(m["content"] for m in messages)
        for section in ["学习目标", "核心概念", "逐步讲解", "常见误区", "个性化建议"]:
            assert section in combined

    def test_parse_valid_output(self):
        spec = CourseExplanationSpecialist()
        raw = """## 学习目标\n目标\n## 核心概念\n概念\n## 逐步讲解\n讲解\n## 常见误区\n误区\n## 个性化建议\n建议"""
        result = spec.parse(raw, "a1")
        assert result.artifact.status.value == "SUCCEEDED"
        assert "学习目标" in result.artifact.body

    def test_parse_dangerous_content_rejected(self):
        spec = CourseExplanationSpecialist()
        raw = "<script>alert(""xss"")</script>"
        result = spec.parse(raw, "a-bad")
        assert result.artifact.status.value == "FAILED"
        assert result.artifact.error_code == "SAFETY_FAILED"

    def test_parse_requires_all_five_sections(self):
        spec = CourseExplanationSpecialist()
        raw = """## 学习目标
目标
## 核心概念
概念
## 逐步讲解
讲解"""
        result = spec.parse(raw, "a-incomplete")
        assert result.artifact.status.value == "FAILED"
        assert result.artifact.error_code == "COURSE_EXPLANATION_INCOMPLETE"

    def test_failed_safety_output_does_not_retain_body(self):
        result = CourseExplanationSpecialist().parse("<script>alert(1)</script>", "a-unsafe")
        assert result.artifact.status.value == "FAILED"
        assert result.artifact.body == ""


class TestMindMapSpecialist:
    def test_prompt_requires_mermaid_and_outline(self):
        spec = MindMapSpecialist()
        messages = spec.build_prompt(BRIEF, "画像", "", "")
        combined = " ".join(m["content"] for m in messages)
        assert "flowchart" in combined.lower() or "graph" in combined.lower()
        assert "大纲" in combined

    def test_parse_mermaid_and_outline(self):
        spec = MindMapSpecialist()
        raw = """## Mermaid
flowchart TD
  A[一次函数] --> B[斜率]
## 大纲
- 一次函数
  - 斜率"""
        result = spec.parse(raw, "a2")
        assert result.artifact.status.value == "SUCCEEDED"
        assert "flowchart" in result.artifact.body

    def test_parse_no_outline_fails(self):
        spec = MindMapSpecialist()
        raw = "flowchart TD\n  A-->B"
        result = spec.parse(raw, "a2b")
        assert result.artifact.status.value == "FAILED"

    def test_parse_empty_outline_fails(self):
        raw = """## Mermaid
flowchart TD
  A-->B
## 大纲
"""
        result = MindMapSpecialist().parse(raw, "a2-empty")
        assert result.artifact.status.value == "FAILED"
        assert result.artifact.error_code == "MISSING_OUTLINE"


class TestQuestionBankSpecialist:
    def test_prompt_requires_three_levels(self):
        spec = QuestionBankSpecialist()
        messages = spec.build_prompt(BRIEF, "画像", "", "")
        combined = " ".join(m["content"] for m in messages)
        for level in ["基础", "提高", "挑战"]:
            assert level in combined

    def test_parse_three_levels(self):
        spec = QuestionBankSpecialist()
        raw = """## 基础
题目1：y=2x+1的截距
答案1：1
解析1：令x=0
## 提高
题目2：求斜率
答案2：2
解析2：系数
## 挑战
题目3：综合
答案3：略
解析3：略"""
        result = spec.parse(raw, "a3")
        assert result.artifact.status.value == "SUCCEEDED"
        assert result.artifact.type_specific_data["basic_count"] >= 1

    def test_parse_rejects_only_basic_level(self):
        raw = """## 基础
题目1：测试
答案1：答案
解析1：解析"""
        result = QuestionBankSpecialist().parse(raw, "a-basic-only")
        assert result.artifact.status.value == "FAILED"
        assert result.artifact.error_code == "QUESTION_BANK_INCOMPLETE"


class TestExtendedReadingSpecialist:
    def test_prompt_requires_citation_rules(self):
        spec = ExtendedReadingSpecialist()
        messages = spec.build_prompt(BRIEF, "画像", "", "")
        combined = " ".join(m["content"] for m in messages)
        assert "资料" in combined

    def test_parse_with_no_external_source(self):
        spec = ExtendedReadingSpecialist()
        raw = """## 延伸阅读
无可引用外部来源，以下基于已有知识。"""
        result = spec.parse(raw, "a4")
        assert result.artifact.status.value == "SUCCEEDED"

    def test_parse_rejects_unknown_citation(self):
        raw = """## 延伸阅读
内容引用[资料99]。"""
        result = ExtendedReadingSpecialist().parse(
            raw,
            "a4-unknown",
            source_allowlist=("资料1",),
        )
        assert result.artifact.status.value == "FAILED"
        assert result.artifact.error_code == "CITATION_NOT_ALLOWED"

    def test_parse_requires_no_source_disclosure_when_allowlist_empty(self):
        raw = """## 延伸阅读
以下是延伸内容。"""
        result = ExtendedReadingSpecialist().parse(raw, "a4-no-disclosure", source_allowlist=())
        assert result.artifact.status.value == "FAILED"
        assert result.artifact.error_code == "MISSING_NO_SOURCE_DISCLOSURE"


class TestAdaptivePracticeSpecialist:
    def test_prompt_for_cs_subject_includes_code_lab(self):
        brief = ResourceBrief(
            topic="Python循环", learning_objectives=["理解for循环"],
            target_difficulty="基础", weak_knowledge_points=[],
            style_constraints="", source_allowlist=[], subject_category=SubjectCategory.CS,
        )
        spec = AdaptivePracticeSpecialist()
        messages = spec.build_prompt(brief, "画像", "", "")
        combined = " ".join(m["content"] for m in messages)
        assert "起始代码" in combined or "code" in combined.lower()

    def test_prompt_for_non_cs_subject_no_starter_code(self):
        brief = ResourceBrief(
            topic="一次函数", learning_objectives=["理解斜率"],
            target_difficulty="基础", weak_knowledge_points=[],
            style_constraints="", source_allowlist=[], subject_category=SubjectCategory.MATH,
        )
        spec = AdaptivePracticeSpecialist()
        messages = spec.build_prompt(brief, "画像", "", "")
        combined = " ".join(m["content"] for m in messages)
        assert "起始代码" not in combined

    def test_parse_cs_code_lab(self):
        spec = AdaptivePracticeSpecialist()
        raw = """## 目标
理解循环
## 环境
Python 3
## 步骤
1. 写代码
## 验收标准
运行通过
## 参考方法
用for循环
## 起始代码
for i in range(10):
    pass"""
        result = spec.parse(raw, "a5", subject_category=SubjectCategory.CS)
        assert result.artifact.status.value == "SUCCEEDED"
        assert result.artifact.type_specific_data["format"] == "code_lab"

    def test_parse_non_cs_experiment(self):
        spec = AdaptivePracticeSpecialist()
        raw = """## 目标
理解斜率
## 前置条件
无
## 步骤
1. 画图
## 验收标准
正确
## 参考方法
两点法"""
        result = spec.parse(raw, "a6", subject_category=SubjectCategory.MATH)
        assert result.artifact.status.value == "SUCCEEDED"
        assert result.artifact.type_specific_data["format"] == "experiment_or_case"

    def test_parse_cs_rejects_missing_starter_code(self):
        raw = """## 目标
理解循环
## 环境
Python 3
## 步骤
1. 写代码
## 验收标准
运行通过
## 参考方法
用for循环"""
        result = AdaptivePracticeSpecialist().parse(
            raw,
            "a5-missing-starter",
            subject_category=SubjectCategory.CS,
        )
        assert result.artifact.status.value == "FAILED"
        assert result.artifact.error_code == "ADAPTIVE_PRACTICE_INCOMPLETE"

    def test_parse_non_cs_requires_all_sections(self):
        raw = """## 目标
理解斜率
## 步骤
1. 画图
## 验收标准
正确
## 参考方法
两点法"""
        result = AdaptivePracticeSpecialist().parse(
            raw,
            "a6-missing-prerequisite",
            subject_category=SubjectCategory.MATH,
        )
        assert result.artifact.status.value == "FAILED"
        assert result.artifact.error_code == "ADAPTIVE_PRACTICE_INCOMPLETE"
