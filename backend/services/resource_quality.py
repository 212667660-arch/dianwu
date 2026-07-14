from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from backend.errors import ProtocolValidationError
from backend.protocols import LearningResource


@dataclass(frozen=True)
class ResourceQualityResult:
    score: int
    issues: list[str]


def _normalized_prompt(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\W+", "", normalized)


def assess_resource_quality(resource: LearningResource) -> ResourceQualityResult:
    score = 100
    issues: list[str] = []
    covered_difficulties = {question.difficulty for question in resource.questions}
    for difficulty in resource.difficulties:
        if difficulty not in covered_difficulties:
            score -= 20
            issues.append(f"MISSING_DIFFICULTY:{difficulty}")
    if len(resource.questions) < 2:
        score -= 15
        issues.append("QUESTION_COUNT_LOW")
    prompts = [_normalized_prompt(question.prompt) for question in resource.questions]
    if len(prompts) != len(set(prompts)):
        score -= 25
        issues.append("DUPLICATE_QUESTION")
    note = resource.content.split("【学习笔记】", 1)[1].split("【分层练习:", 1)[0].strip()
    if len(note) < 20:
        score -= 10
        issues.append("NOTE_TOO_SHORT")
    return ResourceQualityResult(max(0, score), issues)


def validate_resource_quality(resource: LearningResource, minimum_score: int = 60) -> ResourceQualityResult:
    result = assess_resource_quality(resource)
    if result.score < minimum_score:
        raise ProtocolValidationError("RESOURCE_QUALITY_LOW", "学习资源未达到最低质量门槛。")
    return result
