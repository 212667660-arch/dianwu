from __future__ import annotations

import re

from backend.protocols.v2.models import ArtifactType, ArtifactStatus, ResourceArtifact, ResourceBrief
from backend.services.resource_bundle.specialists.base import Specialist, SpecialistResult, build_specialist_prompt

_QB_LEVELS = ["基础", "提高", "挑战"]
_SOLUTION_STEPS = ["已知条件与目标", "所用知识点", "分步推导", "最终答案", "结果检查"]


class QuestionBankSpecialist(Specialist):
    @property
    def artifact_type(self) -> ArtifactType:
        return ArtifactType.QUESTION_BANK

    def build_prompt(
        self, brief: ResourceBrief, profile_text: str,
        learning_context: str, knowledge_context: str,
    ) -> list[dict[str, str]]:
        level_instruction = "\n".join(
            (
                f"## {level}\n题目N：...\n答案N：...\n解析N：\n"
                + "\n".join(f"- {step}：..." for step in _SOLUTION_STEPS)
            )
            for level in _QB_LEVELS
        )
        return build_specialist_prompt(
            artifact_type=self.artifact_type,
            static_instruction=(
                "请严格按照以下三个难度层级输出，每道题需包含题目、答案和完整解析。"
                "解析必须给出已知条件与目标、所用知识点及适用条件、分步推导、最终答案和结果检查。"
                "使用教材时只能引用服务器提供的[资料N]；证据不足时明确说明，不得伪造引用：\n"
                f"{level_instruction}"
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
        type_specific: dict[str, object] = {}
        total_questions = 0
        complete_levels = True
        solution_steps_by_level: dict[str, bool] = {}
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
                solution_steps_ok = q_count >= 1 and all(
                    len(re.findall(rf'{re.escape(step)}[：:]', section_body)) >= q_count
                    for step in _SOLUTION_STEPS
                )
                solution_steps_by_level[level] = solution_steps_ok
                complete_levels = complete_levels and solution_steps_ok
            else:
                type_specific[f"{level}_count"] = 0
                solution_steps_by_level[level] = False
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
                    (
                        f"INCOMPLETE_LEVEL:{level}"
                        if type_specific.get(f"{level}_count", 0) == 0
                        else f"INCOMPLETE_SOLUTION_STEPS:{level}"
                    )
                    for level in _QB_LEVELS
                    if type_specific.get(f"{level}_count", 0) == 0
                    or not solution_steps_by_level.get(level, False)
                ],
            ),
            raw_output=raw_output,
        )
