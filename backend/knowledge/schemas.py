from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_FILE_BYTES = 500 * 1024 * 1024
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


class CapabilityStatus(StrictKnowledgeModel):
    available: bool
    mode: str
    error_code: str | None = None
    version: str | None = None


class KnowledgeStatusResponse(StrictKnowledgeModel):
    fts: CapabilityStatus
    worker: CapabilityStatus
    ocr_pack: CapabilityStatus
    semantic_pack: CapabilityStatus


class TextbookCatalogItem(StrictKnowledgeModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")
    publisher: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    stage: Literal["初中", "高中"]
    grade: str = Field(min_length=1, max_length=40)
    semester: str = Field(min_length=1, max_length=40)
    subject: Literal["数学"]
    edition: str = Field(min_length=1, max_length=40)
    official_url: str = Field(min_length=1, max_length=512)
    access_mode: Literal["OFFICIAL_READER", "LICENSED_DOWNLOAD", "EXTERNAL_CATALOG"]
    license_note: str = Field(min_length=1, max_length=300)
    verified_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    download_url: str | None = Field(default=None, max_length=512)

    @field_validator("official_url", "download_url")
    @classmethod
    def validate_catalog_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("textbook URL must be a clean HTTPS URL")
        if (parsed.hostname or "").lower() not in {"jc.pep.com.cn", "book.pep.com.cn"}:
            raise ValueError("textbook URL host is not approved")
        return value

    @model_validator(mode="after")
    def validate_access_mode(self) -> "TextbookCatalogItem":
        if self.publisher == "人民教育出版社" and (
            self.access_mode == "LICENSED_DOWNLOAD" or self.download_url is not None
        ):
            raise ValueError("PEP textbooks are official-reader metadata only")
        if self.access_mode == "LICENSED_DOWNLOAD" and self.download_url is None:
            raise ValueError("licensed downloads require download_url")
        if self.access_mode != "LICENSED_DOWNLOAD" and self.download_url is not None:
            raise ValueError("only licensed downloads may expose download_url")
        return self


class TextbookCatalogResponse(StrictKnowledgeModel):
    version: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    items: list[TextbookCatalogItem]


class KnowledgeCollectionResponse(StrictKnowledgeModel):
    id: int
    name: str
    description: str
    color: str
    document_count: int
    bound_session_count: int
    created_at: str
    updated_at: str


class KnowledgeDocumentResponse(StrictKnowledgeModel):
    id: int
    sha256: str
    display_name: str
    extension: str
    mime_type: str
    byte_size: int
    status: str
    page_count: int | None
    slide_count: int | None
    sheet_count: int | None
    text_characters: int
    chunk_count: int
    parser_version: str | None
    safe_error_code: str | None
    created_at: str
    updated_at: str


class KnowledgeImportJobResponse(StrictKnowledgeModel):
    id: int
    document_id: int
    status: str
    progress: int
    stage: str
    retryable: bool
    safe_error_code: str | None
    cancel_requested: bool
    version: int
    created_at: str
    updated_at: str


class ImportBatchResponse(StrictKnowledgeModel):
    jobs: list[KnowledgeImportJobResponse]


class KnowledgeSearchRequest(StrictKnowledgeModel):
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    query: str = Field(min_length=1, max_length=4_000)
    limit: int = Field(default=8, ge=1, le=30)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("knowledge query is empty")
        return normalized


class KnowledgeLocatorResponse(StrictKnowledgeModel):
    type: Literal["page", "slide", "sheet_rows", "paragraph"]
    start: int
    end: int
    sheet_name: str | None = None


class KnowledgeSearchItem(StrictKnowledgeModel):
    chunk_id: int
    document_id: int
    document_name: str
    text: str
    heading_path: str
    locator: KnowledgeLocatorResponse
    score: float
    retrieval_mode: Literal["keyword", "hybrid"]


class KnowledgeSearchResponse(StrictKnowledgeModel):
    mode: Literal["keyword", "hybrid"]
    items: list[KnowledgeSearchItem]


class SessionKnowledgeCollectionsUpdate(StrictKnowledgeModel):
    collection_ids: list[int] = Field(max_length=64)
    privacy_mode: Literal["allow_model_context", "local_search_only"] = "allow_model_context"

    @field_validator("collection_ids")
    @classmethod
    def validate_collection_ids(cls, value: list[int]) -> list[int]:
        if any(not isinstance(item, int) or item < 1 for item in value):
            raise ValueError("collection IDs must be positive integers")
        if len(value) != len(set(value)):
            raise ValueError("collection IDs must be unique")
        return value


class SessionKnowledgeCollectionsResponse(StrictKnowledgeModel):
    session_id: str
    collection_ids: list[int]
    privacy_mode: Literal["allow_model_context", "local_search_only"]
