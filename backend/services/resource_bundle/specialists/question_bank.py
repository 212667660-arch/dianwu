from __future__ import annotations

import re

from backend.protocols.v2.models import ArtifactType, ArtifactStatus, ResourceArtifact, ResourceBrief
from backend.services.resource_bundle.safety import check_dangerous_content
from backend.services.resource_bundle.specialists.base import Specialist, SpecialistResult

_QB_LEVELS = ["基础", "提高", "挑战"]


class QuestionBankSpecialist(Specialist):
    @property
    def artifact_type(self) -> ArtifactType:
        return ArtifactType.QUESTION_BANK

    def build_prompt(
        self, brief: ResourceBrief, profile_text: str,
        learning_context: str, knowledge_context: str,
    ) -> list[dict[str, str]]:
        level_instruction = "\n".join(
            f"## {level}\n题目N：...\n答案N：...\n解析N：..."
            for level in _QB_LEVELS
        )
        system_msg = (
            f"你是一位专业的题库生成专家。请为主题「{brief.topic}」生成分层练习题。\n"
            f"学习目标：{''.join(brief.learning_objectives)}\n"
            f"目标难度：{brief.target_difficulty}\n"
            f"薄弱知识点：{''.join(brief.weak_knowledge_points) if brief.weak_knowledge_points else '无'}\n"
            f"风格约束：{brief.style_constraints or '无特殊约束'}\n\n"
            f"请严格按照以下三个难度层级输出，每道题需包含题目、答案和解析：\n{level_instruction}"
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
                    title="题库",
                    status=ArtifactStatus.FAILED,
                    body="",
                    error_code="SAFETY_FAILED",
                    quality_score=0,
                    quality_issues=safety.issues,
                ),
                raw_output=raw_output,
            )

        type_specific: dict[str, object] = {}
        total_questions = 0
        complete_levels = True
        for level in _QB_LEVELS:
            # Count questions in each level section
            pattern = re.compile(rf'##\s*{level}\s*\n(.*?)(?=##\s*(?:{"|".join(_QB_LEVELS)})|\Z)', re.DOTALL)
            section_match = pattern.search(raw_output)
            if section_match:
                section_body = section_match.group(1)
                q_count = len(re.findall(r'题目\d+[：:]', section_body))
                answer_count = len(re.findall(r'答案\d+[：:]', section_body))
                explanation_count = len(re.findall(r'解析\d+[：:]', section_body))
                type_specific[f"{level}_count"] = q_count
                total_questions += q_count
                complete_levels = complete_levels and q_count >= 1
                complete_levels = complete_levels and answer_count >= q_count
                complete_levels = complete_levels and explanation_count >= q_count
            else:
                type_specific[f"{level}_count"] = 0
                complete_levels = False

        # Add a "basic_count" alias for backward compatibility in tests
        type_specific["basic_count"] = type_specific.get("基础_count", 0)

        if complete_levels:
            return SpecialistResult(
                artifact=ResourceArtifact(
                    artifact_id=artifact_id,
                    type=self.artifact_type,
                    title="题库",
                    status=ArtifactStatus.SUCCEEDED,
                    body=raw_output,
                    quality_score=min(total_questions * 10, 100),
                    type_specific_data=type_specific,
                ),
                raw_output=raw_output,
            )
        return SpecialistResult(
            artifact=ResourceArtifact(
                artifact_id=artifact_id,
                type=self.artifact_type,
                title="题库",
                status=ArtifactStatus.FAILED,
                body="",
                error_code="QUESTION_BANK_INCOMPLETE",
                quality_score=min(total_questions * 10, 100),
                quality_issues=[
                    f"INCOMPLETE_LEVEL:{level}"
                    for level in _QB_LEVELS
                    if type_specific.get(f"{level}_count", 0) == 0
                ],
            ),
            raw_output=raw_output,
        )
