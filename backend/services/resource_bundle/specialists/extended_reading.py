from __future__ import annotations

from backend.protocols.v2.models import ArtifactType, ArtifactStatus, ResourceArtifact, ResourceBrief
from backend.services.resource_bundle.safety import check_dangerous_content
from backend.services.resource_bundle.specialists.base import Specialist, SpecialistResult


class ExtendedReadingSpecialist(Specialist):
    @property
    def artifact_type(self) -> ArtifactType:
        return ArtifactType.EXTENDED_READING

    def build_prompt(
        self, brief: ResourceBrief, profile_text: str,
        learning_context: str, knowledge_context: str,
    ) -> list[dict[str, str]]:
        allowlist_hint = ""
        if brief.source_allowlist:
            allowlist_hint = f"可引用的资料：{'、'.join(brief.source_allowlist)}\n只能引用以上资料，若无可用资料则声明'无可引用外部来源，以下基于已有知识。'"
        else:
            allowlist_hint = "无可引用资料，请声明'无可引用外部来源，以下基于已有知识。'"

        system_msg = (
            f"你是一位专业的延伸阅读推荐专家。请为主题「{brief.topic}」生成延伸阅读资源。\n"
            f"学习目标：{''.join(brief.learning_objectives)}\n"
            f"目标难度：{brief.target_difficulty}\n"
            f"薄弱知识点：{''.join(brief.weak_knowledge_points) if brief.weak_knowledge_points else '无'}\n"
            f"风格约束：{brief.style_constraints or '无特殊约束'}\n"
            f"{allowlist_hint}\n\n"
            f"请严格按照以下格式输出：\n"
            f"## 延伸阅读\n（延伸阅读内容，引用资料需使用[资料N]标记）"
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
                    title="延伸阅读",
                    status=ArtifactStatus.FAILED,
                    body=raw_output,
                    error_code="SAFETY_FAILED",
                    quality_score=0,
                ),
                raw_output=raw_output,
            )

        if "## 延伸阅读" not in raw_output:
            return SpecialistResult(
                artifact=ResourceArtifact(
                    artifact_id=artifact_id,
                    type=self.artifact_type,
                    title="延伸阅读",
                    status=ArtifactStatus.FAILED,
                    body=raw_output,
                    error_code="MISSING_SECTION",
                    quality_score=0,
                ),
                raw_output=raw_output,
            )

        return SpecialistResult(
            artifact=ResourceArtifact(
                artifact_id=artifact_id,
                type=self.artifact_type,
                title="延伸阅读",
                status=ArtifactStatus.SUCCEEDED,
                body=raw_output,
                quality_score=70,
                type_specific_data={"has_reading_section": True},
            ),
            raw_output=raw_output,
        )
