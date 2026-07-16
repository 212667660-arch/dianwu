from __future__ import annotations

import abc
from dataclasses import dataclass

from backend.protocols.v2.models import ArtifactType, ArtifactStatus, ResourceArtifact, ResourceBrief


@dataclass
class SpecialistResult:
    artifact: ResourceArtifact
    raw_output: str


class Specialist(abc.ABC):
    @abc.abstractmethod
    def build_prompt(
        self, brief: ResourceBrief, profile_text: str,
        learning_context: str, knowledge_context: str,
    ) -> list[dict[str, str]]:
        ...

    @abc.abstractmethod
    def parse(self, raw_output: str, artifact_id: str) -> SpecialistResult:
        ...

    @property
    @abc.abstractmethod
    def artifact_type(self) -> ArtifactType:
        ...


def build_specialist_messages(
    artifact_type: ArtifactType,
    brief: ResourceBrief,
    profile_text: str,
    learning_context: str,
    knowledge_context: str,
) -> list[dict[str, str]]:
    system_msg = (
        f"你是一位专业的教育资源生成专家，负责生成类型为 {artifact_type.value} 的学习资源。\n"
        f"请严格按照以下信息生成内容：\n"
        f"主题：{brief.topic}\n"
        f"学习目标：{''.join(brief.learning_objectives)}\n"
        f"目标难度：{brief.target_difficulty}\n"
        f"薄弱知识点：{''.join(brief.weak_knowledge_points) if brief.weak_knowledge_points else '无'}\n"
        f"风格约束：{brief.style_constraints or '无特殊约束'}\n"
        f"学科类别：{brief.subject_category.value}\n"
    )
    user_msg = (
        f"学习者画像：{profile_text}\n"
        f"学习上下文：{learning_context}\n"
        f"知识上下文：{knowledge_context}\n"
        f"请生成 {artifact_type.value} 类型的资源。"
    )
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


_SPECIALIST_MAP: dict[ArtifactType, Specialist] = {}

def specialist_for_type(artifact_type: ArtifactType) -> Specialist:
    if not _SPECIALIST_MAP:
        _init_specialist_map()
    return _SPECIALIST_MAP[artifact_type]


def _init_specialist_map() -> None:
    from backend.services.resource_bundle.specialists.course_explanation import CourseExplanationSpecialist
    from backend.services.resource_bundle.specialists.mind_map import MindMapSpecialist
    from backend.services.resource_bundle.specialists.question_bank import QuestionBankSpecialist
    from backend.services.resource_bundle.specialists.extended_reading import ExtendedReadingSpecialist
    from backend.services.resource_bundle.specialists.adaptive_practice import AdaptivePracticeSpecialist

    _SPECIALIST_MAP[ArtifactType.COURSE_EXPLANATION] = CourseExplanationSpecialist()
    _SPECIALIST_MAP[ArtifactType.MIND_MAP] = MindMapSpecialist()
    _SPECIALIST_MAP[ArtifactType.QUESTION_BANK] = QuestionBankSpecialist()
    _SPECIALIST_MAP[ArtifactType.EXTENDED_READING] = ExtendedReadingSpecialist()
    _SPECIALIST_MAP[ArtifactType.ADAPTIVE_PRACTICE] = AdaptivePracticeSpecialist()
