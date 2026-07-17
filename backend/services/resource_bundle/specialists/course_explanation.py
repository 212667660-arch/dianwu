from __future__ import annotations

from backend.protocols.v2.models import ArtifactType, ArtifactStatus, ResourceArtifact, ResourceBrief
from backend.services.resource_bundle.specialists.base import Specialist, SpecialistResult, build_specialist_prompt

_COURSE_SECTIONS = [
    "学习目标",
    "核心概念与定义",
    "公式与适用条件",
    "知识依赖",
    "逐步讲解",
    "常见题型与易错点",
    "个性化建议",
]


class CourseExplanationSpecialist(Specialist):
    @property
    def artifact_type(self) -> ArtifactType:
        return ArtifactType.COURSE_EXPLANATION

    def build_prompt(
        self, brief: ResourceBrief, profile_text: str,
        learning_context: str, knowledge_context: str,
    ) -> list[dict[str, str]]:
        section_instruction = "\n".join(f"## {s}\n（在此填写{s}内容）" for s in _COURSE_SECTIONS)
        return build_specialist_prompt(
            artifact_type=self.artifact_type,
            static_instruction=(
                "请严格按照以下七个部分输出。逐步讲解需要说明每一步的依据；"
                "只有服务器提供的[资料N]可以作为教材引用。检索证据不足时必须明确说明证据不足，"
                "不得伪造教材原文、页码或引用：\n"
                f"{section_instruction}"
            ),
            brief=brief,
            profile_text=profile_text,
            learning_context=learning_context,
            knowledge_context=knowledge_context,
        )

    def parse(
        self, raw_output: str, artifact_id: str, *,
        source_allowlist: tuple[str, ...] = (), subject_category=None,
    ) -> SpecialistResult:
        found = sum(1 for s in _COURSE_SECTIONS if f"## {s}" in raw_output)
        score = min(found * 20, 100)
        if found == len(_COURSE_SECTIONS):
            return SpecialistResult(
                artifact=ResourceArtifact(
                    artifact_id=artifact_id,
                    type=self.artifact_type,
                    title="课程讲解",
                    status=ArtifactStatus.SUCCEEDED,
                    body=raw_output,
                    quality_score=score,
                    type_specific_data={"sections_found": found, "total_sections": len(_COURSE_SECTIONS)},
                ),
                raw_output=raw_output,
            )
        return SpecialistResult(
            artifact=ResourceArtifact(
                artifact_id=artifact_id,
                type=self.artifact_type,
                title="课程讲解",
                status=ArtifactStatus.FAILED,
                body="",
                error_code="COURSE_EXPLANATION_INCOMPLETE",
                quality_score=score,
                quality_issues=[
                    f"MISSING_SECTION:{section}"
                    for section in _COURSE_SECTIONS
                    if f"## {section}" not in raw_output
                ],
            ),
            raw_output=raw_output,
        )
