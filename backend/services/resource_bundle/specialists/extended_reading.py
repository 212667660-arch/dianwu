from __future__ import annotations

import re

from backend.protocols.v2.models import ArtifactType, ArtifactStatus, ResourceArtifact, ResourceBrief
from backend.services.resource_bundle.specialists.base import Specialist, SpecialistResult, build_specialist_prompt


class ExtendedReadingSpecialist(Specialist):
    @property
    def artifact_type(self) -> ArtifactType:
        return ArtifactType.EXTENDED_READING

    def build_prompt(
        self, brief: ResourceBrief, profile_text: str,
        learning_context: str, knowledge_context: str,
    ) -> list[dict[str, str]]:
        return build_specialist_prompt(
            artifact_type=self.artifact_type,
            static_instruction=(
                "只能引用 resource_specialist_data.brief.source_allowlist 中的资料 ID。"
                "若列表为空，必须声明“无可引用外部来源，以下基于已有知识。”\n"
                "请严格按照以下格式输出：\n"
                "## 延伸阅读\n（延伸阅读内容，引用资料需使用[资料N]标记）"
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
        if "## 延伸阅读" not in raw_output:
            return SpecialistResult(
                artifact=ResourceArtifact(
                    artifact_id=artifact_id,
                    type=self.artifact_type,
                    title="延伸阅读",
                    status=ArtifactStatus.FAILED,
                    body="",
                    error_code="MISSING_SECTION",
                    quality_score=0,
                ),
                raw_output=raw_output,
            )

        cited = set(re.findall(r"\[(资料\d+)\]", raw_output))
        unknown = sorted(cited - set(source_allowlist))
        if unknown:
            return SpecialistResult(
                artifact=ResourceArtifact(
                    artifact_id=artifact_id,
                    type=self.artifact_type,
                    title="延伸阅读",
                    status=ArtifactStatus.FAILED,
                    body="",
                    error_code="CITATION_NOT_ALLOWED",
                    quality_score=0,
                    quality_issues=[f"UNKNOWN_CITATION:{item}" for item in unknown],
                ),
                raw_output=raw_output,
            )
        if not source_allowlist and "无可引用外部来源" not in raw_output:
            return SpecialistResult(
                artifact=ResourceArtifact(
                    artifact_id=artifact_id,
                    type=self.artifact_type,
                    title="延伸阅读",
                    status=ArtifactStatus.FAILED,
                    body="",
                    error_code="MISSING_NO_SOURCE_DISCLOSURE",
                    quality_score=0,
                    quality_issues=["MISSING_NO_SOURCE_DISCLOSURE"],
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
