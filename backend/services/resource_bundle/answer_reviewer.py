from __future__ import annotations

from dataclasses import dataclass
import re

from backend.protocols.v2.models import ArtifactType, ResourceArtifact, SubjectCategory
from backend.services.content_safety.prompt_boundary import untrusted_json_block


_CITATION = re.compile(r"\[(资料[1-9]\d{0,2})\]")
_SECTION = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_REVIEWED_TYPES = {
    ArtifactType.COURSE_EXPLANATION,
    ArtifactType.QUESTION_BANK,
    ArtifactType.ADAPTIVE_PRACTICE,
}


@dataclass(frozen=True)
class AnswerReviewVerdict:
    approved: bool
    issues: tuple[str, ...]
    formula_checked: bool
    substitution_checked: bool


def _sections(body: str) -> dict[str, str]:
    matches = list(_SECTION.finditer(body))
    return {
        match.group(1).strip(): body[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(body)].strip()
        for index, match in enumerate(matches)
    }


class AnswerReviewerAgent:
    def applies_to(self, artifact_type: ArtifactType) -> bool:
        return artifact_type in _REVIEWED_TYPES

    def review(
        self,
        artifact: ResourceArtifact,
        *,
        source_allowlist: set[str],
        textbook_source_ids: set[str],
        subject_category: SubjectCategory,
        require_textbook_sections: bool,
    ) -> AnswerReviewVerdict:
        issues: list[str] = []
        body = artifact.body
        sections = _sections(body)
        used_citations = set(_CITATION.findall(body))
        unknown = sorted(used_citations - source_allowlist)
        if unknown:
            issues.append("ANSWER_CITATION_NOT_ALLOWED")

        if artifact.type == ArtifactType.COURSE_EXPLANATION and require_textbook_sections:
            textbook = sections.get("教材内容", "")
            supplement = sections.get("模型补充知识", "")
            if not textbook:
                issues.append("TEXTBOOK_SECTION_MISSING")
            if not supplement:
                issues.append("MODEL_SUPPLEMENT_SECTION_MISSING")
            textbook_citations = set(_CITATION.findall(textbook))
            if textbook and "证据不足" not in textbook and not (textbook_citations & textbook_source_ids):
                issues.append("TEXTBOOK_SECTION_GROUNDING_MISSING")
            if _CITATION.search(supplement):
                issues.append("MODEL_SECTION_CITATION_NOT_ALLOWED")

        formula_checked = any(token in body for token in ("$", "\\(", "\\)", "\\[", "\\]"))
        if formula_checked and (
            body.count("$") % 2 != 0
            or body.count("\\(") != body.count("\\)")
            or body.count("\\[") != body.count("\\]")
        ):
            issues.append("FORMULA_DELIMITER_UNBALANCED")

        substitution_lines = [
            line.strip()
            for line in body.splitlines()
            if "代入" in line and ("=" in line or "$" in line or "\\(" in line)
        ]
        substitution_checked = bool(substitution_lines)
        if substitution_checked and any(line.count("=") < 2 for line in substitution_lines):
            issues.append("SUBSTITUTION_EQUATION_INCOMPLETE")
        if substitution_checked and not sections.get("结果检查"):
            issues.append("RESULT_CHECK_MISSING")

        unique_issues = tuple(dict.fromkeys(issues))
        return AnswerReviewVerdict(
            approved=not unique_issues,
            issues=unique_issues,
            formula_checked=formula_checked,
            substitution_checked=substitution_checked,
        )

    def repair_messages(
        self,
        original_messages: list[dict[str, str]],
        artifact: ResourceArtifact,
        verdict: AnswerReviewVerdict,
    ) -> list[dict[str, str]]:
        review_block = untrusted_json_block(
            "answer_review_repair",
            {
                "artifact_type": artifact.type.value,
                "issues": list(verdict.issues),
                "previous_answer": artifact.body,
            },
            field_limit=20_000,
            total_limit=24_000,
        )
        return [
            *original_messages,
            {
                "role": "user",
                "content": (
                    f"{review_block}\n"
                    "答案复核 Agent 发现上述受控问题。请完整重写资源，只修复这些问题并保持原输出结构；"
                    "教材事实只能放在‘教材内容’并使用允许的[资料N]，模型推导放在‘模型补充知识’；"
                    "所有数学公式定界符必须闭合，数值代入必须写出从已知量到最终结果的完整等式。"
                ),
            },
        ]

    def attach(
        self,
        artifact: ResourceArtifact,
        verdict: AnswerReviewVerdict,
        *,
        status: str,
        repair_attempted: bool,
        warning: bool = False,
    ) -> ResourceArtifact:
        review = {
            "agent": "answer-reviewer/v1",
            "status": status,
            "issues": list(verdict.issues),
            "repair_attempted": repair_attempted,
            "formula_checked": verdict.formula_checked,
            "substitution_checked": verdict.substitution_checked,
        }
        body = artifact.body
        quality_issues = list(artifact.quality_issues)
        quality_score = artifact.quality_score
        if warning:
            body = "> 答案复核提示：公式、代入或教材归属仍需人工核对。\n\n" + body
            quality_issues = list(dict.fromkeys([*quality_issues, *verdict.issues, "ANSWER_REVIEW_WARNING"]))
            quality_score = max(0, quality_score - 20)
        return artifact.model_copy(update={
            "body": body,
            "quality_score": quality_score,
            "quality_issues": quality_issues,
            "type_specific_data": {**artifact.type_specific_data, "answer_review": review},
        })
