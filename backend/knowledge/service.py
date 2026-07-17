from __future__ import annotations

import asyncio
from datetime import datetime
from hashlib import sha256
import json
from typing import Callable

from backend.errors import (
    KnowledgeCollectionConflictError,
    KnowledgeFileSignatureMismatchError,
    KnowledgeImportNotRetryableError,
    KnowledgeIndexUnavailableError,
    KnowledgeObjectMissingError,
    ResourceNotFoundError,
)
from backend.knowledge.models import ImportJobStatus
from backend.knowledge.ocr_engine import rapidocr_available, rapidocr_version
from backend.knowledge.optional_packs import CapabilityRegistry
from backend.knowledge.repository import (
    KnowledgeRecordConflict,
    KnowledgeRecordNotFound,
    KnowledgeRepository,
)
from backend.knowledge.schemas import (
    ImportBatchRequest,
    KnowledgeBulkRequest,
    KnowledgeCollectionCreate,
    KnowledgeCollectionUpdate,
    KnowledgeSearchRequest,
    SessionKnowledgeCollectionsUpdate,
)
from backend.knowledge.search import (
    KnowledgeSearchRepository,
    KnowledgeUnavailable,
    knowledge_fts_available,
)


def _iso(value: datetime) -> str:
    return value.isoformat() + "Z"


