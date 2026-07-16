from __future__ import annotations

import re

from backend.protocols.v2.models import ArtifactType, ArtifactStatus, ResourceArtifact, ResourceBrief
from backend.services.resource_bundle.safety import check_dangerous_content, _MERMAID_SAFE_PREFIX, _MERMAID_UNSAFE
from backend.services.resource_bundle.specialists.base import Specialist, SpecialistResult, build_specialist_prompt


class MindMapSpecialist(Specialist):
    @property
    def artifact_type(self) -> ArtifactType:
        return ArtifactType.MIND_MAP

    def build_prompt(
        self, brief: ResourceBrief, profile_text: str,
        learning_context: str, knowledge_context: str,
    ) -> list[dict[str, str]]:
        return build_specialist_prompt(
            artifact_type=self.artifact_type,
            static_instruction=(
                "请严格按照以下两个部分输出：\n"
                "## Mermaid\n使用 flowchart 或 graph 语法绘制思维导图，只能使用安全的 flowchart/graph 节点和边，禁止任何 click、href、javascript 或 HTML 标签。\n"
                "## 大纲\n用缩进列表展示知识结构大纲"
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
        safety = check_dangerous_content(raw_output)
        if not safety.passed:
            return SpecialistResult(
                artifact=ResourceArtifact(
                    artifact_id=artifact_id,
                    type=self.artifact_type,
                    title="思维导图",
                    status=ArtifactStatus.FAILED,
                    body="",
                    error_code="SAFETY_FAILED",
                    quality_score=0,
                    quality_issues=safety.issues,
                ),
                raw_output=raw_output,
            )

        mermaid_match = re.search(r'##\s*Mermaid\s*\n(.*?)(?=##\s*大纲|\Z)', raw_output, re.DOTALL)
        outline_match = re.search(r'##\s*大纲\s*\n([\s\S]*?)\Z', raw_output)

        if not mermaid_match:
            return SpecialistResult(
                artifact=ResourceArtifact(
                    artifact_id=artifact_id,
                    type=self.artifact_type,
                    title="思维导图",
                    status=ArtifactStatus.FAILED,
                    body="",
                    error_code="MISSING_MERMAID",
                    quality_score=0,
                ),
                raw_output=raw_output,
            )

        mermaid_body = mermaid_match.group(1).strip()

        if not outline_match or not outline_match.group(1).strip():
            return SpecialistResult(
                artifact=ResourceArtifact(
                    artifact_id=artifact_id,
                    type=self.artifact_type,
                    title="思维导图",
                    status=ArtifactStatus.FAILED,
                    body="",
                    error_code="MISSING_OUTLINE",
                    quality_score=0,
                ),
                raw_output=raw_output,
            )

        # Safety checks on mermaid body
        issues: list[str] = []
        if not _MERMAID_SAFE_PREFIX.search(mermaid_body):
            issues.append("MERMAID_UNSAFE_PREFIX")
        if _MERMAID_UNSAFE.search(mermaid_body):
            issues.append("MERMAID_UNSAFE_CONTENT")

        if issues:
            return SpecialistResult(
                artifact=ResourceArtifact(
                    artifact_id=artifact_id,
                    type=self.artifact_type,
                    title="思维导图",
                    status=ArtifactStatus.FAILED,
                    body="",
                    error_code=";".join(issues),
                    quality_score=0,
                    quality_issues=issues,
                ),
                raw_output=raw_output,
            )

        return SpecialistResult(
            artifact=ResourceArtifact(
                artifact_id=artifact_id,
                type=self.artifact_type,
                title="思维导图",
                status=ArtifactStatus.SUCCEEDED,
                body=raw_output,
                quality_score=80,
                type_specific_data={
                    "has_mermaid": True,
                    "has_outline": True,
                    "outline": outline_match.group(1).strip(),
                },
            ),
            raw_output=raw_output,
        )
