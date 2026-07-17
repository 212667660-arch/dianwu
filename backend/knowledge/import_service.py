from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
import inspect
import json
import logging
import os
from pathlib import Path
import sys
import threading
import weakref

from backend.database import SessionLocal
from backend.knowledge.chunking import chunk_blocks
from backend.knowledge.models import ImportJobStatus
from backend.knowledge.repository import (
    KnowledgeRepository,
    StaleKnowledgeJob,
)
from backend.knowledge.search import KnowledgeSearchRepository
from backend.knowledge.worker_protocol import (
    BlockEvent,
    DoneEvent,
    FailureEvent,
    ProgressEvent,
    WorkerProtocolError,
    WorkerRequest,
    parse_worker_line,
)


DEFAULT_LIMITS = {
    "max_text_characters": 50_000_000,
    "max_blocks": 100_000,
    "max_pdf_pages": 2_000,
    "max_zip_entries": 10_000,
    "max_uncompressed_bytes": 500_000_000,
    "max_compression_ratio": 100.0,
}
_SERVICES: weakref.WeakSet["KnowledgeImportService"] = weakref.WeakSet()
_COORDINATORS: dict[str, "KnowledgeImportCoordinator"] = {}
logger = logging.getLogger(__name__)


def parse_timeout_for_bytes(
    byte_size: int,
    *,
    base_seconds: float = 120,
    maximum_seconds: float = 900,
) -> float:
    hundred_mib = 100 * 1024 * 1024
    fifty_mib = 50 * 1024 * 1024
    if byte_size <= hundred_mib:
        return base_seconds
    extra_chunks = (byte_size - hundred_mib + fifty_mib - 1) // fifty_mib
    return min(maximum_seconds, base_seconds + extra_chunks * 60)


