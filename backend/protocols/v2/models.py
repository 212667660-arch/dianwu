from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ArtifactType(str, Enum):
    COURSE_EXPLANATION = "course_explanation"
    MIND_MAP = "mind_map"
    QUESTION_BANK = "question_bank"
    EXTENDED_READING = "extended_reading"
    ADAPTIVE_PRACTICE = "adaptive_practice"


class ArtifactStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ResourceMode(str, Enum):
    BUNDLE = "bundle"
    SINGLE = "single"


class BundleStatus(str, Enum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SubjectCategory(str, Enum):
    MATH = "math"
    PHYSICS = "physics"
    CHEMISTRY = "chemistry"
    BIOLOGY = "biology"
    CS = "cs"
    LITERATURE = "literature"
    HISTORY = "history"
    GEOGRAPHY = "geography"
    ENGLISH = "english"
    POLITICS = "politics"
    OTHER = "other"


class ResourceBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, max_length=200)
    learning_objectives: list[str] = Field(min_length=1, max_length=10)
    target_difficulty: str = Field(min_length=1, max_length=20)
    weak_knowledge_points: list[str] = Field(default_factory=list, max_length=20)
    style_constraints: str = Field(default="", max_length=500)
    source_allowlist: list[str] = Field(default_factory=list, max_length=50)
    subject_category: SubjectCategory

    @field_validator("learning_objectives")
    @classmethod
    def validate_learning_objectives(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("learning_objectives must contain at least one item")
        if any(not item or not item.strip() for item in value):
            raise ValueError("each learning_objective must be a non-empty string")
        return value


class ResourceArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1, max_length=64)
    type: ArtifactType
    title: str = Field(min_length=1, max_length=300)
    status: ArtifactStatus
    body: str = Field(default="", max_length=100000)
    type_specific_data: dict[str, Any] = Field(default_factory=dict)
    quality_score: int = Field(ge=0, le=100)
    quality_issues: list[str] = Field(default_factory=list)
    error_code: Optional[str] = Field(default=None, max_length=100)
    retryable: bool = False


class ResourceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(min_length=1, max_length=64)
    protocol_version: Literal["learning-resource-bundle/v2"] = "learning-resource-bundle/v2"
    topic: str = Field(min_length=1, max_length=200)
    profile_version: int = Field(ge=1)
    learning_state_version: str = Field(min_length=1, max_length=128)
    mode: ResourceMode
    status: BundleStatus
    requested_types: list[ArtifactType] = Field(min_length=1, max_length=5)
    artifacts: list[ResourceArtifact] = Field(min_length=1, max_length=5)
    aggregate_quality: float = Field(ge=0.0, le=100.0)
    created_at: str = Field(min_length=1, max_length=64)
    knowledge_sources: list[dict[str, Any]] = Field(default_factory=list)
    public_sources: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_catalog(self) -> "ResourceBundle":
        if len(self.requested_types) != len(set(self.requested_types)):
            raise ValueError("requested_types must be unique")
        artifact_types = [artifact.type for artifact in self.artifacts]
        if len(artifact_types) != len(set(artifact_types)):
            raise ValueError("artifact types must be unique")
        if set(artifact_types) != set(self.requested_types):
            raise ValueError("artifact types must exactly match requested_types")
        if self.mode == ResourceMode.SINGLE and len(self.requested_types) != 1:
            raise ValueError("single mode requires exactly one requested type")
        return self
