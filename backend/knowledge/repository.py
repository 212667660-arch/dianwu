from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
import json
from pathlib import Path

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.knowledge.models import (
    ImportJobStatus,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeCollectionDocument,
    KnowledgeDocument,
    KnowledgeImportJob,
    KnowledgeWorkerBlock,
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


class KnowledgeRecordConflict(RuntimeError):
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
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise KnowledgeRecordConflict("knowledge collection name already exists") from exc
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
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise KnowledgeRecordConflict("knowledge collection name already exists") from exc
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

    def list_collections(self) -> list[KnowledgeCollection]:
        return list(
            self.db.scalars(
                select(KnowledgeCollection).order_by(
                    KnowledgeCollection.created_at,
                    KnowledgeCollection.id,
                )
            )
        )

    def collection_counts(self, collection_id: int) -> tuple[int, int]:
        documents = self.db.scalar(
            select(func.count(KnowledgeCollectionDocument.id)).where(
                KnowledgeCollectionDocument.collection_id == collection_id
            )
        )
        sessions = self.db.scalar(
            select(func.count(SessionKnowledgeCollection.id)).where(
                SessionKnowledgeCollection.collection_id == collection_id
            )
        )
        return int(documents or 0), int(sessions or 0)

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

    def create_import_jobs(
        self,
        collection_id: int,
        manifests: Sequence[Mapping[str, object]],
    ) -> list[KnowledgeImportJob]:
        self.require_collection(collection_id)
        jobs: list[KnowledgeImportJob] = []
        try:
            for manifest in manifests:
                digest = str(manifest["sha256"])
                document = self.db.scalar(
                    select(KnowledgeDocument).where(KnowledgeDocument.sha256 == digest)
                )
                if document is None:
                    document = KnowledgeDocument(**dict(manifest))
                    self.db.add(document)
                    self.db.flush()
                link = self.db.scalar(
                    select(KnowledgeCollectionDocument).where(
                        KnowledgeCollectionDocument.collection_id == collection_id,
                        KnowledgeCollectionDocument.document_id == document.id,
                    )
                )
                if link is None:
                    self.db.add(
                        KnowledgeCollectionDocument(
                            collection_id=collection_id,
                            document_id=document.id,
                        )
                    )
                job = KnowledgeImportJob(document_id=document.id)
                self.db.add(job)
                jobs.append(job)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        for job in jobs:
            self.db.refresh(job)
        return jobs

    def require_document(self, document_id: int) -> KnowledgeDocument:
        document = self.db.get(KnowledgeDocument, document_id)
        if document is None:
            raise KnowledgeRecordNotFound(f"knowledge document {document_id} was not found")
        return document

    def list_documents(
        self,
        *,
        collection_id: int | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[KnowledgeDocument]:
        statement = select(KnowledgeDocument).where(
            KnowledgeDocument.deleted_pending.is_(False)
        )
        if collection_id is not None:
            statement = statement.join(KnowledgeCollectionDocument).where(
                KnowledgeCollectionDocument.collection_id == collection_id
            )
        return list(
            self.db.scalars(
                statement.order_by(
                    KnowledgeDocument.created_at.desc(),
                    KnowledgeDocument.id.desc(),
                ).offset(offset).limit(limit)
            )
        )

    def delete_document_record(self, document_id: int, *, commit: bool = True) -> bool:
        document = self.db.get(KnowledgeDocument, document_id)
        if document is None:
            return False
        self.db.delete(document)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return True

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

    def session_privacy_mode(self, session_id: str) -> str:
        value = self.db.scalar(
            select(SessionKnowledgeCollection.privacy_mode)
            .where(SessionKnowledgeCollection.session_id == session_id)
            .limit(1)
        )
        return str(value or "allow_model_context")

    def list_jobs(self, *, limit: int = 100) -> list[KnowledgeImportJob]:
        return list(
            self.db.scalars(
                select(KnowledgeImportJob)
                .order_by(KnowledgeImportJob.created_at.desc(), KnowledgeImportJob.id.desc())
                .limit(limit)
            )
        )

    def active_job_ids(self, document_id: int) -> list[int]:
        active_statuses = {
            ImportJobStatus.QUEUED.value,
            ImportJobStatus.VALIDATING.value,
            ImportJobStatus.PARSING.value,
            ImportJobStatus.OCR_REQUIRED.value,
            ImportJobStatus.OCR_RUNNING.value,
            ImportJobStatus.INDEXING.value,
        }
        return list(
            self.db.scalars(
                select(KnowledgeImportJob.id)
                .where(
                    KnowledgeImportJob.document_id == document_id,
                    KnowledgeImportJob.status.in_(active_statuses),
                )
                .order_by(KnowledgeImportJob.id)
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

    def refresh_job(self, job_id: int) -> KnowledgeImportJob:
        self.db.expire_all()
        return self.require_job(job_id)

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
        current_page: int | None = None,
        page_count: int | None = None,
        eta_seconds: int | None = None,
        failed_pages: list[int] | None = None,
    ) -> KnowledgeImportJob:
        values: dict[str, object] = {
            "status": status.value,
            "progress": max(0, min(progress, 100)),
            "stage": stage or status.value.lower(),
            "retryable": retryable,
            "safe_error_code": safe_error_code,
            "version": KnowledgeImportJob.version + 1,
            "updated_at": datetime.utcnow(),
        }
        if current_page is not None:
            values["current_page"] = current_page
        if page_count is not None:
            values["page_count"] = page_count
        if eta_seconds is not None:
            values["eta_seconds"] = eta_seconds
        if failed_pages is not None:
            values["failed_pages_json"] = json.dumps(
                sorted(set(failed_pages)),
                separators=(",", ":"),
            )
        result = self.db.execute(
            update(KnowledgeImportJob)
            .where(
                KnowledgeImportJob.id == job_id,
                KnowledgeImportJob.version == expected_version,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.db.rollback()
            raise StaleKnowledgeJob(job_id)
        self.db.commit()
        self.db.expire_all()
        return self.require_job(job_id)

    def retry_page_numbers(self, job_id: int) -> list[int]:
        job = self.require_job(job_id)
        try:
            raw = json.loads(job.failed_pages_json or "[]")
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        return sorted(
            {
                int(item)
                for item in raw
                if isinstance(item, int) and 1 <= item <= 2_000
            }
        )

    def reset_job_for_retry(self, job_id: int) -> KnowledgeImportJob:
        job = self.require_job(job_id)
        if job.status not in {
            ImportJobStatus.FAILED.value,
            ImportJobStatus.OCR_REQUIRED.value,
            ImportJobStatus.INTERRUPTED.value,
        }:
            raise KnowledgeRecordConflict("knowledge import job is not retryable")
        job.status = ImportJobStatus.QUEUED.value
        job.progress = 0
        job.stage = "queued"
        job.retryable = False
        job.safe_error_code = None
        job.cancel_requested = False
        job.current_page = None
        job.eta_seconds = None
        job.version += 1
        job.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(job)
        return job

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

    def stage_worker_block(self, job_id: int, block) -> None:
        self.require_job(job_id)
        payload = block.model_dump(mode="json")
        existing = self.db.scalar(
            select(KnowledgeWorkerBlock).where(
                KnowledgeWorkerBlock.job_id == job_id,
                KnowledgeWorkerBlock.ordinal == block.ordinal,
            )
        )
        if existing is None:
            self.db.add(
                KnowledgeWorkerBlock(
                    job_id=job_id,
                    ordinal=block.ordinal,
                    payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                )
            )
        else:
            existing.payload_json = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        self.db.commit()

    def finish_worker_output(self, job_id: int, done) -> None:
        job = self.require_job(job_id)
        document = self.require_document(job.document_id)
        document.page_count = done.page_count
        document.slide_count = done.slide_count
        document.sheet_count = done.sheet_count
        if done.ocr_performed:
            document.text_characters = sum(
                len(block.text) for block in self.worker_block_events(job_id)
            )
        else:
            document.text_characters = done.text_characters
        self.db.commit()

    def clear_worker_output(self, job_id: int) -> None:
        self.db.execute(
            delete(KnowledgeWorkerBlock).where(KnowledgeWorkerBlock.job_id == job_id)
        )
        self.db.commit()

    def worker_block_events(self, job_id: int):
        from backend.knowledge.worker_protocol import BlockEvent

        rows = list(
            self.db.scalars(
                select(KnowledgeWorkerBlock)
                .where(KnowledgeWorkerBlock.job_id == job_id)
                .order_by(KnowledgeWorkerBlock.ordinal)
            )
        )
        return [BlockEvent.model_validate_json(row.payload_json) for row in rows]

    def mark_active_jobs_interrupted(self) -> int:
        active = {
            ImportJobStatus.QUEUED.value,
            ImportJobStatus.VALIDATING.value,
            ImportJobStatus.PARSING.value,
            ImportJobStatus.OCR_RUNNING.value,
            ImportJobStatus.INDEXING.value,
        }
        result = self.db.execute(
            update(KnowledgeImportJob)
            .where(KnowledgeImportJob.status.in_(active))
            .values(
                status=ImportJobStatus.INTERRUPTED.value,
                stage="interrupted",
                retryable=True,
                safe_error_code="KNOWLEDGE_IMPORT_INTERRUPTED",
                version=KnowledgeImportJob.version + 1,
                updated_at=datetime.utcnow(),
            )
            .execution_options(synchronize_session=False)
        )
        self.db.commit()
        return int(result.rowcount or 0)

    def mark_job_interrupted(self, job_id: int) -> bool:
        recoverable = {
            ImportJobStatus.QUEUED.value,
            ImportJobStatus.VALIDATING.value,
            ImportJobStatus.PARSING.value,
            ImportJobStatus.OCR_REQUIRED.value,
            ImportJobStatus.OCR_RUNNING.value,
            ImportJobStatus.INDEXING.value,
        }
        result = self.db.execute(
            update(KnowledgeImportJob)
            .where(
                KnowledgeImportJob.id == job_id,
                KnowledgeImportJob.status.in_(recoverable),
            )
            .values(
                status=ImportJobStatus.INTERRUPTED.value,
                stage="interrupted",
                retryable=True,
                safe_error_code="KNOWLEDGE_IMPORT_INTERRUPTED",
                version=KnowledgeImportJob.version + 1,
                updated_at=datetime.utcnow(),
            )
            .execution_options(synchronize_session=False)
        )
        self.db.commit()
        return result.rowcount == 1

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
