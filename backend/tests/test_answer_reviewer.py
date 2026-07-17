from __future__ import annotations

from backend.protocols.v2.models import ArtifactStatus, ArtifactType, ResourceArtifact, SubjectCategory
from backend.services.resource_bundle.answer_reviewer import AnswerReviewerAgent


def artifact(body: str, artifact_type: ArtifactType = ArtifactType.COURSE_EXPLANATION) -> ResourceArtifact:
    return ResourceArtifact(
        artifact_id="review-1",
        type=artifact_type,
        title="待复核答案",
        status=ArtifactStatus.SUCCEEDED,
        body=body,
        quality_score=90,
    )


def test_reviewer_accepts_separated_grounded_math_with_complete_substitution() -> None:
    verdict = AnswerReviewerAgent().review(
        artifact("""## 教材内容
一次函数定义见[资料1]。
## 模型补充知识
可用图像理解斜率。
## 公式与适用条件
$y=kx+b$
## 分步推导
代入 $x=2$ 得 $y=2\\times2+1=5$。
## 结果检查
将 $y=5$ 代回成立。"""),
        source_allowlist={"资料1"},
        textbook_source_ids={"资料1"},
        subject_category=SubjectCategory.MATH,
        require_textbook_sections=True,
    )

    assert verdict.approved is True
    assert verdict.issues == ()
    assert verdict.formula_checked is True
    assert verdict.substitution_checked is True


def test_reviewer_flags_citation_ownership_formula_format_and_incomplete_substitution() -> None:
    verdict = AnswerReviewerAgent().review(
        artifact("""## 教材内容
没有引用。
## 模型补充知识
模型补充却声称来自[资料1]。
## 公式与适用条件
$y=kx+b
## 分步推导
代入 x=2。
## 结果检查
待检查。"""),
        source_allowlist={"资料1"},
        textbook_source_ids={"资料1"},
        subject_category=SubjectCategory.MATH,
        require_textbook_sections=True,
    )

    assert verdict.approved is False
    assert "TEXTBOOK_SECTION_GROUNDING_MISSING" in verdict.issues
    assert "MODEL_SECTION_CITATION_NOT_ALLOWED" in verdict.issues
    assert "FORMULA_DELIMITER_UNBALANCED" in verdict.issues
    assert "SUBSTITUTION_EQUATION_INCOMPLETE" in verdict.issues


def test_public_source_citation_does_not_count_as_textbook_grounding() -> None:
    verdict = AnswerReviewerAgent().review(
        artifact("""## 教材内容
这段只引用公开网页[资料2]。
## 模型补充知识
模型推导不引用来源。"""),
        source_allowlist={"资料1", "资料2"},
        textbook_source_ids={"资料1"},
        subject_category=SubjectCategory.MATH,
        require_textbook_sections=True,
    )

    assert verdict.approved is False
    assert "TEXTBOOK_SECTION_GROUNDING_MISSING" in verdict.issues
