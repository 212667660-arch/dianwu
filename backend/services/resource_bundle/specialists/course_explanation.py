from __future__ import annotations

from backend.protocols.v2.models import ArtifactType, ArtifactStatus, ResourceArtifact, ResourceBrief
from backend.services.resource_bundle.safety import check_dangerous_content
from backend.services.resource_bundle.specialists.base import Specialist, SpecialistResult, build_specialist_prompt

_COURSE_SECTIONS = ["学习目标", "核心概念", "逐步讲解", "常见误区", "个性化建议"]


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
            static_instruction=f"请严格按照以下五个部分输出：\n{section_instruction}",
            brief=brief,
            profile_text=profile_text,
            learning_context=learning_context,
            knowledge_context=knowledge_context,
        )

    def parse(
        self, raw_output: str, artifact_id: str, *,
        source_allowlist: tuple[str, ...] = (), subject_category=None,
    ) -> SpecialistResult:
        safety = check_dangerous_content(raw_output)
        if not safety.passed:
            return SpecialistResult(
                artifact=ResourceArtifact(
                    artifact_id=artifact_id,
                    type=self.artifact_type,
                    title="课程讲解",
                    status=ArtifactStatus.FAILED,
                    body="",
                    error_code="SAFETY_FAILED",
                    quality_score=0,
                    quality_issues=safety.issues,
                ),
                raw_output=raw_output,
            )

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