def _stream_sha256(path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class KnowledgeService:
    def __init__(
        self,
        repository: KnowledgeRepository,
        object_store,
        search_repository,
        coordinator,
        session_factory: Callable[[], object] | None = None,
    ) -> None:
        self.repository = repository
        self.object_store = object_store
        self.search_repository = search_repository
        self.coordinator = coordinator
        self.session_factory = session_factory

    def _with_fresh_repository(self, operation):
        if self.session_factory is None:
            return operation(self.repository)
        db = self.session_factory()
        try:
            repository = KnowledgeRepository(db, self.repository.knowledge_root)
            return operation(repository)
        finally:
            db.close()

    def status(self) -> dict[str, object]:
        fts = knowledge_fts_available()
        if not fts:
            try:
                self.search_repository.ensure_schema()
                fts = True
            except KnowledgeUnavailable:
                fts = False
        capabilities = CapabilityRegistry()
        if self.repository.knowledge_root is not None:
            packs_root = self.repository.knowledge_root / "packs"
            for kind in ("ocr", "semantic"):
                pack_root = packs_root / kind
                if pack_root.is_dir():
                    capabilities.load_pack(pack_root)
        if not capabilities.ocr.available and rapidocr_available():
            capabilities.ocr = type(capabilities.ocr)(
                True,
                "builtin",
                None,
                rapidocr_version(),
            )

        def capability_payload(state) -> dict[str, object]:
            return {
                "available": state.available,
                "mode": state.mode,
                "error_code": state.error_code,
                "version": state.version,
            }

        return {
            "fts": {
                "available": fts,
                "mode": "keyword" if fts else "unavailable",
                "error_code": None if fts else "KNOWLEDGE_INDEX_UNAVAILABLE",
                "version": None,
            },
            "worker": {
                "available": True,
                "mode": "isolated",
                "error_code": None,
                "version": None,
            },
            "ocr_pack": capability_payload(capabilities.ocr),
            "semantic_pack": capability_payload(capabilities.semantic),
        }

    def _collection_response(self, collection) -> dict[str, object]:
        document_count, session_count = self.repository.collection_counts(collection.id)
        return {
            "id": collection.id,
            "name": collection.name,
            "description": collection.description,
            "color": collection.color,
            "document_count": document_count,
            "bound_session_count": session_count,
            "created_at": _iso(collection.created_at),
            "updated_at": _iso(collection.updated_at),
        }

    def list_collections(self) -> list[dict[str, object]]:
        return [
            self._collection_response(collection)
            for collection in self.repository.list_collections()
        ]

    def get_collection(self, collection_id: int) -> dict[str, object]:
        try:
            collection = self.repository.require_collection(collection_id)
        except KnowledgeRecordNotFound as exc:
            raise ResourceNotFoundError(
                "KNOWLEDGE_COLLECTION_NOT_FOUND",
                "知识库集合不存在。",
            ) from exc
        return self._collection_response(collection)

    def create_collection(self, value: KnowledgeCollectionCreate) -> dict[str, object]:
        try:
            collection = self.repository.create_collection(
                value.name,
                value.description,
                value.color,
            )
        except KnowledgeRecordConflict as exc:
            raise KnowledgeCollectionConflictError() from exc
        return self._collection_response(collection)

    def update_collection(
        self,
        collection_id: int,
        value: KnowledgeCollectionUpdate,
    ) -> dict[str, object]:
        try:
            collection = self.repository.update_collection(
                collection_id,
                **value.model_dump(exclude_none=True),
            )
        except KnowledgeRecordNotFound as exc:
            raise ResourceNotFoundError(
                "KNOWLEDGE_COLLECTION_NOT_FOUND",
                "知识库集合不存在。",
            ) from exc
        except KnowledgeRecordConflict as exc:
            raise KnowledgeCollectionConflictError() from exc
        return self._collection_response(collection)

    def delete_collection(self, collection_id: int) -> None:
        if not self.repository.delete_collection(collection_id):
            raise ResourceNotFoundError(
                "KNOWLEDGE_COLLECTION_NOT_FOUND",
                "知识库集合不存在。",
            )

    def _document_response(self, document) -> dict[str, object]:
        return {
            "id": document.id,
            "sha256": document.sha256,
            "display_name": document.display_name,
            "extension": document.extension,
            "mime_type": document.mime_type,
            "byte_size": document.byte_size,
            "status": document.status,
            "page_count": document.page_count,
            "slide_count": document.slide_count,
            "sheet_count": document.sheet_count,
            "text_characters": document.text_characters,
            "chunk_count": document.chunk_count,
            "parser_version": document.parser_version,
            "safe_error_code": document.safe_error_code,
            "favorite": bool(document.favorite),
            "deleted_at": _iso(document.deleted_at) if document.deleted_at else None,
            "collection_ids": self.repository.document_collection_ids(document.id),
            "tags": self.repository.document_tag_names(document.id),
            "created_at": _iso(document.created_at),
            "updated_at": _iso(document.updated_at),
        }

    def list_documents(
        self,
        *,
        collection_id: int | None,
        offset: int,
        limit: int,
        only_deleted: bool = False,
        favorite: bool | None = None,
        tag: str | None = None,
        query: str | None = None,
        status: str | None = None,
        sort: str = "created",
        descending: bool = True,
    ) -> list[dict[str, object]]:
        return [
            self._document_response(document)
            for document in self.repository.list_documents(
                collection_id=collection_id,
                offset=offset,
                limit=limit,
                only_deleted=only_deleted,
                favorite=favorite,
                tag=tag,
                query=query,
                status=status,
                sort=sort,
                descending=descending,
            )
        ]

    def get_document(self, document_id: int) -> dict[str, object]:
        try:
            document = self.repository.require_document(document_id)
        except KnowledgeRecordNotFound as exc:
            raise ResourceNotFoundError(
                "KNOWLEDGE_DOCUMENT_NOT_FOUND",
                "知识库文档不存在。",
            ) from exc
        return self._document_response(document)

    def _job_response(self, job) -> dict[str, object]:
        try:
            failed_pages = json.loads(job.failed_pages_json or "[]")
        except (TypeError, json.JSONDecodeError):
            failed_pages = []
        if not isinstance(failed_pages, list):
            failed_pages = []
        return {
            "id": job.id,
            "document_id": job.document_id,
            "status": job.status,
            "progress": job.progress,
            "stage": job.stage,
            "retryable": job.retryable,
            "safe_error_code": job.safe_error_code,
            "cancel_requested": job.cancel_requested,
            "current_page": job.current_page,
            "page_count": job.page_count,
            "eta_seconds": job.eta_seconds,
            "failed_pages": failed_pages,
            "version": job.version,
            "created_at": _iso(job.created_at),
            "updated_at": _iso(job.updated_at),
        }

    def _prepare_import_batch(self, value: ImportBatchRequest) -> dict[str, object]:
        manifests = [manifest.model_dump() for manifest in value.files]
        for manifest in value.files:
            try:
                object_path = self.object_store.resolve(manifest.object_relpath)
            except (FileNotFoundError, ValueError) as exc:
                raise KnowledgeObjectMissingError() from exc
            if (
                object_path.stat().st_size != manifest.byte_size
                or _stream_sha256(object_path) != manifest.sha256
            ):
                raise KnowledgeFileSignatureMismatchError()
        try:
            def prepare(repository):
                duplicates = []
                for manifest in value.files:
                    existing = repository.find_document_by_sha(manifest.sha256)
                    if existing is None:
                        continue
                    previous = repository.document_collection_ids(existing.id)
                    duplicates.append(
                        {
                            "document_id": existing.id,
                            "display_name": manifest.display_name,
                            "collection_ids": sorted(set(previous + [value.collection_id])),
                            "action": (
                                "already_present"
                                if value.collection_id in previous
                                else "linked_existing"
                            ),
                        }
                    )
                jobs = [
                    self._job_response(job)
                    for job in repository.create_import_jobs(
                        value.collection_id,
                        manifests,
                    )
                ]
                return {"jobs": jobs, "duplicates": duplicates}

            return self._with_fresh_repository(prepare)
        except KnowledgeRecordNotFound as exc:
            raise ResourceNotFoundError(
                "KNOWLEDGE_COLLECTION_NOT_FOUND",
                "知识库集合不存在。",
            ) from exc

    async def import_batch(self, value: ImportBatchRequest) -> dict[str, object]:
        result = await asyncio.to_thread(self._prepare_import_batch, value)
        for job in result["jobs"]:
            self.coordinator.enqueue(int(job["id"]))
        return result

    def list_jobs(self) -> list[dict[str, object]]:
        return [self._job_response(job) for job in self.repository.list_jobs()]

    def get_job(self, job_id: int) -> dict[str, object]:
        try:
            return self._job_response(self.repository.require_job(job_id))
        except KnowledgeRecordNotFound as exc:
            raise ResourceNotFoundError(
                "KNOWLEDGE_IMPORT_NOT_FOUND",
                "知识库导入任务不存在。",
            ) from exc

    def retry_job(self, job_id: int) -> dict[str, object]:
        def retry(repository):
            return self._job_response(repository.reset_job_for_retry(job_id))

        try:
            job = self._with_fresh_repository(retry)
        except KnowledgeRecordNotFound as exc:
            raise ResourceNotFoundError(
                "KNOWLEDGE_IMPORT_NOT_FOUND",
                "知识库导入任务不存在。",
            ) from exc
        except KnowledgeRecordConflict as exc:
            raise KnowledgeImportNotRetryableError() from exc
        self.coordinator.enqueue(int(job["id"]))
        return job

    def _request_cancel(self, job_id: int) -> dict[str, object]:
        try:
            return self._with_fresh_repository(
                lambda repository: self._job_response(repository.request_cancel(job_id))
            )
        except KnowledgeRecordNotFound as exc:
            raise ResourceNotFoundError(
                "KNOWLEDGE_IMPORT_NOT_FOUND",
                "知识库导入任务不存在。",
            ) from exc

    def _current_job(self, job_id: int) -> dict[str, object]:
        try:
            return self._with_fresh_repository(
                lambda repository: self._job_response(repository.require_job(job_id))
            )
        except KnowledgeRecordNotFound as exc:
            raise ResourceNotFoundError(
                "KNOWLEDGE_IMPORT_NOT_FOUND",
                "知识库导入任务不存在。",
            ) from exc

    def _cancel_queued_job(self, job_id: int) -> dict[str, object]:
        def cancel(repository):
            current = repository.require_job(job_id)
            if current.status != ImportJobStatus.QUEUED.value:
                return self._job_response(current)
            current = repository.transition_job(
                job_id,
                expected_version=current.version,
                status=ImportJobStatus.CANCELLED,
                progress=current.progress,
                safe_error_code="KNOWLEDGE_IMPORT_CANCELLED",
            )
            return self._job_response(current)

        return self._with_fresh_repository(cancel)

    async def cancel_job(self, job_id: int) -> dict[str, object]:
        await asyncio.to_thread(self._request_cancel, job_id)
        await self.coordinator.cancel(job_id)
        current = await asyncio.to_thread(self._current_job, job_id)
        if current["status"] == ImportJobStatus.QUEUED.value:
            current = await asyncio.to_thread(self._cancel_queued_job, job_id)
        return current

    def _prepare_rebuild_document(self, document_id: int) -> dict[str, object]:
        def rebuild(repository):
            document = repository.require_document(document_id)
            return self._job_response(repository.create_job(document.id))

        try:
            return self._with_fresh_repository(rebuild)
        except KnowledgeRecordNotFound as exc:
            raise ResourceNotFoundError(
                "KNOWLEDGE_DOCUMENT_NOT_FOUND",
                "知识库文档不存在。",
            ) from exc

    async def rebuild_document(self, document_id: int) -> dict[str, object]:
        job = await asyncio.to_thread(self._prepare_rebuild_document, document_id)
        self.coordinator.enqueue(int(job["id"]))
        return job

    def _prepare_document_deletion(self, document_id: int) -> tuple[str, list[int]]:
        def prepare(repository):
            document = repository.require_document(document_id)
            job_ids = repository.active_job_ids(document_id)
            for job_id in job_ids:
                repository.request_cancel(job_id)
            return document.object_relpath, job_ids

        try:
            return self._with_fresh_repository(prepare)
        except KnowledgeRecordNotFound as exc:
            raise ResourceNotFoundError(
                "KNOWLEDGE_DOCUMENT_NOT_FOUND",
                "知识库文档不存在。",
            ) from exc

    def _finalize_document_deletion(self, document_id: int, object_relpath: str) -> None:
        def remove(repository):
            try:
                KnowledgeSearchRepository(repository.db).delete_document_index(
                    document_id,
                    commit=False,
                )
            except KnowledgeUnavailable:
                pass
            try:
                if not repository.delete_document_record(document_id, commit=False):
                    raise KnowledgeRecordNotFound(
                        f"knowledge document {document_id} was not found"
                    )
                repository.db.commit()
            except Exception:
                repository.db.rollback()
                raise

        self._with_fresh_repository(remove)
        try:
            self.object_store.delete(object_relpath)
        except FileNotFoundError:
            pass

    async def delete_document(self, document_id: int) -> None:
        _object_relpath, job_ids = await asyncio.to_thread(
            self._prepare_document_deletion,
            document_id,
        )
        for job_id in job_ids:
            await self.coordinator.cancel(job_id)
        await asyncio.to_thread(
            self._with_fresh_repository,
            lambda repository: repository.soft_delete_documents([document_id]),
        )

    async def purge_document(self, document_id: int) -> None:
        def require_trashed(repository):
            document = repository.require_document(document_id)
            if document.deleted_at is None:
                raise KnowledgeRecordConflict("active document cannot be purged")

        await asyncio.to_thread(self._with_fresh_repository, require_trashed)
        object_relpath, job_ids = await asyncio.to_thread(
            self._prepare_document_deletion,
            document_id,
        )
        for job_id in job_ids:
            await self.coordinator.cancel(job_id)
        await asyncio.to_thread(
            self._finalize_document_deletion,
            document_id,
            object_relpath,
        )

    async def bulk_documents(self, value: KnowledgeBulkRequest) -> dict[str, object]:
        items: list[dict[str, object]] = []
        for document_id in value.document_ids:
            try:
                if value.action == "move_to_trash":
                    await self.delete_document(document_id)
                elif value.action == "purge":
                    await self.purge_document(document_id)
                else:
                    def mutate(repository):
                        repository.require_document(document_id)
                        if value.action == "restore":
                            repository.restore_documents([document_id])
                        elif value.action == "favorite":
                            repository.set_documents_favorite(
                                [document_id],
                                bool(value.favorite),
                            )
                        elif value.action == "set_tags":
                            repository.set_document_tags([document_id], value.tags)
                        elif value.action == "add_to_collections":
                            repository.add_documents_to_collections(
                                [document_id],
                                value.collection_ids,
                            )
                        elif value.action == "remove_from_collections":
                            repository.remove_documents_from_collections(
                                [document_id],
                                value.collection_ids,
                            )

                    await asyncio.to_thread(self._with_fresh_repository, mutate)
                items.append({"document_id": document_id, "ok": True, "code": None})
            except ResourceNotFoundError as exc:
                items.append({"document_id": document_id, "ok": False, "code": exc.code})
            except KnowledgeRecordNotFound:
                items.append(
                    {
                        "document_id": document_id,
                        "ok": False,
                        "code": "KNOWLEDGE_DOCUMENT_NOT_FOUND",
                    }
                )
            except KnowledgeRecordConflict:
                items.append(
                    {
                        "document_id": document_id,
                        "ok": False,
                        "code": "KNOWLEDGE_BULK_CONFLICT",
                    }
                )
        return {"items": items}

    def search(self, value: KnowledgeSearchRequest) -> dict[str, object]:
        collection_ids = self.repository.bound_collection_ids(value.session_id)
        try:
            hits = self.search_repository.search(
                value.query,
                collection_ids,
                value.limit,
            )
        except KnowledgeUnavailable as exc:
            raise KnowledgeIndexUnavailableError() from exc
        return {
            "mode": "keyword",
            "items": [
                {
                    "chunk_id": hit.chunk_id,
                    "document_id": hit.document_id,
                    "document_name": hit.document_name,
                    "text": hit.text,
                    "heading_path": hit.heading_path,
                    "locator": {
                        "type": hit.locator_type,
                        "start": hit.locator_start,
                        "end": hit.locator_end,
                        "sheet_name": hit.sheet_name,
                    },
                    "score": hit.score,
                    "retrieval_mode": "keyword",
                }
                for hit in hits
            ],
        }

    def get_session_collections(self, session_id: str) -> dict[str, object]:
        return {
            "session_id": session_id,
            "collection_ids": self.repository.bound_collection_ids(session_id),
            "privacy_mode": self.repository.session_privacy_mode(session_id),
        }

    def save_session_collections(
        self,
        session_id: str,
        value: SessionKnowledgeCollectionsUpdate,
    ) -> dict[str, object]:
        try:
            collection_ids = self.repository.replace_session_collections(
                session_id,
                value.collection_ids,
                privacy_mode=value.privacy_mode,
            )
        except KnowledgeRecordNotFound as exc:
            raise ResourceNotFoundError(
                "KNOWLEDGE_COLLECTION_NOT_FOUND",
                "知识库集合不存在。",
            ) from exc
        return {
            "session_id": session_id,
            "collection_ids": collection_ids,
            "privacy_mode": value.privacy_mode,
        }
