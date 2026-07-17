from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.database import Base
from backend.knowledge.models import ImportJobStatus
from backend.knowledge.repository import KnowledgeRepository, StaleKnowledgeJob


@pytest.fixture()
def repository(tmp_path: Path) -> tuple[KnowledgeRepository, Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = Session(engine)
    value = KnowledgeRepository(db, tmp_path / "knowledge")
    try:
        yield value, db
    finally:
        db.close()
        engine.dispose()


def create_document(repository: KnowledgeRepository, digest: str = "a" * 64):
    return repository.upsert_document(
        sha256=digest,
        display_name="讲义.pdf",
        extension=".pdf",
        mime_type="application/pdf",
        byte_size=16,
        object_relpath=f"objects/{digest}",
    )


def test_document_hash_is_global_but_collection_links_are_unique(repository) -> None:
    repo, _db = repository
    first = repo.create_collection("高数", "", "#c98f65")
    second = repo.create_collection("软件杯", "", "#8f9d7a")
    doc_a = create_document(repo)
    doc_b = repo.upsert_document(
        sha256="a" * 64,
        display_name="副本.pdf",
        extension=".pdf",
        mime_type="application/pdf",
        byte_size=16,
        object_relpath=f"objects/{'a' * 64}",
    )

    repo.link_document(first.id, doc_a.id)
    repo.link_document(first.id, doc_a.id)
    repo.link_document(second.id, doc_a.id)

    assert doc_a.id == doc_b.id
    assert repo.collection_document_ids(first.id) == [doc_a.id]
    assert repo.collection_document_ids(second.id) == [doc_a.id]


def test_session_scope_contains_only_bound_collections(repository) -> None:
    repo, _db = repository
    repo.ensure_session("student_a")
    visible = repo.create_collection("可见", "", "#c98f65")
    hidden = repo.create_collection("不可见", "", "#8f9d7a")

    repo.replace_session_collections("student_a", [visible.id])

    assert repo.bound_collection_ids("student_a") == [visible.id]
    assert hidden.id not in repo.bound_collection_ids("student_a")


def test_replacing_session_collections_removes_stale_links(repository) -> None:
    repo, _db = repository
    repo.ensure_session("student_a")
    first = repo.create_collection("高数", "", "#c98f65")
    second = repo.create_collection("英语", "", "#8f9d7a")
    repo.replace_session_collections("student_a", [first.id, second.id])

    repo.replace_session_collections("student_a", [second.id])

    assert repo.bound_collection_ids("student_a") == [second.id]


def test_import_job_version_rejects_stale_update(repository) -> None:
    repo, _db = repository
    document = create_document(repo)
    job = repo.create_job(document_id=document.id)

    updated = repo.transition_job(
        job.id,
        expected_version=0,
        status=ImportJobStatus.VALIDATING,
        progress=5,
    )

    assert updated.version == 1
    assert updated.status == ImportJobStatus.VALIDATING.value
    with pytest.raises(StaleKnowledgeJob):
        repo.transition_job(
            job.id,
            expected_version=0,
            status=ImportJobStatus.PARSING,
            progress=10,
        )


def test_cancel_request_is_idempotent(repository) -> None:
    repo, _db = repository
    document = create_document(repo)
    job = repo.create_job(document_id=document.id)

    first = repo.request_cancel(job.id)
    second = repo.request_cancel(job.id)

    assert first.cancel_requested is True
    assert second.cancel_requested is True
    assert first.version == second.version


def test_ocr_progress_and_retry_state_preserve_failed_pages(repository) -> None:
    repo, _db = repository
    document = create_document(repo)
    job = repo.create_job(document_id=document.id)

    running = repo.transition_job(
        job.id,
        expected_version=job.version,
        status=ImportJobStatus.OCR_RUNNING,
        progress=55,
        stage="ocr",
        current_page=5,
        page_count=10,
        eta_seconds=12,
        failed_pages=[2],
    )

    assert running.current_page == 5
    assert running.page_count == 10
    assert running.eta_seconds == 12
    assert running.failed_pages_json == "[2]"

    failed = repo.transition_job(
        job.id,
        expected_version=running.version,
        status=ImportJobStatus.FAILED,
        progress=55,
        stage="ocr_partial",
        retryable=True,
        safe_error_code="KNOWLEDGE_OCR_PAGE_FAILED",
        failed_pages=[2],
    )

    retry = repo.reset_job_for_retry(job.id)
    assert retry.status == ImportJobStatus.QUEUED.value
    assert retry.progress == 0
    assert retry.cancel_requested is False
    assert retry.failed_pages_json == "[2]"
    assert repo.retry_page_numbers(job.id) == [2]
