from __future__ import annotations

from backend.protocols.v2.models import ArtifactType, ArtifactStatus, ResourceArtifact, ResourceBrief
from backend.services.resource_bundle.safety import check_dangerous_content
from backend.services.resource_bundle.specialists.base import Specialist, SpecialistResult

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
        system_msg = (
            f"你是一位专业的课程讲解专家。请为主题「{brief.topic}」生成结构化的课程讲解。\n"
            f"学习目标：{''.join(brief.learning_objectives)}\n"
            f"目标难度：{brief.target_difficulty}\n"
            f"薄弱知识点：{''.join(brief.weak_knowledge_points) if brief.weak_knowledge_points else '无'}\n"
            f"风格约束：{brief.style_constraints or '无特殊约束'}\n\n"
            f"请严格按照以下五个部分输出：\n{section_instruction}"
        )
        user_msg = (
            f"学习者画像：{profile_text}\n"
            f"学习上下文：{learning_context}\n"
            f"知识上下文：{knowledge_context}"
        )
        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

    def parse(self, raw_output: str, artifact_id: str) -> SpecialistResult:
        safety = check_dangerous_content(raw_output)
        if not safety.passed:
            return SpecialistResult(
                artifact=ResourceArtifact(
                    artifact_id=artifact_id,
                    type=self.artifact_type,
                    title="课程讲解",
                    status=ArtifactStatus.FAILED,
                    body=raw_output,
                    error_code="SAFETY_FAILED",
                    quality_score=0,
                ),
                raw_output=raw_output,
            )

        found = sum(1 for s in _COURSE_SECTIONS if f"## {s}" in raw_output)
        score = min(found * 20, 100)
        if found >= 3:
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
                body=raw_output,
                error_code="INSUFFICIENT_SECTIONS",
                quality_score=score,
            ),
            raw_output=raw_output,
        )
