from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from pathlib import Path
import threading
import time
from types import SimpleNamespace

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.database import Base
from backend.knowledge.import_service import (
    KnowledgeImportCoordinator,
    KnowledgeImportService,
    parse_timeout_for_bytes,
    worker_environment,
)
from backend.knowledge.models import ImportJobStatus
from backend.knowledge.repository import KnowledgeRepository
from backend.knowledge.search import KnowledgeSearchRepository
from backend.knowledge.worker_protocol import BlockEvent, DoneEvent, ProgressEvent


def test_parse_timeout_scales_for_large_files_with_a_hard_cap() -> None:
    mib = 1024 * 1024
    assert parse_timeout_for_bytes(100 * mib, base_seconds=120) == 120
    assert parse_timeout_for_bytes(188 * mib, base_seconds=120) == 240
    assert parse_timeout_for_bytes(500 * mib, base_seconds=120) == 600
    assert parse_timeout_for_bytes(10_000 * mib, base_seconds=120) == 900


@dataclass(frozen=True)
class FakeJob:
    id: int
    document_id: int
    status: str = ImportJobStatus.QUEUED.value
    progress: int = 0
    stage: str = "queued"
    retryable: bool = False
    safe_error_code: str | None = None
    cancel_requested: bool = False
    version: int = 0
    current_page: int | None = None
    page_count: int | None = None
    eta_seconds: int | None = None
    failed_pages_json: str = "[]"


class FakeRepository:
    def __init__(self) -> None:
        self.jobs = {7: FakeJob(id=7, document_id=3)}
        self.documents = {
            3: SimpleNamespace(
                id=3,
                sha256="a" * 64,
                object_relpath="objects/" + "a" * 64,
                extension=".txt",
            )
        }
        self.blocks = []
        self.done = None
        self.cancel_requests = 0

    def require_job(self, job_id: int) -> FakeJob:
        return self.jobs[job_id]

    def require_document(self, document_id: int):
        return self.documents[document_id]

    def retry_page_numbers(self, job_id: int) -> list[int]:
        import json

        return json.loads(self.jobs[job_id].failed_pages_json)

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
    ) -> FakeJob:
        job = self.jobs[job_id]
        assert job.version == expected_version
        job = replace(
            job,
            status=status.value,
            progress=progress,
            stage=stage or status.value.lower(),
            retryable=retryable,
            safe_error_code=safe_error_code,
            current_page=current_page,
            page_count=page_count,
            eta_seconds=eta_seconds,
            failed_pages_json=(
                __import__("json").dumps(failed_pages)
                if failed_pages is not None
                else job.failed_pages_json
            ),
            version=job.version + 1,
        )
        self.jobs[job_id] = job
        return job

    def request_cancel(self, job_id: int) -> FakeJob:
        self.cancel_requests += 1
        job = self.jobs[job_id]
        if job.cancel_requested:
            return job
        job = replace(job, cancel_requested=True, version=job.version + 1)
        self.jobs[job_id] = job
        return job

    def mark_active_jobs_interrupted(self) -> int:
        count = 0
        for job_id, job in tuple(self.jobs.items()):
            if job.status in {
                ImportJobStatus.QUEUED.value,
                ImportJobStatus.VALIDATING.value,
                ImportJobStatus.PARSING.value,
                ImportJobStatus.OCR_RUNNING.value,
                ImportJobStatus.INDEXING.value,
            }:
                self.jobs[job_id] = replace(
                    job,
                    status=ImportJobStatus.INTERRUPTED.value,
                    retryable=True,
                    safe_error_code="KNOWLEDGE_IMPORT_INTERRUPTED",
                    version=job.version + 1,
                )
                count += 1
        return count

    def stage_worker_block(self, _job_id, block) -> None:
        self.blocks.append(block)

    def finish_worker_output(self, _job_id, done) -> None:
        self.done = done

    def clear_worker_output(self, _job_id) -> None:
        self.blocks.clear()
        self.done = None


class FakeStdout:
    def __init__(self, lines: list[bytes] | None = None) -> None:
        self.lines = asyncio.Queue()
        for line in lines or []:
            self.lines.put_nowait(line)

    async def readline(self) -> bytes:
        return await self.lines.get()


