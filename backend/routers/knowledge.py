from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session

from backend.config import KNOWLEDGE_DIR
from backend.database import SessionLocal, get_db
from backend.knowledge.import_service import get_knowledge_import_coordinator
from backend.knowledge.object_store import KnowledgeObjectStore
from backend.knowledge.repository import KnowledgeRepository
from backend.knowledge.schemas import (
    ImportBatchRequest,
    ImportBatchResponse,
    KnowledgeCollectionCreate,
    KnowledgeCollectionResponse,
    KnowledgeCollectionUpdate,
    KnowledgeDocumentResponse,
    KnowledgeImportJobResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeStatusResponse,
    SessionKnowledgeCollectionsResponse,
    SessionKnowledgeCollectionsUpdate,
)
from backend.knowledge.search import KnowledgeSearchRepository
from backend.knowledge.service import KnowledgeService


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
session_router = APIRouter(prefix="/api/sessions", tags=["knowledge"])
PositiveId = Annotated[int, Path(ge=1)]
SessionId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]


def get_knowledge_service(db: Session = Depends(get_db)) -> KnowledgeService:
    repository = KnowledgeRepository(db, KNOWLEDGE_DIR)
    return KnowledgeService(
        repository,
        KnowledgeObjectStore(KNOWLEDGE_DIR),
        KnowledgeSearchRepository(db),
        get_knowledge_import_coordinator(KNOWLEDGE_DIR),
        session_factory=SessionLocal,
    )


@router.get("/status", response_model=KnowledgeStatusResponse)
def knowledge_status(service: KnowledgeService = Depends(get_knowledge_service)):
    return service.status()


@router.get("/collections", response_model=list[KnowledgeCollectionResponse])
def list_collections(service: KnowledgeService = Depends(get_knowledge_service)):
    return service.list_collections()


@router.post("/collections", status_code=201, response_model=KnowledgeCollectionResponse)
def create_collection(
    value: KnowledgeCollectionCreate,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    return service.create_collection(value)


@router.get("/collections/{collection_id}", response_model=KnowledgeCollectionResponse)
def get_collection(
    collection_id: PositiveId,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    return service.get_collection(collection_id)


@router.put("/collections/{collection_id}", response_model=KnowledgeCollectionResponse)
def update_collection(
    collection_id: PositiveId,
    value: KnowledgeCollectionUpdate,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    return service.update_collection(collection_id, value)


@router.delete("/collections/{collection_id}", status_code=204)
def delete_collection(
    collection_id: PositiveId,
    service: KnowledgeService = Depends(get_knowledge_service),
) -> Response:
    service.delete_collection(collection_id)
    return Response(status_code=204)


@router.get("/documents", response_model=list[KnowledgeDocumentResponse])
def list_documents(
    collection_id: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    service: KnowledgeService = Depends(get_knowledge_service),
):
    return service.list_documents(
        collection_id=collection_id,
        offset=offset,
        limit=limit,
    )


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentResponse)
def get_document(
    document_id: PositiveId,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    return service.get_document(document_id)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: PositiveId,
    service: KnowledgeService = Depends(get_knowledge_service),
) -> Response:
    await service.delete_document(document_id)
    return Response(status_code=204)


@router.post("/documents/{document_id}/rebuild", status_code=202, response_model=KnowledgeImportJobResponse)
async def rebuild_document(
    document_id: PositiveId,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    return await service.rebuild_document(document_id)


@router.post("/imports", status_code=202, response_model=ImportBatchResponse)
async def create_import(
    value: ImportBatchRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    return await service.import_batch(value)


@router.get("/imports", response_model=list[KnowledgeImportJobResponse])
def list_imports(service: KnowledgeService = Depends(get_knowledge_service)):
    return service.list_jobs()


@router.get("/imports/{job_id}", response_model=KnowledgeImportJobResponse)
def get_import(
    job_id: PositiveId,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    return service.get_job(job_id)


@router.delete("/imports/{job_id}", response_model=KnowledgeImportJobResponse)
async def cancel_import(
    job_id: PositiveId,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    return await service.cancel_job(job_id)


@router.post("/search", response_model=KnowledgeSearchResponse)
def search(
    value: KnowledgeSearchRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    return service.search(value)


@session_router.get(
    "/{session_id}/knowledge-collections",
    response_model=SessionKnowledgeCollectionsResponse,
)
def get_session_collections(
    session_id: SessionId,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    return service.get_session_collections(session_id)


@session_router.put(
    "/{session_id}/knowledge-collections",
    response_model=SessionKnowledgeCollectionsResponse,
)
def save_session_collections(
    session_id: SessionId,
    value: SessionKnowledgeCollectionsUpdate,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    return service.save_session_collections(session_id, value)
