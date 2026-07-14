from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

LEVELS = {"入门", "基础", "中等", "熟练", "未明确"}
STYLES = {"视觉型", "听觉型", "动觉型", "读写型", "复合型", "未明确"}
COGNITIVE_LEVELS = {"记忆", "理解", "应用", "分析", "评价", "创造", "未明确"}
DIFFICULTIES = {"基础", "提高", "挑战"}


class DiagnosisDecision(BaseModel):
    status: str
    current_turn: int = Field(ge=1, le=5)
    confirmed_fields: list[str]
    missing_fields: list[str]
    confidence: float = Field(ge=0, le=1)
    next_question: str
    reason: str = Field(min_length=1, max_length=120)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in {"CONTINUE", "COMPLETE"}:
            raise ValueError("状态必须为 CONTINUE 或 COMPLETE")
        return value


class LearnerProfile(BaseModel):
    profile_version: int = Field(ge=1)
    grade: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=80)
    current_level: str
    weaknesses: list[str]
    learning_style: str
    style_evidence: str = Field(min_length=1, max_length=200)
    cognitive_level: str
    goal: str = Field(min_length=1, max_length=300)
    recommended_difficulties: list[str]
    confidence: float = Field(ge=0, le=1)
    pending_question: str = Field(min_length=1, max_length=300)

    @field_validator("current_level")
    @classmethod
    def validate_level(cls, value: str) -> str:
        if value not in LEVELS:
            raise ValueError("当前水平非法")
        return value

    @field_validator("learning_style")
    @classmethod
    def validate_style(cls, value: str) -> str:
        if value not in STYLES:
            raise ValueError("学习风格非法")
        return value

    @field_validator("cognitive_level")
    @classmethod
    def validate_cognitive_level(cls, value: str) -> str:
        if value not in COGNITIVE_LEVELS:
            raise ValueError("认知层次非法")
        return value

    @field_validator("recommended_difficulties")
    @classmethod
    def validate_difficulties(cls, value: list[str]) -> list[str]:
        if not value or any(item not in DIFFICULTIES for item in value):
            raise ValueError("推荐难度非法")
        return value


class PracticeQuestion(BaseModel):
    ordinal: int = Field(ge=1)
    difficulty: str
    prompt: str = Field(min_length=1, max_length=4000)
    answer: str = Field(min_length=1, max_length=4000)
    explanation: str = Field(min_length=1, max_length=8000)

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, value: str) -> str:
        if value not in DIFFICULTIES:
            raise ValueError("练习题难度非法")
        return value


class LearningResource(BaseModel):
    topic: str = Field(min_length=1, max_length=128)
    profile_version: int = Field(ge=1)
    resource_types: list[str]
    difficulties: list[str]
    content: str = Field(min_length=1, max_length=30000)
    questions: list[PracticeQuestion] = Field(default_factory=list)

    @field_validator("resource_types")
    @classmethod
    def validate_types(cls, value: list[str]) -> list[str]:
        allowed = {"笔记", "练习"}
        if not value or any(item not in allowed for item in value):
            raise ValueError("资源类型非法")
        return value

    @field_validator("difficulties")
    @classmethod
    def validate_resource_difficulties(cls, value: list[str]) -> list[str]:
        if not value or any(item not in DIFFICULTIES for item in value):
            raise ValueError("目标难度非法")
        return value
