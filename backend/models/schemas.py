from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.services.model_capabilities import ReasoningAdapter, ReasoningEffort
from backend.services.content_safety.models import SafetyMetadata

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class KnowledgeScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: Optional[int] = Field(default=None, ge=1)
    page_start: Optional[int] = Field(default=None, ge=1)
    page_end: Optional[int] = Field(default=None, ge=1)
    search_mode: Literal["focused", "expanded"] = "focused"

    @model_validator(mode="after")
    def validate_page_range(self) -> "KnowledgeScope":
        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("page_start and page_end must be provided together")
        if self.page_start is not None and self.page_end is not None:
            if self.page_end < self.page_start:
                raise ValueError("page_end precedes page_start")
            if self.page_end - self.page_start + 1 > 500:
                raise ValueError("page range exceeds 500 pages")
        return self

    def to_domain(self):
        from backend.knowledge.context import KnowledgeRetrievalScope

        return KnowledgeRetrievalScope(**self.model_dump())


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=8000)
    session_id: str = Field(default="default", min_length=1, max_length=64)
    request_id: Optional[str] = Field(default=None, max_length=64)
    resource_mode: Optional[Literal["bundle", "single"]] = Field(default=None)
    resource_type: Optional[Literal[
        "course_explanation",
        "mind_map",
        "question_bank",
        "extended_reading",
        "adaptive_practice",
    ]] = Field(default=None)
    knowledge_scope: Optional[KnowledgeScope] = None

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message 不能为空")
        return value

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        if not SESSION_ID_PATTERN.fullmatch(value):
            raise ValueError("session_id 只能包含字母、数字、下划线和连字符")
        return value

    @field_validator("resource_type")
    @classmethod
    def validate_resource_type(cls, value):
        if value is not None:
            allowed = {"course_explanation", "mind_map", "question_bank",
                       "extended_reading", "adaptive_practice"}
            if value not in allowed:
                raise ValueError("resource_type must be one of " + str(allowed))
        return value

    @model_validator(mode="after")
    def validate_resource_mode_requires_type(self):
        if self.resource_mode == "single" and not self.resource_type:
            raise ValueError("resource_type is required when resource_mode is single")
        if self.resource_mode != "single" and self.resource_type is not None:
            raise ValueError("resource_type is only accepted when resource_mode is single")
        return self


class ProfileRequest(BaseModel):
    messages: list[str] = Field(min_length=1, max_length=5)

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, value: list[str]) -> list[str]:
        result = [item.strip() for item in value]
        if any(not item for item in result):
            raise ValueError("messages 不能包含空文本")
        return result


class ProfileResponse(BaseModel):
    profile_text: str


class ResourceRequest(BaseModel):
    profile_text: str = Field(min_length=1, max_length=16000)
    message: str = Field(min_length=1, max_length=8000)
    use_web_search: bool = True


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query 不能为空")
        return value


class WebSearchResult(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=8, max_length=2048)
    snippet: str = Field(default="", max_length=1000)


class KnowledgeLocator(BaseModel):
    type: Literal["page", "slide", "sheet_rows", "paragraph"]
    start: int = Field(ge=1)
    end: int = Field(ge=1)
    sheet_name: Optional[str] = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_range(self) -> "KnowledgeLocator":
        if self.end < self.start:
            raise ValueError("knowledge locator end precedes start")
        if self.type == "sheet_rows" and not self.sheet_name:
            raise ValueError("sheet row locator requires sheet_name")
        if self.type != "sheet_rows" and self.sheet_name is not None:
            raise ValueError("only sheet row locators accept sheet_name")
        return self


class KnowledgeSourceResult(BaseModel):
    reference_id: str = Field(pattern=r"^资料[1-9]\d{0,2}$")
    document_id: int = Field(ge=1)
    document_name: str = Field(min_length=1, max_length=255)
    locator_label: str = Field(min_length=1, max_length=160)
    locator: KnowledgeLocator
    chunk_id: int = Field(ge=1)
    retrieval_mode: Literal["keyword", "hybrid"]


class ResourceArtifactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    type: Literal[
        "course_explanation",
        "mind_map",
        "question_bank",
        "extended_reading",
        "adaptive_practice",
    ]
    title: str
    status: Literal["SUCCEEDED", "FAILED", "CANCELLED"]
    body: str = ""
    type_specific_data: dict[str, Any] = Field(default_factory=dict)
    quality_score: float = 0.0
    quality_issues: list[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    retryable: bool = False
    safety: Optional[SafetyMetadata] = None


class BundleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    protocol_version: Literal["learning-resource-bundle/v2"]
    topic: str
    profile_version: int
    learning_state_version: str
    mode: Literal["bundle", "single"]
    status: Literal["COMPLETED", "PARTIAL", "FAILED", "CANCELLED"]
    requested_types: list[Literal[
        "course_explanation",
        "mind_map",
        "question_bank",
        "extended_reading",
        "adaptive_practice",
    ]]
    artifacts: list[ResourceArtifactResponse] = Field(default_factory=list)
    aggregate_quality: float = 0.0
    created_at: str
    knowledge_sources: list[dict[str, Any]] = Field(default_factory=list)
    public_sources: list[dict[str, Any]] = Field(default_factory=list)
    evidence_status: Literal["grounded", "insufficient", "unavailable"] = "unavailable"
    knowledge_scope: Optional[dict[str, Any]] = None
    recovery_actions: list[Literal["retry", "expand_range"]] = Field(default_factory=list)


class RetryArtifactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=64)

    @field_validator("session_id")
    @classmethod
    def validate_retry_session_id(cls, value: str) -> str:
        if not SESSION_ID_PATTERN.fullmatch(value):
            raise ValueError("invalid session_id")
        return value


class RetryArtifactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle: BundleResponse


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply: str
    phase: Literal["diagnosis", "profile", "resource"]
    state: str
    profile_version: int = 0
    cached: bool = False
    sources: list[WebSearchResult] = Field(default_factory=list)
    knowledge_sources: list[KnowledgeSourceResult] = Field(default_factory=list)
    bundle: Optional[BundleResponse] = None
    evidence_status: Literal["grounded", "insufficient", "unavailable"] = "unavailable"
    knowledge_scope: Optional[dict[str, Any]] = None
    recovery_actions: list[Literal["retry", "expand_range"]] = Field(default_factory=list)


class WebSearchResponse(BaseModel):
    query: str
    results: list[WebSearchResult]


class ResourceResponse(BaseModel):
    resource_text: str
    sources: list[WebSearchResult] = Field(default_factory=list)
    knowledge_sources: list[KnowledgeSourceResult] = Field(default_factory=list)


class AnswerAttemptRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=8000)
    hint_count: int = Field(default=0, ge=0, le=20)
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("answer")
    @classmethod
    def strip_answer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("answer 不能为空")
        return value


class AnswerAttemptResponse(BaseModel):
    attempt_id: int
    question_id: int
    duplicate: bool
    correct: bool
    score: float
    submitted_answer: str
    expected_answer: str
    explanation: str
    feedback: str
    error_type: Optional[str] = None
    mastery_score: float
    mastery_label: str
    next_review_at: datetime


class KnowledgePointProgress(BaseModel):
    id: int
    name: str
    subject: str
    mastery_score: float
    mastery_label: str
    attempts: int
    correct_attempts: int
    correct_streak: int
    last_error_type: Optional[str] = None
    last_practiced_at: Optional[datetime] = None
    next_review_at: Optional[datetime] = None


class ProgressResponse(BaseModel):
    session_id: str
    learning_state_version: int
    total_attempts: int
    correct_attempts: int
    accuracy: float
    knowledge_points: list[KnowledgePointProgress]


class ReviewTaskResponse(BaseModel):
    id: int
    knowledge_point_id: int
    knowledge_point: str
    reason: str
    due_at: datetime
    interval_days: int
    status: str


class MistakeItemResponse(BaseModel):
    attempt_id: int
    question_id: int
    knowledge_point: str
    prompt: str
    submitted_answer: str
    expected_answer: str
    explanation: str
    error_type: Optional[str] = None
    created_at: datetime


class NextActionResponse(BaseModel):
    session_id: str
    action: str
    knowledge_point_id: Optional[int] = None
    knowledge_point: Optional[str] = None
    recommended_difficulty: str
    reason: str
    due_at: Optional[datetime] = None
    suggested_request: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    retryable: bool
    request_id: Optional[str] = None


class ModelSettingsUpdate(BaseModel):
    provider: Literal["openai", "anthropic"]
    api_key: str = Field(min_length=1, max_length=512)
    base_url: str = Field(min_length=8, max_length=512)
    model_name: str = Field(min_length=1, max_length=128)
    anthropic_version: str = Field(default="2023-06-01", min_length=1, max_length=32)
    request_timeout_seconds: float = Field(default=60.0, ge=5.0, le=300.0)

    @field_validator("api_key", "base_url", "model_name", "anthropic_version")
    @classmethod
    def strip_model_settings(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("模型配置不能为空")
        return value


class ModelSettingsResponse(BaseModel):
    provider: Literal["openai", "anthropic"]
    base_url: str
    model_name: str
    api_key_configured: bool
    api_key_hint: str
    anthropic_version: str
    request_timeout_seconds: float


class ModelConnectionTestResponse(BaseModel):
    provider: Literal["openai", "anthropic"]
    model_name: str
    status: Literal["connected"]
    latency_ms: int = Field(ge=0)


class ModelDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    provider_model_name: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=128)
    max_output_tokens: int = Field(default=4096, ge=512, le=32768)
    supported_reasoning_efforts: list[ReasoningEffort] = Field(
        min_length=1,
        max_length=6,
    )
    reasoning_adapter: ReasoningAdapter

    @field_validator("provider_model_name", "label")
    @classmethod
    def validate_model_text(cls, value: str) -> str:
        value = value.strip()
        if not value or any(character in value for character in "\0\r\n"):
            raise ValueError("模型字段包含不允许的控制字符")
        return value

    @field_validator("supported_reasoning_efforts")
    @classmethod
    def validate_reasoning_efforts(
        cls,
        value: list[ReasoningEffort],
    ) -> list[ReasoningEffort]:
        if "auto" not in value:
            raise ValueError("模型能力必须包含 auto 推理档位")
        if len(value) != len(set(value)):
            raise ValueError("模型推理档位不能重复")
        return value


