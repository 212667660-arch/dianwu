from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from types import SimpleNamespace

from backend.knowledge.import_service import KnowledgeImportService, worker_environment
from backend.knowledge.models import ImportJobStatus


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

    def require_job(self, job_id: int) -> FakeJob:
        return self.jobs[job_id]

    def require_document(self, document_id: int):
        return self.documents[document_id]

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
            version=job.version + 1,
        )
        self.jobs[job_id] = job
        return job

    def request_cancel(self, job_id: int) -> FakeJob:
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

        cancelled = await service.cancel(7)
        await asyncio.wait_for(running, timeout=1)

        assert cancelled.cancel_requested is True
        assert process.terminated is True
        assert repository.require_job(7).status == ImportJobStatus.CANCELLED.value

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
