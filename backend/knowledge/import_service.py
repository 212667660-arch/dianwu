from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
import inspect
import json
import os
from pathlib import Path
import sys
import weakref

from backend.database import SessionLocal
from backend.knowledge.chunking import chunk_blocks
from backend.knowledge.models import ImportJobStatus
from backend.knowledge.repository import KnowledgeRepository
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
    bootstrap = (
        "import runpy,sys;"
        + "sys.path.insert(0,"
        + repr(str(project_root))
        + ");"
        + "runpy.run_module('backend.knowledge.worker_main',run_name='__main__')"
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-X",
        "utf8",
        "-c",
        bootstrap,
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


class KnowledgeImportService:
    def __init__(
        self,
        repository,
        *,
        spawn_worker: Callable[[WorkerRequest], object] | None = None,
        parse_timeout_seconds: float = 120,
        termination_timeout_seconds: float = 2,
    ) -> None:
        self.repository = repository
        self.parse_timeout_seconds = parse_timeout_seconds
        self.termination_timeout_seconds = termination_timeout_seconds
        self._spawn_worker = spawn_worker
        self._active: dict[int, object] = {}
        self._active_lock = asyncio.Lock()
        self._normal_slots = asyncio.Semaphore(2)
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
        async with self._normal_slots:
            self._transition(job_id, ImportJobStatus.VALIDATING, 1)
            request = self._request_for(job_id)
            process = None
            try:
                process = await self._start_worker(request)
                async with self._active_lock:
                    self._active[job_id] = process
                self._transition(job_id, ImportJobStatus.PARSING, 5)
                done = await asyncio.wait_for(
                    self._consume(job_id, process),
                    timeout=self.parse_timeout_seconds,
                )
                current = self.repository.require_job(job_id)
                if current.cancel_requested:
                    self.repository.clear_worker_output(job_id)
                    return self._transition(
                        job_id,
                        ImportJobStatus.CANCELLED,
                        current.progress,
                        safe_error_code="KNOWLEDGE_IMPORT_CANCELLED",
                    )
                self.repository.finish_worker_output(job_id, done)
                self._transition(job_id, ImportJobStatus.INDEXING, 95)
                blocks = self.repository.worker_block_events(job_id)
                chunks = chunk_blocks(blocks, parser_version="chunk-v1")
                document_id = self.repository.require_job(job_id).document_id
                self.repository.replace_chunks(document_id, chunks)
                search = KnowledgeSearchRepository(self.repository.db)
                search.replace_document_index(document_id)
                self.repository.clear_worker_output(job_id)
                return self._transition(job_id, ImportJobStatus.COMPLETED, 100)
            except asyncio.TimeoutError:
                if process is not None:
                    await self._stop_process(process)
                self.repository.clear_worker_output(job_id)
                return self._transition(
                    job_id,
                    ImportJobStatus.FAILED,
                    self.repository.require_job(job_id).progress,
                    retryable=True,
                    safe_error_code="KNOWLEDGE_PARSE_TIMEOUT",
                )
            except WorkerReportedFailure as exc:
                if process is not None:
                    await self._stop_process(process)
                self.repository.clear_worker_output(job_id)
                return self._transition(
                    job_id,
                    ImportJobStatus.FAILED,
                    self.repository.require_job(job_id).progress,
                    retryable=exc.retryable,
                    safe_error_code=exc.code,
                )
            except WorkerProtocolError:
                if process is not None:
                    await self._stop_process(process)
                self.repository.clear_worker_output(job_id)
                return self._transition(
                    job_id,
                    ImportJobStatus.FAILED,
                    self.repository.require_job(job_id).progress,
                    retryable=False,
                    safe_error_code="KNOWLEDGE_WORKER_PROTOCOL_INVALID",
                )
            except Exception:
                if process is not None:
                    await self._stop_process(process)
                current = self.repository.require_job(job_id)
                self.repository.clear_worker_output(job_id)
                if current.cancel_requested:
                    return self._transition(
                        job_id,
                        ImportJobStatus.CANCELLED,
                        current.progress,
                        safe_error_code="KNOWLEDGE_IMPORT_CANCELLED",
                    )
                return self._transition(
                    job_id,
                    ImportJobStatus.FAILED,
                    current.progress,
                    retryable=True,
                    safe_error_code="KNOWLEDGE_PARSE_FAILED",
                )
            finally:
                async with self._active_lock:
                    self._active.pop(job_id, None)

    async def cancel(self, job_id: int):
        job = self.repository.request_cancel(job_id)
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


def recover_interrupted_import_jobs() -> int:
    db = SessionLocal()
    try:
        return KnowledgeRepository(db).mark_active_jobs_interrupted()
    finally:
        db.close()


async def shutdown_import_services() -> None:
    await asyncio.gather(
        *(service.shutdown() for service in list(_SERVICES)),
        return_exceptions=True,
    )