class ModelProfileSecret(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    label: str = Field(min_length=1, max_length=64)
    enabled: bool = True
    provider: Literal["openai", "anthropic"]
    base_url: str = Field(min_length=8, max_length=512)
    api_key: str = Field(min_length=1, max_length=512, repr=False)
    anthropic_version: str = Field(default="2023-06-01", min_length=1, max_length=32)
    request_timeout_seconds: float = Field(default=60, ge=5, le=300)
    default_model_id: str = Field(min_length=1, max_length=128)
    models: list[ModelDefinition] = Field(min_length=1, max_length=64)

    @field_validator(
        "label",
        "base_url",
        "api_key",
        "anthropic_version",
        "default_model_id",
    )
    @classmethod
    def validate_profile_text(cls, value: str) -> str:
        value = value.strip()
        if not value or any(character in value for character in "\0\r\n"):
            raise ValueError("模型配置包含不允许的控制字符")
        return value

    @model_validator(mode="after")
    def validate_models(self) -> "ModelProfileSecret":
        model_ids = [model.id for model in self.models]
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("同一配置中的模型 ID 不能重复")
        if self.default_model_id not in model_ids:
            raise ValueError("默认模型必须存在于模型列表中")
        return self


class ModelRuntimeSnapshotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_profile_id: str | None = Field(default=None, min_length=1, max_length=64)
    auto_failover: bool = True
    fallback_profile_ids: list[str] = Field(default_factory=list, max_length=16)
    profiles: list[ModelProfileSecret] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_snapshot(self) -> "ModelRuntimeSnapshotInput":
        profile_ids = [profile.id for profile in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("配置 ID 不能重复")
        if not self.profiles:
            if self.default_profile_id is not None or self.fallback_profile_ids:
                raise ValueError("空配置快照不能指定默认或备用配置")
            return self
        if self.default_profile_id is None:
            raise ValueError("非空配置快照必须指定默认配置")
        profiles_by_id = {profile.id: profile for profile in self.profiles}
        default_profile = profiles_by_id.get(self.default_profile_id)
        if default_profile is None:
            raise ValueError("默认配置不存在")
        if not default_profile.enabled:
            raise ValueError("默认配置必须启用")
        if len(self.fallback_profile_ids) != len(set(self.fallback_profile_ids)):
            raise ValueError("备用配置 ID 不能重复")
        if self.default_profile_id in self.fallback_profile_ids:
            raise ValueError("默认配置不能重复出现在备用列表中")
        if any(profile_id not in profiles_by_id for profile_id in self.fallback_profile_ids):
            raise ValueError("备用配置不存在")
        return self


class ModelRuntimeProfileStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    profile_id: str
    enabled: bool
    needs_attention: bool
    circuit_state: Literal["closed", "open", "half_open"]
    cooldown_until: float
    consecutive_failures: int = Field(ge=0)


class ModelRuntimeStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    ready: bool
    default_profile_id: str | None
    auto_failover: bool
    fallback_profile_ids: tuple[str, ...]
    profiles: tuple[ModelRuntimeProfileStatusResponse, ...]


class SessionModelPreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_mode: Literal["auto", "manual"] = "auto"
    preferred_profile_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    model_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    reasoning_effort: ReasoningEffort = "auto"
    failover_override: Literal["inherit", "on", "off"] = "inherit"

    @model_validator(mode="after")
    def validate_manual_profile(self) -> "SessionModelPreferenceUpdate":
        if self.profile_mode == "manual" and self.preferred_profile_id is None:
            raise ValueError("手动模式必须指定模型配置")
        if self.profile_mode == "auto" and self.preferred_profile_id is not None:
            raise ValueError("自动模式不能指定模型配置")
        return self


class SessionModelPreferenceResponse(SessionModelPreferenceUpdate):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
