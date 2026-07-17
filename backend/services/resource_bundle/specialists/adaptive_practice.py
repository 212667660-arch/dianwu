from __future__ import annotations

import re

from backend.protocols.v2.models import ArtifactType, ArtifactStatus, ResourceArtifact, ResourceBrief, SubjectCategory
from backend.services.resource_bundle.specialists.base import Specialist, SpecialistResult, build_specialist_prompt, has_required_grounding

_CODE_LAB_SECTIONS = ["目标", "环境", "步骤", "验收标准", "参考方法", "起始代码"]
_EXPERIMENT_SECTIONS = ["目标", "前置条件", "步骤", "验收标准", "参考方法"]
_MATH_PRACTICE_SECTIONS = ["目标", "已知条件与目标", "所用知识点", "分步推导", "最终答案", "结果检查", "验收标准", "参考方法"]


class AdaptivePracticeSpecialist(Specialist):
    @property
    def artifact_type(self) -> ArtifactType:
        return ArtifactType.ADAPTIVE_PRACTICE

    def build_prompt(
        self, brief: ResourceBrief, profile_text: str,
        learning_context: str, knowledge_context: str,
    ) -> list[dict[str, str]]:
        if brief.subject_category == SubjectCategory.CS:
            sections = "\n".join(f"## {s}\n（在此填写{s}内容）" for s in _CODE_LAB_SECTIONS)
            static_instruction = (
                "生成编程实验并包含非空起始代码，严格按以下部分输出：\n"
                f"{sections}"
            )
        elif brief.subject_category == SubjectCategory.MATH:
            sections = "\n".join(f"## {s}\n（在此填写{s}内容）" for s in _MATH_PRACTICE_SECTIONS)
            static_instruction = (
                "生成数学适应性练习并完整展示做题过程。使用教材时只能引用服务器提供的[资料N]；"
                "证据不足时必须明确说明证据不足。严格按以下部分输出：\n"
                f"{sections}"
            )
        else:
            sections = "\n".join(f"## {s}\n（在此填写{s}内容）" for s in _EXPERIMENT_SECTIONS)
            static_instruction = (
                "生成实验/案例，不提供代码模板，严格按以下部分输出：\n"
                f"{sections}"
            )
        return build_specialist_prompt(
            artifact_type=self.artifact_type,
            static_instruction=static_instruction,
            brief=brief,
            profile_text=profile_text,
            learning_context=learning_context,
            knowledge_context=knowledge_context,
        )

    def parse(
        self, raw_output: str, artifact_id: str, *,
        source_allowlist: tuple[str, ...] = (),
        subject_category: SubjectCategory = SubjectCategory.OTHER,
    ) -> SpecialistResult:
        fmt = (
            "code_lab" if subject_category == SubjectCategory.CS
            else "worked_practice" if subject_category == SubjectCategory.MATH
            else "experiment_or_case"
        )
        required = (
            _CODE_LAB_SECTIONS if subject_category == SubjectCategory.CS
            else _MATH_PRACTICE_SECTIONS if subject_category == SubjectCategory.MATH
            else _EXPERIMENT_SECTIONS
        )
        found = sum(1 for s in required if f"## {s}" in raw_output)
        starter_match = (
            re.search(r"##\s*起始代码\s*\n([\s\S]*?)\Z", raw_output)
            if subject_category == SubjectCategory.CS
            else None
        )
        starter_ok = subject_category != SubjectCategory.CS or bool(
            starter_match and starter_match.group(1).strip()
        )

        grounding_ok = has_required_grounding(raw_output, source_allowlist)
        if found == len(required) and starter_ok and grounding_ok:
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
                body="",
                error_code=(
                    "TEXTBOOK_EVIDENCE_REQUIRED"
                    if found == len(required) and starter_ok and not grounding_ok
                    else "ADAPTIVE_PRACTICE_INCOMPLETE"
                ),
                quality_score=min(found * 15, 100),
                quality_issues=[
                    *[
                        f"MISSING_SECTION:{section}"
                        for section in required
                        if f"## {section}" not in raw_output
                    ],
                    *([] if starter_ok else ["STARTER_CODE_EMPTY"]),
                    *([] if grounding_ok else ["MISSING_TEXTBOOK_EVIDENCE_OR_INSUFFICIENCY"]),
                ],
            ),
            raw_output=raw_output,
        )
