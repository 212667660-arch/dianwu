from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_BATCH_BYTES = 500 * 1024 * 1024
MAX_BATCH_FILES = 50
_SAFE_DISPLAY_NAME = re.compile(r"^[^/\\\x00\r\n]{1,255}$")


class StrictKnowledgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImportManifest(StrictKnowledgeModel):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    display_name: str = Field(min_length=1, max_length=255)
    extension: Literal[".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".markdown", ".csv"]
    mime_type: str = Field(min_length=1, max_length=128)
    byte_size: int = Field(ge=1, le=MAX_FILE_BYTES)
    object_relpath: str = Field(pattern=r"^objects/[a-f0-9]{64}$")

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not _SAFE_DISPLAY_NAME.fullmatch(normalized):
            raise ValueError("display_name contains unsafe characters")
        return normalized

    @model_validator(mode="after")
    def object_name_matches_hash(self) -> "ImportManifest":
        if self.object_relpath != f"objects/{self.sha256}":
            raise ValueError("object_relpath must match sha256")
        return self


class ImportBatchRequest(StrictKnowledgeModel):
    collection_id: int = Field(ge=1)
    files: list[ImportManifest] = Field(min_length=1, max_length=MAX_BATCH_FILES)

    @model_validator(mode="after")
    def validate_batch(self) -> "ImportBatchRequest":
        if sum(item.byte_size for item in self.files) > MAX_BATCH_BYTES:
            raise ValueError("knowledge import batch exceeds 500 MiB")
        hashes = [item.sha256 for item in self.files]
        if len(hashes) != len(set(hashes)):
            raise ValueError("knowledge import batch contains duplicate objects")
        return self


class KnowledgeCollectionCreate(StrictKnowledgeModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    color: str = Field(default="#c98f65", pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("collection name is empty")
        return normalized


class KnowledgeCollectionUpdate(StrictKnowledgeModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class KnowledgeChunkInput(StrictKnowledgeModel):
    ordinal: int = Field(ge=0, le=100_000)
    text: str = Field(min_length=1, max_length=2_000_000)
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    heading_path: str = Field(default="", max_length=2_000)
    locator_type: Literal["page", "slide", "sheet_rows", "paragraph"]
    locator_start: int = Field(ge=1)
    locator_end: int = Field(ge=1)
    sheet_name: str | None = Field(default=None, max_length=128)
    token_estimate: int = Field(ge=1, le=2_000_000)
    parser_version: str = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_locator(self) -> "KnowledgeChunkInput":
        if self.locator_end < self.locator_start:
            raise ValueError("locator_end must not precede locator_start")
        if self.locator_type == "sheet_rows" and not self.sheet_name:
            raise ValueError("sheet_rows requires sheet_name")
        return self