class WorkerReportedFailure(RuntimeError):
    def __init__(self, code: str, retryable: bool):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def worker_environment(
    source: Mapping[str, str],
    *,
    object_root: str,
    limits: Mapping[str, int | float],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for key in ("SYSTEMROOT", "TEMP", "TMP"):
        value = source.get(key)
        if value:
            result[key] = value
    result["PYTHONUTF8"] = "1"
    result["PYTHONNOUSERSITE"] = "1"
    result["A3_KNOWLEDGE_OBJECT_ROOT"] = object_root
    result["A3_KNOWLEDGE_LIMITS"] = json.dumps(
        dict(limits),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return result


async def spawn_isolated_worker(
    request: WorkerRequest,
    *,
    object_root: Path,
):
    project_root = Path(__file__).resolve().parents[2]
    command = knowledge_worker_command(project_root)
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(project_root),
        env=worker_environment(
            os.environ,
            object_root=str(object_root),
            limits=request.limits,
        ),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    if process.stdin is None:
        process.terminate()
        raise RuntimeError("knowledge worker stdin is unavailable")
    process.stdin.write((request.model_dump_json() + "\n").encode("utf-8"))
    await process.stdin.drain()
    process.stdin.close()
    return process


def knowledge_worker_command(project_root: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--knowledge-worker"]
    bootstrap = (
        "import runpy,sys;"
        + "sys.path.insert(0,"
        + repr(str(project_root))
        + ");"
        + "runpy.run_module('backend.knowledge.worker_main',run_name='__main__')"
    )
    return [
        sys.executable,
        "-I",
        "-X",
        "utf8",
        "-c",
        bootstrap,
    ]


class KnowledgeImportService:
    def __init__(
        self,
        repository,
        *,
        spawn_worker: Callable[[WorkerRequest], object] | None = None,
        schedule_semantic_update: Callable[[int], None] | None = None,
        parse_timeout_seconds: float = 120,
        termination_timeout_seconds: float = 2,
    ) -> None:
        self.repository = repository
        self.parse_timeout_seconds = parse_timeout_seconds
        self.termination_timeout_seconds = termination_timeout_seconds
        self._spawn_worker = spawn_worker
        self._schedule_semantic_update = schedule_semantic_update
        self._active: dict[int, object] = {}
        self._active_lock = asyncio.Lock()
        _SERVICES.add(self)

    def recover_interrupted(self) -> int:
        return self.repository.mark_active_jobs_interrupted()

    def _request_for(self, job_id: int) -> WorkerRequest:
        job = self.repository.require_job(job_id)
        document = self.repository.require_document(job.document_id)
        return WorkerRequest(
            job_id=job.id,
            object_relpath=document.object_relpath,
            extension=document.extension,
            limits=DEFAULT_LIMITS,
        )

    async def _start_worker(self, request: WorkerRequest):
        if self._spawn_worker is not None:
            value = self._spawn_worker(request)
            return await value if inspect.isawaitable(value) else value
        if self.repository.knowledge_root is None:
            raise RuntimeError("knowledge root is unavailable")
        return await spawn_isolated_worker(
            request,
            object_root=self.repository.knowledge_root / "objects",
        )

    def _transition(
        self,
        job_id: int,
        status: ImportJobStatus,
        progress: int,
        *,
        stage: str | None = None,
        retryable: bool = False,
        safe_error_code: str | None = None,
    ):
        current = self.repository.require_job(job_id)
        return self.repository.transition_job(
            job_id,
            expected_version=current.version,
            status=status,
            progress=progress,
            stage=stage,
            retryable=retryable,
            safe_error_code=safe_error_code,
        )

    def _refresh_job(self, job_id: int):
        refresh_job = getattr(self.repository, "refresh_job", self.repository.require_job)
        return refresh_job(job_id)

    def _terminal_transition(
        self,
        job_id: int,
        *,
        completed: bool = False,
        retryable: bool = False,
        safe_error_code: str | None = None,
    ):
        for _attempt in range(3):
            current = self._refresh_job(job_id)
            if current.cancel_requested:
                status = ImportJobStatus.CANCELLED
                progress = current.progress
                terminal_retryable = False
                terminal_code = "KNOWLEDGE_IMPORT_CANCELLED"
            elif completed:
                status = ImportJobStatus.COMPLETED
                progress = 100
                terminal_retryable = False
                terminal_code = None
            else:
                status = ImportJobStatus.FAILED
                progress = current.progress
                terminal_retryable = retryable
                terminal_code = safe_error_code
            try:
                return self.repository.transition_job(
                    job_id,
                    expected_version=current.version,
                    status=status,
                    progress=progress,
                    retryable=terminal_retryable,
                    safe_error_code=terminal_code,
                )
            except StaleKnowledgeJob:
                continue
        raise StaleKnowledgeJob(job_id)

    async def _stop_process(self, process) -> None:
        if process.returncode is None:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=self.termination_timeout_seconds)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    async def _consume(self, job_id: int, process) -> DoneEvent:
        if process.stdout is None:
            raise WorkerProtocolError("worker stdout is unavailable")
        done: DoneEvent | None = None
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            event = parse_worker_line(line.rstrip(b"\r\n"))
            if isinstance(event, ProgressEvent):
                self._transition(
                    job_id,
                    ImportJobStatus.PARSING,
                    event.progress,
                    stage=event.stage,
                )
            elif isinstance(event, BlockEvent):
                self.repository.stage_worker_block(job_id, event)
            elif isinstance(event, DoneEvent):
                done = event
                break
            elif isinstance(event, FailureEvent):
                raise WorkerReportedFailure(event.code, event.retryable)
        returncode = await process.wait()
        if returncode != 0:
            raise RuntimeError("knowledge worker exited unsuccessfully")
        if done is None:
            raise WorkerProtocolError("knowledge worker did not emit done")
        return done

    async def run_job(self, job_id: int):
        process = None
        try:
            self._transition(job_id, ImportJobStatus.VALIDATING, 1)
            current = self._refresh_job(job_id)
            if current.cancel_requested:
                return self._terminal_transition(job_id, completed=True)
            request = self._request_for(job_id)
            process = await self._start_worker(request)
            async with self._active_lock:
                self._active[job_id] = process
            self._transition(job_id, ImportJobStatus.PARSING, 5)
            document = self.repository.require_document(current.document_id)
            timeout_seconds = parse_timeout_for_bytes(
                getattr(document, "byte_size", 0),
                base_seconds=self.parse_timeout_seconds,
            )
            done = await asyncio.wait_for(
                self._consume(job_id, process),
                timeout=timeout_seconds,
            )
            current = self._refresh_job(job_id)
            if current.cancel_requested:
                self.repository.clear_worker_output(job_id)
                return self._terminal_transition(job_id, completed=True)
            if done.ocr_required:
                self.repository.clear_worker_output(job_id)
                return self._transition(
                    job_id,
                    ImportJobStatus.OCR_REQUIRED,
                    90,
                    stage="ocr_required",
                    retryable=True,
                    safe_error_code="KNOWLEDGE_OCR_PACK_REQUIRED",
                )
            self.repository.finish_worker_output(job_id, done)
            self._transition(job_id, ImportJobStatus.INDEXING, 95)
            blocks = self.repository.worker_block_events(job_id)
            chunks = chunk_blocks(blocks, parser_version="chunk-v1")
            document_id = self._refresh_job(job_id).document_id
            self.repository.replace_chunks(document_id, chunks)
            search = KnowledgeSearchRepository(self.repository.db)
            search.replace_document_index(document_id)
            if self._schedule_semantic_update is not None:
                try:
                    self._schedule_semantic_update(document_id)
                except Exception:
                    logger.warning(
                        "knowledge semantic update skipped: KNOWLEDGE_VECTOR_INDEX_UNAVAILABLE"
                    )
            self.repository.clear_worker_output(job_id)
            return self._terminal_transition(job_id, completed=True)
        except asyncio.TimeoutError:
            if process is not None:
                await self._stop_process(process)
            self.repository.clear_worker_output(job_id)
            return self._terminal_transition(
                job_id,
                retryable=True,
                safe_error_code="KNOWLEDGE_PARSE_TIMEOUT",
            )
        except WorkerReportedFailure as exc:
            if process is not None:
                await self._stop_process(process)
            self.repository.clear_worker_output(job_id)
            return self._terminal_transition(
                job_id,
                retryable=exc.retryable,
                safe_error_code=exc.code,
            )
        except WorkerProtocolError:
            if process is not None:
                await self._stop_process(process)
            self.repository.clear_worker_output(job_id)
            return self._terminal_transition(
                job_id,
                safe_error_code="KNOWLEDGE_WORKER_PROTOCOL_INVALID",
            )
        except Exception:
            if process is not None:
                await self._stop_process(process)
            self.repository.clear_worker_output(job_id)
            return self._terminal_transition(
                job_id,
                retryable=True,
                safe_error_code="KNOWLEDGE_PARSE_FAILED",
            )
        finally:
            async with self._active_lock:
                self._active.pop(job_id, None)

    async def cancel(self, job_id: int):
        job = self._refresh_job(job_id)
        async with self._active_lock:
            process = self._active.get(job_id)
        if process is not None and process.returncode is None:
            process.terminate()
        return job

    async def shutdown(self) -> None:
        async with self._active_lock:
            active = list(self._active.values())
        await asyncio.gather(
            *(self._stop_process(process) for process in active),
            return_exceptions=True,
        )


class KnowledgeImportCoordinator:
    def __init__(self, knowledge_root: Path) -> None:
        self.knowledge_root = Path(knowledge_root)
        self._tasks: dict[int, asyncio.Future] = {}
        self._services: dict[int, KnowledgeImportService] = {}
        self._worker_loops: dict[int, asyncio.AbstractEventLoop] = {}
        self._ready: dict[int, threading.Event] = {}
        self._skip_before_start: dict[int, threading.Event] = {}
        self._starting: set[int] = set()
        self._state_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="a3-knowledge-worker",
        )
        self._closed = False

    def enqueue(self, job_id: int) -> None:
        existing = self._tasks.get(job_id)
        if existing is not None and not existing.done():
            return
        asyncio.get_running_loop()
        if self._closed:
            raise RuntimeError("knowledge import coordinator is closed")
        ready = threading.Event()
        skip_before_start = threading.Event()
        self._ready[job_id] = ready
        self._skip_before_start[job_id] = skip_before_start
        task = asyncio.get_running_loop().run_in_executor(
            self._executor,
            self._run_in_worker_thread,
            job_id,
            ready,
            skip_before_start,
        )
        self._tasks[job_id] = task
        task.add_done_callback(
            lambda completed, value=job_id: self._finish_task(value, completed)
        )

    def _finish_task(self, job_id: int, task: asyncio.Future) -> None:
        self._tasks.pop(job_id, None)
        self._ready.pop(job_id, None)
        self._skip_before_start.pop(job_id, None)
        with self._state_lock:
            self._starting.discard(job_id)
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.warning(
                "knowledge import coordinator failed: job_id=%s code=KNOWLEDGE_PARSE_FAILED",
                job_id,
            )

    def _run_in_worker_thread(
        self,
        job_id: int,
        ready: threading.Event,
        skip_before_start: threading.Event,
    ) -> None:
        with self._state_lock:
            if skip_before_start.is_set():
                ready.set()
                return
            self._starting.add(job_id)
        try:
            asyncio.run(self._run(job_id))
        except Exception:
            try:
                self._mark_interrupted(job_id)
            except Exception:
                logger.warning(
                    "knowledge import recovery failed: job_id=%s code=KNOWLEDGE_PARSE_FAILED",
                    job_id,
                )
            raise
        finally:
            with self._state_lock:
                self._starting.discard(job_id)
            ready.set()

    def _mark_interrupted(self, job_id: int) -> None:
        db = SessionLocal()
        try:
            KnowledgeRepository(db, self.knowledge_root).mark_job_interrupted(job_id)
        finally:
            db.close()

    async def _run(self, job_id: int) -> None:
        db = SessionLocal()
        service = KnowledgeImportService(
            KnowledgeRepository(db, self.knowledge_root)
        )
        with self._state_lock:
            self._services[job_id] = service
            self._worker_loops[job_id] = asyncio.get_running_loop()
            self._starting.discard(job_id)
            ready = self._ready.get(job_id)
            if ready is not None:
                ready.set()
        try:
            await service.run_job(job_id)
        finally:
            with self._state_lock:
                self._services.pop(job_id, None)
                self._worker_loops.pop(job_id, None)
            db.close()

    async def cancel(self, job_id: int):
        task = self._tasks.get(job_id)
        ready = self._ready.get(job_id)
        if task is None:
            return None
        with self._state_lock:
            starting = job_id in self._starting
            skip_before_start = self._skip_before_start.get(job_id)
            if ready is not None and not ready.is_set() and not starting:
                if skip_before_start is not None:
                    skip_before_start.set()
                task.cancel()
                return None
        if ready is not None and not ready.is_set():
            await asyncio.to_thread(ready.wait)
        with self._state_lock:
            service = self._services.get(job_id)
            worker_loop = self._worker_loops.get(job_id)
        result = None
        if service is not None and worker_loop is not None and not worker_loop.is_closed():
            try:
                future = asyncio.run_coroutine_threadsafe(
                    service.cancel(job_id),
                    worker_loop,
                )
                result = await asyncio.wrap_future(future)
            except RuntimeError:
                result = None
        await asyncio.gather(task, return_exceptions=True)
        return result

    async def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        not_started: list[int] = []
        with self._state_lock:
            for job_id, ready in self._ready.items():
                if ready.is_set() or job_id in self._starting:
                    continue
                skip_before_start = self._skip_before_start.get(job_id)
                if skip_before_start is not None:
                    skip_before_start.set()
                task = self._tasks.get(job_id)
                if task is not None:
                    task.cancel()
                not_started.append(job_id)
        if not_started:
            await asyncio.gather(
                *(asyncio.to_thread(self._mark_interrupted, job_id) for job_id in not_started),
                return_exceptions=True,
            )
        with self._state_lock:
            active = [
                (service, self._worker_loops.get(job_id))
                for job_id, service in self._services.items()
            ]
        futures = []
        for service, worker_loop in active:
            if worker_loop is None or worker_loop.is_closed():
                continue
            try:
                futures.append(
                    asyncio.wrap_future(
                        asyncio.run_coroutine_threadsafe(
                            service.shutdown(),
                            worker_loop,
                        )
                    )
                )
            except RuntimeError:
                continue
        if futures:
            await asyncio.gather(*futures, return_exceptions=True)
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks.values()), return_exceptions=True)
        await asyncio.to_thread(
            lambda: self._executor.shutdown(wait=True, cancel_futures=True)
        )


def get_knowledge_import_coordinator(
    knowledge_root: Path,
) -> KnowledgeImportCoordinator:
    key = str(Path(knowledge_root).resolve())
    coordinator = _COORDINATORS.get(key)
    if coordinator is None:
        coordinator = KnowledgeImportCoordinator(Path(key))
        _COORDINATORS[key] = coordinator
    return coordinator


def recover_interrupted_import_jobs() -> int:
    db = SessionLocal()
    try:
        return KnowledgeRepository(db).mark_active_jobs_interrupted()
    finally:
        db.close()


async def shutdown_import_services() -> None:
    await asyncio.gather(
        *(coordinator.shutdown() for coordinator in tuple(_COORDINATORS.values())),
        return_exceptions=True,
    )
    await asyncio.gather(
        *(service.shutdown() for service in list(_SERVICES)),
        return_exceptions=True,
    )
    _COORDINATORS.clear()
