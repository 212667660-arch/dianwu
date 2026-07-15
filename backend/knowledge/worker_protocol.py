from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)


PROTOCOL_VERSION = "knowledge-worker/v1"
MAX_EVENT_BYTES = 2_100_000


class WorkerProtocolError(ValueError):
    pass


class StrictWorkerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkerRequest(StrictWorkerModel):
    version: Literal["knowledge-worker/v1"] = PROTOCOL_VERSION
    job_id: int = Field(ge=1)
    object_relpath: str = Field(pattern=r"^objects/[a-f0-9]{64}$")
    extension: Literal[".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".markdown", ".csv"]
    limits: dict[str, int | float] = Field(default_factory=dict, max_length=32)


class WorkerEventBase(StrictWorkerModel):
    version: Literal["knowledge-worker/v1"] = PROTOCOL_VERSION


class ProgressEvent(WorkerEventBase):
    type: Literal["progress"] = "progress"
    progress: int = Field(ge=0, le=100)
    stage: str = Field(min_length=1, max_length=64)


class BlockEvent(WorkerEventBase):
    type: Literal["block"] = "block"
    ordinal: int = Field(ge=0, le=100_000)
    text: str = Field(min_length=1, max_length=2_000_000)
    heading_path: list[str] = Field(default_factory=list, max_length=32)
    locator_type: Literal["page", "slide", "sheet_rows", "paragraph"]
    locator_start: int = Field(ge=1)
    locator_end: int = Field(ge=1)
    sheet_name: str | None = Field(default=None, max_length=128)

    @field_validator("heading_path")
    @classmethod
    def validate_headings(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 256 for item in value):
            raise ValueError("heading path contains an invalid item")
        return [item.strip() for item in value]

    @model_validator(mode="after")
    def validate_locator(self) -> "BlockEvent":
        if self.locator_end < self.locator_start:
            raise ValueError("locator end precedes start")
        if self.locator_type == "sheet_rows" and not self.sheet_name:
            raise ValueError("sheet row locator requires sheet_name")
        if self.locator_type != "sheet_rows" and self.sheet_name is not None:
            raise ValueError("only sheet rows accept sheet_name")
        return self


class DoneEvent(WorkerEventBase):
    type: Literal["done"] = "done"
    page_count: int | None = Field(default=None, ge=0, le=2_000)
    slide_count: int | None = Field(default=None, ge=0, le=10_000)
    sheet_count: int | None = Field(default=None, ge=0, le=100)
    text_characters: int = Field(ge=0, le=50_000_000)
    ocr_required: bool = False


class FailureEvent(WorkerEventBase):
    type: Literal["failure"] = "failure"
    code: str = Field(pattern=r"^KNOWLEDGE_[A-Z0-9_]{1,54}$")
    retryable: bool = False


WorkerEvent = Annotated[
    ProgressEvent | BlockEvent | DoneEvent | FailureEvent,
    Field(discriminator="type"),
]
_EVENT_ADAPTER = TypeAdapter(WorkerEvent)


def parse_worker_line(value: str | bytes) -> WorkerEvent:
    if isinstance(value, bytes):
        try:
            raw = value.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise WorkerProtocolError("worker event is not UTF-8") from exc
    elif isinstance(value, str):
        raw = value
    else:
        raise WorkerProtocolError("worker event must be text")
    if len(raw.encode("utf-8")) > MAX_EVENT_BYTES:
        raise WorkerProtocolError("worker event exceeds size limit")
    try:
        return _EVENT_ADAPTER.validate_json(raw)
    except Exception as exc:
        raise WorkerProtocolError("worker event is invalid") from exc


def encode_worker_event(event: WorkerEvent) -> str:
    return event.model_dump_json()
