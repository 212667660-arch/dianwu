from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.database import Base


class ImportJobStatus(StrEnum):
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    PARSING = "PARSING"
    OCR_REQUIRED = "OCR_REQUIRED"
    OCR_RUNNING = "OCR_RUNNING"
    INDEXING = "INDEXING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sha256 = Column(String(64), unique=True, index=True, nullable=False)
    display_name = Column(String(255), nullable=False)
    extension = Column(String(12), nullable=False)
    mime_type = Column(String(128), nullable=False)
    byte_size = Column(Integer, nullable=False)
    object_relpath = Column(String(160), unique=True, nullable=False)
    parser_version = Column(String(32), nullable=True)
    status = Column(String(32), nullable=False, default=ImportJobStatus.QUEUED.value)
    page_count = Column(Integer, nullable=True)
    sheet_count = Column(Integer, nullable=True)
    slide_count = Column(Integer, nullable=True)
    text_characters = Column(Integer, nullable=False, default=0)
    chunk_count = Column(Integer, nullable=False, default=0)
    safe_error_code = Column(String(64), nullable=True)
    deleted_pending = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    collection_links = relationship(
        "KnowledgeCollectionDocument",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    chunks = relationship(
        "KnowledgeChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="KnowledgeChunk.ordinal",
    )
    jobs = relationship(
        "KnowledgeImportJob",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="KnowledgeImportJob.id",
    )


class KnowledgeCollection(Base):
    __tablename__ = "knowledge_collections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(80), unique=True, nullable=False)
    description = Column(String(500), nullable=False, default="")
    color = Column(String(7), nullable=False, default="#c98f65")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    document_links = relationship(
        "KnowledgeCollectionDocument",
        back_populates="collection",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    session_links = relationship(
        "SessionKnowledgeCollection",
        back_populates="collection",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class KnowledgeCollectionDocument(Base):
    __tablename__ = "knowledge_collection_documents"
    __table_args__ = (
        UniqueConstraint("collection_id", "document_id", name="uq_knowledge_collection_document"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    collection_id = Column(
        Integer,
        ForeignKey("knowledge_collections.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    document_id = Column(
        Integer,
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    collection = relationship("KnowledgeCollection", back_populates="document_links")
    document = relationship("KnowledgeDocument", back_populates="collection_links")


class SessionKnowledgeCollection(Base):
    __tablename__ = "session_knowledge_collections"
    __table_args__ = (
        UniqueConstraint("session_id", "collection_id", name="uq_session_knowledge_collection"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String(64),
        ForeignKey("chat_sessions.session_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    collection_id = Column(
        Integer,
        ForeignKey("knowledge_collections.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    privacy_mode = Column(String(32), nullable=False, default="allow_model_context")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    collection = relationship("KnowledgeCollection", back_populates="session_links")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "ordinal",
            "parser_version",
            name="uq_knowledge_chunk_version",
        ),
        Index("ix_knowledge_chunks_document_version", "document_id", "parser_version"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        Integer,
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    ordinal = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    text_sha256 = Column(String(64), nullable=False)
    heading_path = Column(Text, nullable=False, default="")
    locator_type = Column(String(24), nullable=False)
    locator_start = Column(Integer, nullable=False)
    locator_end = Column(Integer, nullable=False)
    sheet_name = Column(String(128), nullable=True)
    token_estimate = Column(Integer, nullable=False)
    parser_version = Column(String(32), nullable=False)

    document = relationship("KnowledgeDocument", back_populates="chunks")


class KnowledgeImportJob(Base):
    __tablename__ = "knowledge_import_jobs"
    __table_args__ = (
        Index("ix_knowledge_jobs_status_updated", "status", "updated_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        Integer,
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status = Column(String(32), nullable=False, default=ImportJobStatus.QUEUED.value)
    progress = Column(Integer, nullable=False, default=0)
    stage = Column(String(64), nullable=False, default="queued")
    retryable = Column(Boolean, nullable=False, default=False)
    safe_error_code = Column(String(64), nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    document = relationship("KnowledgeDocument", back_populates="jobs")
