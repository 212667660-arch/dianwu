from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
import inspect
from pathlib import Path
from typing import Protocol

import fitz

from backend.knowledge.parsers import KnowledgeParseError, StructuredBlock


@dataclass(frozen=True)
class OcrLimits:
    max_pages: int = 2_000
    max_dimension: int = 4_096
    render_scale: float = 2.0
    max_seconds: float = 20 * 60


@dataclass(frozen=True)
class OcrPageEvent:
    page: int
    page_count: int
    progress: int
    block: StructuredBlock | None
    error_code: str | None = None
    eta_seconds: int | None = None


class OcrEngine(Protocol):
    async def recognize(
        self,
        image: bytes,
        *,
        page_number: int,
        width: int,
        height: int,
    ) -> str: ...

    async def close(self) -> None: ...


async def _close_engine(engine: OcrEngine) -> None:
    result = engine.close()
    if inspect.isawaitable(result):
        await result


async def ocr_pdf(
    path: Path,
    engine: OcrEngine,
    cancel,
    *,
    limits: OcrLimits | None = None,
    page_numbers: list[int] | tuple[int, ...] | None = None,
    continue_on_error: bool = False,
) -> AsyncIterator[OcrPageEvent]:
    selected_limits = limits or OcrLimits()
    document = None
    try:
        document = fitz.open(Path(path))
        if document.needs_pass:
            raise KnowledgeParseError("KNOWLEDGE_DOCUMENT_ENCRYPTED")
        page_count = len(document)
        if page_count > selected_limits.max_pages:
            raise KnowledgeParseError("KNOWLEDGE_PARSE_LIMIT_EXCEEDED")
        if page_numbers is None:
            selected_pages = list(range(1, page_count + 1))
        else:
            selected_pages = sorted(set(int(item) for item in page_numbers))
            if any(item < 1 or item > page_count for item in selected_pages):
                raise KnowledgeParseError("KNOWLEDGE_PARSE_LIMIT_EXCEEDED")
        deadline = asyncio.get_running_loop().time() + selected_limits.max_seconds
        started_at = asyncio.get_running_loop().time()
        for selected_index, page_number in enumerate(selected_pages, 1):
            if cancel.is_set():
                break
            page = document[page_number - 1]
            width = max(float(page.rect.width), 1.0)
            height = max(float(page.rect.height), 1.0)
            scale = min(
                selected_limits.render_scale,
                selected_limits.max_dimension / width,
                selected_limits.max_dimension / height,
            )
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(scale, scale),
                alpha=False,
            )
            try:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise asyncio.TimeoutError
                try:
                    text = await asyncio.wait_for(
                        engine.recognize(
                            pixmap.tobytes("png"),
                            page_number=page_number,
                            width=pixmap.width,
                            height=pixmap.height,
                        ),
                        timeout=remaining,
                    )
                except asyncio.TimeoutError as exc:
                    if not continue_on_error:
                        raise KnowledgeParseError(
                            "KNOWLEDGE_OCR_TIMEOUT",
                            retryable=True,
                        ) from exc
                    text = None
                    error_code = "KNOWLEDGE_OCR_TIMEOUT"
                except Exception:
                    if not continue_on_error:
                        raise
                    text = None
                    error_code = "KNOWLEDGE_OCR_PAGE_FAILED"
            finally:
                del pixmap
            elapsed = max(asyncio.get_running_loop().time() - started_at, 0.0)
            average = elapsed / max(selected_index, 1)
            remaining_pages = max(len(selected_pages) - selected_index, 0)
            eta_seconds = int(round(average * remaining_pages))
            progress = int(selected_index * 100 / max(len(selected_pages), 1))
            if text is None:
                yield OcrPageEvent(
                    page=page_number,
                    page_count=page_count,
                    progress=progress,
                    block=None,
                    error_code=error_code,
                    eta_seconds=eta_seconds,
                )
                continue
            yield OcrPageEvent(
                page=page_number,
                page_count=page_count,
                progress=progress,
                block=StructuredBlock(
                    text=str(text or "").strip(),
                    heading_path=(),
                    locator_type="page",
                    locator_start=page_number,
                    locator_end=page_number,
                ),
                eta_seconds=eta_seconds,
            )
    finally:
        if document is not None:
            document.close()
        await _close_engine(engine)
