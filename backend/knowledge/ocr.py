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
    block: StructuredBlock


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
        deadline = asyncio.get_running_loop().time() + selected_limits.max_seconds
        for page_number, page in enumerate(document, 1):
            if cancel.is_set():
                break
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
                    raise KnowledgeParseError(
                        "KNOWLEDGE_OCR_TIMEOUT",
                        retryable=True,
                    ) from exc
            finally:
                del pixmap
            yield OcrPageEvent(
                page=page_number,
                page_count=page_count,
                progress=int(page_number * 100 / max(page_count, 1)),
                block=StructuredBlock(
                    text=str(text or "").strip(),
                    heading_path=(),
                    locator_type="page",
                    locator_start=page_number,
                    locator_end=page_number,
                ),
            )
    finally:
        if document is not None:
            document.close()
        await _close_engine(engine)