class FakeProcess:
    def __init__(self, lines: list[bytes] | None = None) -> None:
        self.stdout = FakeStdout(lines)
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False
        self.started = asyncio.Event()
        self.done = asyncio.Event()

    async def wait(self) -> int:
        self.started.set()
        await self.done.wait()
        return self.returncode or 0

    def finish(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.stdout.lines.put_nowait(b"")
        self.done.set()

    def terminate(self) -> None:
        self.terminated = True
        self.finish(-15)

    def kill(self) -> None:
        self.killed = True
        self.finish(-9)


def test_cancel_terminates_worker_and_persists_cancelled() -> None:
    async def exercise() -> None:
        repository = FakeRepository()
        process = FakeProcess()
        service = KnowledgeImportService(
            repository,
            spawn_worker=lambda _request: (process.started.set(), process)[1],
            parse_timeout_seconds=30,
        )
        running = asyncio.create_task(service.run_job(7))
        await asyncio.wait_for(process.started.wait(), timeout=1)

        repository.request_cancel(7)
        cancelled = await service.cancel(7)
        await asyncio.wait_for(running, timeout=1)

        assert cancelled.cancel_requested is True
        assert repository.cancel_requests == 1
        assert process.terminated is True
        assert repository.require_job(7).status == ImportJobStatus.CANCELLED.value

    asyncio.run(exercise())


def test_coordinator_runs_job_loop_outside_caller_event_loop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    coordinator = KnowledgeImportCoordinator(tmp_path / "knowledge")

    async def slow_run(_job_id: int) -> None:
        time.sleep(0.15)

    monkeypatch.setattr(coordinator, "_run", slow_run)

    async def exercise() -> None:
        started = time.perf_counter()
        coordinator.enqueue(7)
        await asyncio.sleep(0.02)
        elapsed = time.perf_counter() - started
        await coordinator.shutdown()
        assert elapsed < 0.08

    asyncio.run(exercise())


def test_coordinator_limits_parallel_jobs_to_two(
    tmp_path: Path,
    monkeypatch,
) -> None:
    coordinator = KnowledgeImportCoordinator(tmp_path / "knowledge")
    lock = threading.Lock()
    release = threading.Event()
    two_started = threading.Event()
    active = 0
    maximum_active = 0

    async def controlled_run(_job_id: int) -> None:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            if active >= 2:
                two_started.set()
        while not release.is_set():
            await asyncio.sleep(0.005)
        with lock:
            active -= 1

    monkeypatch.setattr(coordinator, "_run", controlled_run)
    monkeypatch.setattr(
        coordinator,
        "_mark_interrupted",
        lambda _job_id: None,
    )

    async def exercise() -> None:
        for job_id in range(1, 6):
            coordinator.enqueue(job_id)
        assert await asyncio.to_thread(two_started.wait, 1)
        await asyncio.sleep(0.05)
        with lock:
            observed = maximum_active
        release.set()
        await coordinator.shutdown()
        assert observed == 2

    asyncio.run(exercise())


def test_coordinator_shutdown_marks_not_started_jobs_interrupted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    coordinator = KnowledgeImportCoordinator(tmp_path / "knowledge")
    release = threading.Event()
    two_started = threading.Event()
    lock = threading.Lock()
    active = 0
    interrupted: list[int] = []

    async def controlled_run(_job_id: int) -> None:
        nonlocal active
        with lock:
            active += 1
            if active == 2:
                two_started.set()
        while not release.is_set():
            await asyncio.sleep(0.005)
        with lock:
            active -= 1

    monkeypatch.setattr(coordinator, "_run", controlled_run)
    monkeypatch.setattr(
        coordinator,
        "_mark_interrupted",
        lambda job_id: interrupted.append(job_id),
        raising=False,
    )

    async def exercise() -> None:
        coordinator.enqueue(1)
        coordinator.enqueue(2)
        coordinator.enqueue(3)
        assert await asyncio.to_thread(two_started.wait, 1)
        shutdown = asyncio.create_task(coordinator.shutdown())
        await asyncio.sleep(0.05)
        release.set()
        await shutdown

    asyncio.run(exercise())
    assert interrupted == [3]


def test_coordinator_initialization_failure_marks_job_interrupted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    coordinator = KnowledgeImportCoordinator(tmp_path / "knowledge")
    interrupted: list[int] = []

    async def fail_run(_job_id: int) -> None:
        raise RuntimeError("injected initialization failure")

    monkeypatch.setattr(coordinator, "_run", fail_run)
    monkeypatch.setattr(
        coordinator,
        "_mark_interrupted",
        lambda job_id: interrupted.append(job_id),
        raising=False,
    )

    async def exercise() -> None:
        coordinator.enqueue(7)
        while coordinator._tasks:
            await asyncio.sleep(0.005)
        await coordinator.shutdown()

    asyncio.run(exercise())
    assert interrupted == [7]


def test_cancel_during_indexing_finishes_as_cancelled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def exercise() -> None:
        database_path = tmp_path / "cancel-during-index.sqlite3"
        engine = create_engine(f"sqlite+pysqlite:///{database_path}", future=True)

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine)
        db = Session(engine)
        repository = KnowledgeRepository(db, tmp_path / "knowledge")
        document = repository.upsert_document(
            sha256="8" * 64,
            display_name="索引取消.txt",
            extension=".txt",
            mime_type="text/plain",
            byte_size=16,
            object_relpath="objects/" + "8" * 64,
        )
        job = repository.create_job(document.id)
        done = DoneEvent(text_characters=0)
        process = FakeProcess([(done.model_dump_json() + "\n").encode("utf-8")])
        process.finish(0)

        def cancel_from_another_session(_self, _document_id: int) -> None:
            other = Session(engine)
            try:
                KnowledgeRepository(other).request_cancel(job.id)
            finally:
                other.close()

        monkeypatch.setattr(
            KnowledgeSearchRepository,
            "replace_document_index",
            cancel_from_another_session,
        )
        try:
            result = await KnowledgeImportService(
                repository,
                spawn_worker=lambda _request: process,
            ).run_job(job.id)
            assert result.status == ImportJobStatus.CANCELLED.value
            assert result.safe_error_code == "KNOWLEDGE_IMPORT_CANCELLED"
        finally:
            db.close()
            engine.dispose()

    asyncio.run(exercise())


