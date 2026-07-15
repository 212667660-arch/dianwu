from __future__ import annotations

import asyncio
from hashlib import sha256
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import fitz
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.database import Base
from backend.knowledge.import_service import (
    KnowledgeImportService,
    knowledge_worker_command,
    worker_environment,
)
from backend.knowledge.models import ImportJobStatus
from backend.knowledge.repository import KnowledgeRepository
from backend.knowledge.schemas import KnowledgeChunkInput
from backend.knowledge.search import KnowledgeSearchRepository
from backend.knowledge.worker_protocol import DoneEvent, WorkerRequest, parse_worker_line
from backend.tests.knowledge.test_import_service import FakeRepository


TEN_MIB = 10 * 1024 * 1024


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _build_large_text_pdf(path: Path, *, target_bytes: int = TEN_MIB) -> Path:
    document = fitz.open()
    for index in range(80):
        page = document.new_page()
        page.insert_text((72, 72), f"Newton second law page {index + 1}: force equals mass times acceleration.")
    document.save(path)
    document.close()
    with path.open("ab") as stream:
        remaining = target_bytes - stream.tell()
        if remaining > 0:
            stream.write(b"%" + b"a" * (remaining - 1))
    return path


def _database(tmp_path: Path) -> tuple[object, Session, KnowledgeRepository]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'performance.sqlite3'}", future=True)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = Session(engine)
    return engine, db, KnowledgeRepository(db, tmp_path / "knowledge")


def test_ten_mib_text_pdf_import_finishes_under_thirty_seconds(tmp_path: Path) -> None:
    source = _build_large_text_pdf(tmp_path / "large.pdf")
    digest = sha256(source.read_bytes()).hexdigest()
    objects_root = tmp_path / "knowledge" / "objects"
    objects_root.mkdir(parents=True)
    shutil.copyfile(source, objects_root / digest)
    engine, db, repository = _database(tmp_path)
    collection = repository.create_collection("性能样本")
    document = repository.upsert_document(
        sha256=digest,
        display_name="large.pdf",
        extension=".pdf",
        mime_type="application/pdf",
        byte_size=source.stat().st_size,
        object_relpath=f"objects/{digest}",
    )
    repository.link_document(collection.id, document.id)
    job = repository.create_job(document.id)
    started = time.perf_counter()
    try:
        result = asyncio.run(KnowledgeImportService(repository).run_job(job.id))
        elapsed = time.perf_counter() - started
        print(f"knowledge_pdf_bytes={source.stat().st_size} import_seconds={elapsed:.3f}")
        assert result.status == ImportJobStatus.COMPLETED.value
        assert elapsed < 30
    finally:
        db.close()
        engine.dispose()


def test_ten_thousand_chunk_fts_queries_stay_under_p95_budget(tmp_path: Path) -> None:
    engine, db, repository = _database(tmp_path)
    collection = repository.create_collection("FTS 性能")
    document = repository.upsert_document(
        sha256="f" * 64,
        display_name="一万片段.txt",
        extension=".txt",
        mime_type="text/plain",
        byte_size=1,
        object_relpath="objects/" + "f" * 64,
    )
    repository.link_document(collection.id, document.id)
    chunks = []
    for ordinal in range(10_000):
        text = f"牛顿第二定律 样本 {ordinal} 力等于质量乘以加速度"
        chunks.append(
            KnowledgeChunkInput(
                ordinal=ordinal,
                text=text,
                text_sha256=sha256(text.encode("utf-8")).hexdigest(),
                heading_path="物理",
                locator_type="paragraph",
                locator_start=ordinal + 1,
                locator_end=ordinal + 1,
                token_estimate=20,
                parser_version="chunk-v1",
            )
        )
    try:
        repository.replace_chunks(document.id, chunks)
        search = KnowledgeSearchRepository(db)
        search.replace_document_index(document.id)
        for _ in range(5):
            assert search.search("牛顿 定律", [collection.id], limit=8)
        timings = []
        for _ in range(100):
            started = time.perf_counter()
            assert search.search("牛顿 定律", [collection.id], limit=8)
            timings.append(time.perf_counter() - started)
        p95 = _p95(timings)
        print(f"knowledge_chunks=10000 queries=100 p95_ms={p95 * 1000:.3f}")
        assert p95 < 0.2
    finally:
        db.close()
        engine.dispose()


def test_real_worker_cancellation_exits_under_two_seconds() -> None:
    async def exercise() -> tuple[float, object]:
        repository = FakeRepository()
        child: asyncio.subprocess.Process | None = None

        async def spawn(_request: WorkerRequest):
            nonlocal child
            child = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                "import time; time.sleep(30)",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return child

        service = KnowledgeImportService(repository, spawn_worker=spawn, parse_timeout_seconds=60)
        running = asyncio.create_task(service.run_job(7))
        while child is None:
            await asyncio.sleep(0.005)
        repository.request_cancel(7)
        started = time.perf_counter()
        await service.cancel(7)
        result = await running
        return time.perf_counter() - started, result

    elapsed, result = asyncio.run(exercise())
    print(f"knowledge_cancel_seconds={elapsed:.3f}")
    assert elapsed < 2
    assert result.status == ImportJobStatus.CANCELLED.value


def test_health_liveness_stays_responsive_while_worker_is_active(tmp_path: Path) -> None:
    from backend.main import app

    source = _build_large_text_pdf(tmp_path / "health-load.pdf")
    digest = sha256(source.read_bytes()).hexdigest()
    objects_root = tmp_path / "knowledge" / "objects"
    objects_root.mkdir(parents=True)
    shutil.copyfile(source, objects_root / digest)
    project_root = Path(__file__).resolve().parents[3]
    request = WorkerRequest(
        job_id=1,
        object_relpath=f"objects/{digest}",
        extension=".pdf",
        limits={},
    )
    process = subprocess.Popen(
        knowledge_worker_command(project_root),
        cwd=project_root,
        env=worker_environment(os.environ, object_root=str(objects_root), limits={}),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert process.stdin is not None
    process.stdin.write((request.model_dump_json() + "\n").encode("utf-8"))
    process.stdin.close()
    process.stdin = None
    timings = []
    try:
        with TestClient(app) as client:
            for _ in range(100):
                started = time.perf_counter()
                assert client.get("/health/live").status_code == 200
                timings.append(time.perf_counter() - started)
        stdout, _ = process.communicate(timeout=30)
        events = [parse_worker_line(line) for line in stdout.splitlines()]
        p95 = _p95(timings)
        print(f"health_requests=100 p95_ms={p95 * 1000:.3f}")
        assert process.returncode == 0
        assert isinstance(events[-1], DoneEvent)
        assert p95 < 0.5
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
