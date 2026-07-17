from __future__ import annotations

import asyncio
from pathlib import Path

import fitz

from backend.knowledge.parsers import ParsedDocument
from backend.knowledge.worker_main import process_document_request
from backend.knowledge.worker_protocol import BlockEvent, DoneEvent, ProgressEvent, WorkerRequest


class FakeEngine:
    def __init__(self, fail_page: int | None = None) -> None:
        self.fail_page = fail_page

    async def recognize(self, _image: bytes, *, page_number: int, **_kwargs) -> str:
        if page_number == self.fail_page:
            raise RuntimeError("page failed")
        return f"第 {page_number} 页：x²＋1"

    async def close(self) -> None:
        return None


def _blank_pdf(path: Path, pages: int) -> Path:
    document = fitz.open()
    for _ in range(pages):
        document.new_page()
    document.save(path)
    document.close()
    return path


def _request(*, retry_pages: list[int] | None = None) -> WorkerRequest:
    return WorkerRequest(
        job_id=1,
        object_relpath="objects/" + "a" * 64,
        extension=".pdf",
        ocr_page_numbers=retry_pages or [],
    )


def _scan_result(_path, _limits, **_kwargs) -> ParsedDocument:
    return ParsedDocument(blocks=(), text_characters=0, page_count=3, ocr_required=True)


def test_worker_runs_offline_ocr_and_emits_real_page_locators(tmp_path: Path) -> None:
    async def exercise() -> None:
        events = []
        await process_document_request(
            _request(),
            _blank_pdf(tmp_path / "scan.pdf", 3),
            events.append,
            parser=_scan_result,
            ocr_available=lambda: True,
            ocr_engine_factory=FakeEngine,
        )

        blocks = [event for event in events if isinstance(event, BlockEvent)]
        assert [event.locator_start for event in blocks] == [1, 2, 3]
        assert blocks[0].text == "第 1 页：x²＋1"
        assert any(
            isinstance(event, ProgressEvent)
            and event.stage == "ocr"
            and event.current_page == 2
            and event.page_count == 3
            for event in events
        )
        done = next(event for event in events if isinstance(event, DoneEvent))
        assert done.ocr_performed is True
        assert done.ocr_required is False
        assert done.failed_pages == []
        assert done.text_characters > 0

    asyncio.run(exercise())


def test_worker_keeps_successful_pages_and_reports_failed_page(tmp_path: Path) -> None:
    async def exercise() -> None:
        events = []
        await process_document_request(
            _request(),
            _blank_pdf(tmp_path / "partial.pdf", 3),
            events.append,
            parser=_scan_result,
            ocr_available=lambda: True,
            ocr_engine_factory=lambda: FakeEngine(fail_page=2),
        )

        blocks = [event for event in events if isinstance(event, BlockEvent)]
        assert [event.locator_start for event in blocks] == [1, 3]
        done = next(event for event in events if isinstance(event, DoneEvent))
        assert done.failed_pages == [2]
        assert done.ocr_performed is True

    asyncio.run(exercise())


def test_worker_retries_only_requested_pages(tmp_path: Path) -> None:
    async def exercise() -> None:
        events = []
        await process_document_request(
            _request(retry_pages=[2]),
            _blank_pdf(tmp_path / "retry.pdf", 3),
            events.append,
            parser=_scan_result,
            ocr_available=lambda: True,
            ocr_engine_factory=FakeEngine,
        )
        blocks = [event for event in events if isinstance(event, BlockEvent)]
        assert [event.ordinal for event in blocks] == [1]
        assert [event.locator_start for event in blocks] == [2]

    asyncio.run(exercise())


def test_worker_stays_at_ocr_required_when_engine_is_unavailable(tmp_path: Path) -> None:
    async def exercise() -> None:
        events = []
        await process_document_request(
            _request(),
            _blank_pdf(tmp_path / "missing.pdf", 3),
            events.append,
            parser=_scan_result,
            ocr_available=lambda: False,
            ocr_engine_factory=FakeEngine,
        )
        done = next(event for event in events if isinstance(event, DoneEvent))
        assert done.ocr_required is True
        assert done.ocr_performed is False
        assert not any(isinstance(event, BlockEvent) for event in events)

    asyncio.run(exercise())