def test_invalid_worker_output_marks_job_failed_without_escaping() -> None:
    async def exercise() -> None:
        repository = FakeRepository()
        process = FakeProcess([b"not-json\n", b""])
        service = KnowledgeImportService(repository, spawn_worker=lambda _request: process)

        result = await service.run_job(7)

        assert result.status == ImportJobStatus.FAILED.value
        assert result.safe_error_code == "KNOWLEDGE_WORKER_PROTOCOL_INVALID"
        assert process.terminated is True

    asyncio.run(exercise())


def test_parse_timeout_terminates_worker_and_is_retryable() -> None:
    async def exercise() -> None:
        repository = FakeRepository()
        process = FakeProcess()
        service = KnowledgeImportService(
            repository,
            spawn_worker=lambda _request: process,
            parse_timeout_seconds=0.01,
        )

        result = await service.run_job(7)

        assert process.terminated is True
        assert result.status == ImportJobStatus.FAILED.value
        assert result.safe_error_code == "KNOWLEDGE_PARSE_TIMEOUT"
        assert result.retryable is True

    asyncio.run(exercise())


def test_startup_marks_running_jobs_interrupted() -> None:
    repository = FakeRepository()
    repository.jobs[7] = replace(
        repository.jobs[7],
        status=ImportJobStatus.PARSING.value,
        version=2,
    )
    service = KnowledgeImportService(repository)

    assert service.recover_interrupted() == 1
    assert repository.require_job(7).status == ImportJobStatus.INTERRUPTED.value
    assert repository.require_job(7).retryable is True


def test_startup_marks_queued_jobs_interrupted() -> None:
    repository = FakeRepository()
    service = KnowledgeImportService(repository)

    assert service.recover_interrupted() == 1
    assert repository.require_job(7).status == ImportJobStatus.INTERRUPTED.value
    assert repository.require_job(7).retryable is True


def test_worker_environment_is_minimal_and_contains_no_credentials() -> None:
    source = {
        "SYSTEMROOT": r"C:\Windows",
        "TEMP": r"C:\Temp",
        "MODEL_API_KEY": "secret",
        "DESKTOP_TOKEN": "desktop-secret",
        "HTTPS_PROXY": "http://proxy",
        "UNRELATED": "value",
    }

    result = worker_environment(
        source,
        object_root=r"C:\A3\knowledge\objects",
        limits={"max_blocks": 100_000},
    )

    assert result["SYSTEMROOT"] == r"C:\Windows"
    assert result["TEMP"] == r"C:\Temp"
    assert result["PYTHONUTF8"] == "1"
    assert result["A3_KNOWLEDGE_OBJECT_ROOT"] == r"C:\A3\knowledge\objects"
    assert "MODEL_API_KEY" not in result
    assert "DESKTOP_TOKEN" not in result
    assert "HTTPS_PROXY" not in result
    assert "UNRELATED" not in result


def test_scan_pdf_stops_at_ocr_required_without_replacing_fts() -> None:
    async def exercise() -> None:
        repository = FakeRepository()
        done = DoneEvent(page_count=3, text_characters=0, ocr_required=True)
        process = FakeProcess([(done.model_dump_json() + "\n").encode("utf-8")])
        process.finish(0)
        service = KnowledgeImportService(
            repository,
            spawn_worker=lambda _request: process,
        )

        result = await service.run_job(7)

        assert result.status == ImportJobStatus.OCR_REQUIRED.value
        assert result.progress == 90
        assert result.retryable is True
        assert result.safe_error_code == "KNOWLEDGE_OCR_PACK_REQUIRED"

    asyncio.run(exercise())


