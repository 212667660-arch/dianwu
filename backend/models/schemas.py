from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str = Field(default="default", min_length=1, max_length=64)
    request_id: Optional[str] = Field(default=None, max_length=64)

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


class ChatResponse(BaseModel):
    reply: str
    phase: Literal["diagnosis", "profile", "resource"]
    state: str
    profile_version: int = 0
    cached: bool = False
    sources: list[WebSearchResult] = Field(default_factory=list)
    knowledge_sources: list[KnowledgeSourceResult] = Field(default_factory=list)


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
