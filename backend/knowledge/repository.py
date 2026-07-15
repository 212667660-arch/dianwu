from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.knowledge.models import (
    ImportJobStatus,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeCollectionDocument,
    KnowledgeDocument,
    KnowledgeImportJob,
    SessionKnowledgeCollection,
)
from backend.knowledge.schemas import KnowledgeChunkInput
from backend.services import db as session_repository


class StaleKnowledgeJob(RuntimeError):
    def __init__(self, job_id: int):
        super().__init__(f"knowledge import job {job_id} has changed")
        self.job_id = job_id


class KnowledgeRecordNotFound(LookupError):
    pass


class KnowledgeRepository:
    def __init__(self, db: Session, knowledge_root: Path | None = None) -> None:
        self.db = db
        self.knowledge_root = Path(knowledge_root) if knowledge_root is not None else None

    def create_collection(
        self,
        name: str,
        description: str = "",
        color: str = "#c98f65",
    ) -> KnowledgeCollection:
        collection = KnowledgeCollection(
            name=name.strip(),
            description=description.strip(),
            color=color.lower(),
        )
        self.db.add(collection)
        self.db.commit()
        self.db.refresh(collection)
        return collection

    def update_collection(
        self,
        collection_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        color: str | None = None,
    ) -> KnowledgeCollection:
        collection = self.require_collection(collection_id)
        if name is not None:
            collection.name = name.strip()
        if description is not None:
            collection.description = description.strip()
        if color is not None:
            collection.color = color.lower()
        collection.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(collection)
        return collection

    def delete_collection(self, collection_id: int) -> bool:
        collection = self.db.get(KnowledgeCollection, collection_id)
        if collection is None:
            return False
        self.db.delete(collection)
        self.db.commit()
        return True

    def require_collection(self, collection_id: int) -> KnowledgeCollection:
        collection = self.db.get(KnowledgeCollection, collection_id)
        if collection is None:
            raise KnowledgeRecordNotFound(f"knowledge collection {collection_id} was not found")
        return collection

    def upsert_document(
        self,
        *,
        sha256: str,
        display_name: str,
        extension: str,
        mime_type: str,
        byte_size: int,
        object_relpath: str,
    ) -> KnowledgeDocument:
        existing = self.db.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.sha256 == sha256)
        )
        if existing is not None:
            return existing
        document = KnowledgeDocument(
            sha256=sha256,
            display_name=display_name,
            extension=extension,
            mime_type=mime_type,
            byte_size=byte_size,
            object_relpath=object_relpath,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def require_document(self, document_id: int) -> KnowledgeDocument:
        document = self.db.get(KnowledgeDocument, document_id)
        if document is None:
            raise KnowledgeRecordNotFound(f"knowledge document {document_id} was not found")
        return document

    def link_document(self, collection_id: int, document_id: int) -> KnowledgeCollectionDocument:
        self.require_collection(collection_id)
        self.require_document(document_id)
        existing = self.db.scalar(
            select(KnowledgeCollectionDocument).where(
                KnowledgeCollectionDocument.collection_id == collection_id,
                KnowledgeCollectionDocument.document_id == document_id,
            )
        )
        if existing is not None:
            return existing
        link = KnowledgeCollectionDocument(
            collection_id=collection_id,
            document_id=document_id,
        )
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        return link

    def unlink_document(self, collection_id: int, document_id: int) -> bool:
        result = self.db.execute(
            delete(KnowledgeCollectionDocument).where(
                KnowledgeCollectionDocument.collection_id == collection_id,
                KnowledgeCollectionDocument.document_id == document_id,
            )
        )
        self.db.commit()
        return bool(result.rowcount)

    def collection_document_ids(self, collection_id: int) -> list[int]:
        return list(
            self.db.scalars(
                select(KnowledgeCollectionDocument.document_id)
                .where(KnowledgeCollectionDocument.collection_id == collection_id)
                .order_by(KnowledgeCollectionDocument.document_id)
            )
        )

    def ensure_session(self, session_id: str):
        return session_repository.get_or_create_session(self.db, session_id)

    def replace_session_collections(
        self,
        session_id: str,
        collection_ids: Iterable[int],
        *,
        privacy_mode: str = "allow_model_context",
    ) -> list[int]:
        self.ensure_session(session_id)
        normalized = sorted(set(collection_ids))
        if normalized:
            found = set(
                self.db.scalars(
                    select(KnowledgeCollection.id).where(KnowledgeCollection.id.in_(normalized))
                )
            )
            missing = set(normalized) - found
            if missing:
                raise KnowledgeRecordNotFound(
                    f"knowledge collections were not found: {sorted(missing)}"
                )
        self.db.execute(
            delete(SessionKnowledgeCollection).where(
                SessionKnowledgeCollection.session_id == session_id
            )
        )
        self.db.add_all(
            SessionKnowledgeCollection(
                session_id=session_id,
                collection_id=collection_id,
                privacy_mode=privacy_mode,
            )
            for collection_id in normalized
        )
        self.db.commit()
        return normalized

    def bound_collection_ids(self, session_id: str) -> list[int]:
        return list(
            self.db.scalars(
                select(SessionKnowledgeCollection.collection_id)
                .where(SessionKnowledgeCollection.session_id == session_id)
                .order_by(SessionKnowledgeCollection.collection_id)
            )
        )

    def create_job(self, document_id: int) -> KnowledgeImportJob:
        self.require_document(document_id)
        job = KnowledgeImportJob(document_id=document_id)
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def require_job(self, job_id: int) -> KnowledgeImportJob:
        job = self.db.get(KnowledgeImportJob, job_id)
        if job is None:
            raise KnowledgeRecordNotFound(f"knowledge import job {job_id} was not found")
        return job

    def transition_job(
        self,
        job_id: int,
        *,
        expected_version: int,
        status: ImportJobStatus,
        progress: int,
        stage: str | None = None,
        retryable: bool = False,
        safe_error_code: str | None = None,
    ) -> KnowledgeImportJob:
        result = self.db.execute(
            update(KnowledgeImportJob)
            .where(
                KnowledgeImportJob.id == job_id,
                KnowledgeImportJob.version == expected_version,
            )
            .values(
                status=status.value,
                progress=max(0, min(progress, 100)),
                stage=stage or status.value.lower(),
                retryable=retryable,
                safe_error_code=safe_error_code,
                version=KnowledgeImportJob.version + 1,
                updated_at=datetime.utcnow(),
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.db.rollback()
            raise StaleKnowledgeJob(job_id)
        self.db.commit()
        self.db.expire_all()
        return self.require_job(job_id)

    def request_cancel(self, job_id: int) -> KnowledgeImportJob:
        job = self.require_job(job_id)
        if job.cancel_requested:
            return job
        job.cancel_requested = True
        job.version += 1
        job.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(job)
        return job

    def replace_chunks(
        self,
        document_id: int,
        chunks: Sequence[KnowledgeChunkInput],
    ) -> list[KnowledgeChunk]:
        document = self.require_document(document_id)
        self.db.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
        )
        values = [
            KnowledgeChunk(document_id=document_id, **chunk.model_dump())
            for chunk in chunks
        ]
        self.db.add_all(values)
        document.chunk_count = len(values)
        document.text_characters = sum(len(chunk.text) for chunk in chunks)
        document.parser_version = chunks[0].parser_version if chunks else None
        self.db.commit()
        return values

    def referenced_hashes(self) -> set[str]:
        return set(
            self.db.scalars(
                select(KnowledgeDocument.sha256).where(
                    KnowledgeDocument.deleted_pending.is_(False)
                )
            )
        )
