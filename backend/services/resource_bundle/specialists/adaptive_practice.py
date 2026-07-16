from __future__ import annotations

from backend.protocols.v2.models import ArtifactType, ArtifactStatus, ResourceArtifact, ResourceBrief, SubjectCategory
from backend.services.resource_bundle.safety import check_dangerous_content
from backend.services.resource_bundle.specialists.base import Specialist, SpecialistResult

_CODE_LAB_SECTIONS = ["目标", "环境", "步骤", "验收标准", "参考方法", "起始代码"]
_EXPERIMENT_SECTIONS = ["目标", "前置条件", "步骤", "验收标准", "参考方法"]


class AdaptivePracticeSpecialist(Specialist):
    @property
    def artifact_type(self) -> ArtifactType:
        return ArtifactType.ADAPTIVE_PRACTICE

    def build_prompt(
        self, brief: ResourceBrief, profile_text: str,
        learning_context: str, knowledge_context: str,
    ) -> list[dict[str, str]]:
        if brief.subject_category == SubjectCategory.CS:
            section_instruction = "\n".join(f"## {s}\n（在此填写{s}内容）" for s in _CODE_LAB_SECTIONS)
            format_note = (
                f"请生成编程实验（code lab）格式的适应性练习。\n"
                f"必须包含 ## 起始代码 部分，提供初始代码框架。\n"
                f"严格按照以下部分输出：\n{section_instruction}"
            )
        else:
            section_instruction = "\n".join(f"## {s}\n（在此填写{s}内容）" for s in _EXPERIMENT_SECTIONS)
            format_note = (
                f"请生成实验/案例格式的适应性练习。\n"
                f"不需要提供代码模板。\n"
                f"严格按照以下部分输出：\n{section_instruction}"
            )

        system_msg = (
            f"你是一位专业的适应性练习设计专家。请为主题「{brief.topic}」生成适应性练习。\n"
            f"学习目标：{''.join(brief.learning_objectives)}\n"
            f"目标难度：{brief.target_difficulty}\n"
            f"薄弱知识点：{''.join(brief.weak_knowledge_points) if brief.weak_knowledge_points else '无'}\n"
            f"风格约束：{brief.style_constraints or '无特殊约束'}\n"
            f"学科类别：{brief.subject_category.value}\n\n"
            f"{format_note}"
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
                    title="适应性练习",
                    status=ArtifactStatus.FAILED,
                    body=raw_output,
                    error_code="SAFETY_FAILED",
                    quality_score=0,
                ),
                raw_output=raw_output,
            )

        has_starter = "## 起始代码" in raw_output
        has_env = "## 环境" in raw_output
        fmt = "code_lab" if (has_starter or has_env) else "experiment_or_case"

        required = _CODE_LAB_SECTIONS if fmt == "code_lab" else _EXPERIMENT_SECTIONS
        found = sum(1 for s in required if f"## {s}" in raw_output)

        if found >= len(required) - 1:
            return SpecialistResult(
                artifact=ResourceArtifact(
                    artifact_id=artifact_id,
                    type=self.artifact_type,
                    title="适应性练习",
                    status=ArtifactStatus.SUCCEEDED,
                    body=raw_output,
                    quality_score=min(found * 15, 100),
                    type_specific_data={"format": fmt, "sections_found": found, "total_sections": len(required)},
                ),
                raw_output=raw_output,
            )
        return SpecialistResult(
            artifact=ResourceArtifact(
                artifact_id=artifact_id,
                type=self.artifact_type,
                title="适应性练习",
                status=ArtifactStatus.FAILED,
                body=raw_output,
                error_code="INSUFFICIENT_SECTIONS",
                quality_score=min(found * 15, 100),
            ),
            raw_output=raw_output,
        )