def test_partial_ocr_failure_preserves_successful_page_blocks_for_retry() -> None:
    async def exercise() -> None:
        repository = FakeRepository()
        block = BlockEvent(
            ordinal=0,
            text="page one",
            heading_path=[],
            locator_type="page",
            locator_start=1,
            locator_end=1,
        )
        progress = ProgressEvent(
            progress=60,
            stage="ocr",
            current_page=2,
            page_count=3,
            eta_seconds=4,
            failed_pages=[2],
        )
        done = DoneEvent(
            page_count=3,
            text_characters=8,
            ocr_performed=True,
            failed_pages=[2],
        )
        lines = [
            (event.model_dump_json() + "\n").encode("utf-8")
            for event in (block, progress, done)
        ]
        process = FakeProcess(lines)
        process.finish(0)
        service = KnowledgeImportService(
            repository,
            spawn_worker=lambda _request: process,
        )

        result = await service.run_job(7)

        assert result.status == ImportJobStatus.FAILED.value
        assert result.stage == "ocr_partial"
        assert result.retryable is True
        assert result.safe_error_code == "KNOWLEDGE_OCR_PAGE_FAILED"
        assert result.current_page == 2
        assert result.page_count == 3
        assert result.eta_seconds == 4
        assert result.failed_pages_json == "[2]"
        assert [item.locator_start for item in repository.blocks] == [1]

    asyncio.run(exercise())


def test_retry_request_contains_only_failed_ocr_pages() -> None:
    repository = FakeRepository()
    repository.jobs[7] = replace(
        repository.jobs[7],
        status=ImportJobStatus.FAILED.value,
        failed_pages_json="[2,5]",
    )
    repository.documents[3].extension = ".pdf"
    request = KnowledgeImportService(repository)._request_for(7)
    assert request.ocr_page_numbers == [2, 5]


def test_semantic_update_scheduler_failure_never_fails_keyword_import(
    monkeypatch,
) -> None:
    async def exercise() -> None:
        repository = FakeRepository()
        repository.db = object()
        repository.worker_block_events = lambda _job_id: []
        repository.replace_chunks = lambda _document_id, _chunks: []
        done = DoneEvent(text_characters=0)
        process = FakeProcess([(done.model_dump_json() + "\n").encode("utf-8")])
        process.finish(0)

        class FakeSearch:
            def __init__(self, _db) -> None:
                pass

            def replace_document_index(self, _document_id: int) -> None:
                pass

        monkeypatch.setattr(
            "backend.knowledge.import_service.KnowledgeSearchRepository",
            FakeSearch,
        )

        def broken_scheduler(_document_id: int) -> None:
            raise RuntimeError("semantic queue unavailable")

        result = await KnowledgeImportService(
            repository,
            spawn_worker=lambda _request: process,
            schedule_semantic_update=broken_scheduler,
        ).run_job(7)

        assert result.status == ImportJobStatus.COMPLETED.value

    asyncio.run(exercise())


def test_real_worker_persists_chunks_and_builds_search_index(tmp_path: Path) -> None:
    async def exercise() -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine)
        db = Session(engine)
        knowledge_root = tmp_path / "knowledge"
        objects_root = knowledge_root / "objects"
        objects_root.mkdir(parents=True)
        digest = "e" * 64
        content = "牛顿第二定律说明力等于质量乘以加速度"
        (objects_root / digest).write_text(content, encoding="utf-8")
        repository = KnowledgeRepository(db, knowledge_root)
        collection = repository.create_collection("物理")
        document = repository.upsert_document(
            sha256=digest,
            display_name="物理讲义.txt",
            extension=".txt",
            mime_type="text/plain",
            byte_size=len(content.encode("utf-8")),
            object_relpath=f"objects/{digest}",
        )
        repository.link_document(collection.id, document.id)
        job = repository.create_job(document.id)
        try:
            result = await KnowledgeImportService(repository).run_job(job.id)
            hits = KnowledgeSearchRepository(db).search(
                "牛顿 定律",
                collection_ids=[collection.id],
            )
            assert result.status == ImportJobStatus.COMPLETED.value
            assert repository.require_document(document.id).chunk_count == 1
            assert [hit.document_name for hit in hits] == ["物理讲义.txt"]
        finally:
            db.close()
            engine.dispose()

    asyncio.run(exercise())
