from __future__ import annotations

import asyncio
from pathlib import Path

import fitz
import pytest

from backend.knowledge.ocr import OcrLimits, ocr_pdf
from backend.knowledge.parsers import KnowledgeParseError
from backend.knowledge.worker_main import scrub_sensitive_environment


class FakeOcrEngine:
    def __init__(self, *, fail_page: int | None = None) -> None:
        self.fail_page = fail_page
        self.pages: list[tuple[int, int, int]] = []
        self.closed = False

    async def recognize(
        self,
        image: bytes,
        *,
        page_number: int,
        width: int,
        height: int,
    ) -> str:
        assert image.startswith(b"\x89PNG")
        self.pages.append((page_number, width, height))
        if page_number == self.fail_page:
            raise RuntimeError("engine failed")
        return f"第 {page_number} 页识别文本"

    async def close(self) -> None:
        self.closed = True


def _pdf(path: Path, pages: int, *, width: float = 595, height: float = 842) -> Path:
    document = fitz.open()
    for _ in range(pages):
        document.new_page(width=width, height=height)
    document.save(path)
    document.close()
    return path


def test_ocr_reports_each_page_and_stops_on_cancel(tmp_path: Path) -> None:
    async def exercise() -> None:
        cancel = asyncio.Event()
        engine = FakeOcrEngine()
        events = []
        async for event in ocr_pdf(_pdf(tmp_path / "scan.pdf", 4), engine, cancel):
            events.append(event)
            if event.page == 2:
                cancel.set()

        assert [event.page for event in events] == [1, 2]
        assert [event.block.locator_start for event in events] == [1, 2]
        assert events[-1].progress == 50
        assert engine.closed is True

    asyncio.run(exercise())


def test_ocr_scales_each_page_to_bounded_dimensions(tmp_path: Path) -> None:
    async def exercise() -> None:
        engine = FakeOcrEngine()
        events = [
            event
            async for event in ocr_pdf(
                _pdf(tmp_path / "wide.pdf", 1, width=9_000, height=500),
                engine,
                asyncio.Event(),
                limits=OcrLimits(max_dimension=4_096),
            )
        ]

        assert len(events) == 1
        assert max(engine.pages[0][1:]) <= 4_096
        assert engine.closed is True

    asyncio.run(exercise())


def test_ocr_closes_document_and_engine_when_recognition_fails(tmp_path: Path) -> None:
    async def exercise() -> None:
        engine = FakeOcrEngine(fail_page=1)
        with pytest.raises(RuntimeError, match="engine failed"):
            async for _event in ocr_pdf(
                _pdf(tmp_path / "broken.pdf", 1),
                engine,
                asyncio.Event(),
            ):
                pass
        assert engine.closed is True

    asyncio.run(exercise())


def test_ocr_timeout_is_retryable_and_closes_engine(tmp_path: Path) -> None:
    class SlowEngine(FakeOcrEngine):
        async def recognize(self, image: bytes, **kwargs) -> str:
            await asyncio.sleep(0.1)
            return await super().recognize(image, **kwargs)

    async def exercise() -> None:
        engine = SlowEngine()
        with pytest.raises(KnowledgeParseError) as exc_info:
            async for _event in ocr_pdf(
                _pdf(tmp_path / "slow.pdf", 1),
                engine,
                asyncio.Event(),
                limits=OcrLimits(max_seconds=0.01),
            ):
                pass
        assert exc_info.value.code == "KNOWLEDGE_OCR_TIMEOUT"
        assert exc_info.value.retryable is True
        assert engine.closed is True

    asyncio.run(exercise())


def test_ocr_continues_after_one_failed_page_and_reports_eta(tmp_path: Path) -> None:
    async def exercise() -> None:
        engine = FakeOcrEngine(fail_page=2)
        events = [
            event
            async for event in ocr_pdf(
                _pdf(tmp_path / "partial.pdf", 3),
                engine,
                asyncio.Event(),
                continue_on_error=True,
            )
        ]

        assert [event.page for event in events] == [1, 2, 3]
        assert events[1].block is None
        assert events[1].error_code == "KNOWLEDGE_OCR_PAGE_FAILED"
        assert events[2].block is not None
        assert events[2].eta_seconds == 0
        assert engine.closed is True

    asyncio.run(exercise())


def test_ocr_retries_only_selected_pages_with_original_page_locators(tmp_path: Path) -> None:
    async def exercise() -> None:
        engine = FakeOcrEngine()
        events = [
            event
            async for event in ocr_pdf(
                _pdf(tmp_path / "retry.pdf", 5),
                engine,
                asyncio.Event(),
                page_numbers=[2, 5],
            )
        ]

        assert [event.page for event in events] == [2, 5]
        assert [event.block.locator_start for event in events if event.block] == [2, 5]
        assert events[-1].progress == 100
        assert [item[0] for item in engine.pages] == [2, 5]

    asyncio.run(exercise())


def test_worker_main_scrubs_model_proxy_and_token_environment() -> None:
    environment = {
        "SYSTEMROOT": r"C:\Windows",
        "TEMP": r"C:\Temp",
        "A3_KNOWLEDGE_OBJECT_ROOT": r"C:\A3\objects",
        "A3_KNOWLEDGE_LIMITS": "{}",
        "OPENAI_API_KEY": "secret",
        "ANTHROPIC_API_KEY": "secret",
        "HTTPS_PROXY": "http://proxy",
        "DESKTOP_TOKEN": "desktop-secret",
        "UNRELATED": "value",
    }

    scrub_sensitive_environment(environment)

    assert environment == {
        "SYSTEMROOT": r"C:\Windows",
        "TEMP": r"C:\Temp",
        "A3_KNOWLEDGE_OBJECT_ROOT": r"C:\A3\objects",
        "A3_KNOWLEDGE_LIMITS": "{}",
    }
