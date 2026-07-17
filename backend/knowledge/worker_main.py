from __future__ import annotations

import asyncio
import os
from pathlib import Path
import socket
import sys
from typing import Callable, MutableMapping

from backend.knowledge.ocr import ocr_pdf
from backend.knowledge.ocr_engine import RapidOcrEngine, rapidocr_available

from backend.knowledge.worker_protocol import (
    BlockEvent,
    DoneEvent,
    FailureEvent,
    ProgressEvent,
    WorkerRequest,
    encode_worker_event,
)
from backend.knowledge.parsers import KnowledgeParseError, ParserLimits, parse_document


class NetworkDisabledError(OSError):
    pass


def scrub_sensitive_environment(environment: MutableMapping[str, str]) -> None:
    allowed = {
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "PYTHONUTF8",
        "PYTHONNOUSERSITE",
    }
    for key in tuple(environment):
        if key in allowed or key.startswith("A3_KNOWLEDGE_"):
            continue
        environment.pop(key, None)


def disable_network() -> None:
    def denied(*_args, **_kwargs):
        raise NetworkDisabledError("network access is disabled for knowledge workers")

    socket.create_connection = denied
    socket.getaddrinfo = denied


def safe_object_path(request: WorkerRequest) -> Path:
    root = Path(os.environ["A3_KNOWLEDGE_OBJECT_ROOT"]).resolve(strict=True)
    candidate = (root.parent / request.object_relpath).resolve(strict=True)
    candidate.relative_to(root)
    if not candidate.is_file():
        raise ValueError("knowledge object is not a file")
    return candidate


def emit(event) -> None:
    sys.stdout.buffer.write((encode_worker_event(event) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


async def process_document_request(
    request: WorkerRequest,
    path: Path,
    emit_event: Callable[[object], None],
    *,
    parser=parse_document,
    ocr_available=rapidocr_available,
    ocr_engine_factory=RapidOcrEngine,
) -> None:
    emit_event(ProgressEvent(progress=5, stage="parsing"))

    def report_parse_progress(current: int, total: int) -> None:
        emit_event(
            ProgressEvent(
                progress=min(65, 5 + int(current * 60 / max(total, 1))),
                stage="parsing",
            )
        )

    result = parser(
        path,
        ParserLimits(**request.limits),
        extension=request.extension,
        progress_callback=report_parse_progress,
    )
    if result.ocr_required:
        if request.extension != ".pdf" or not ocr_available():
            emit_event(
                DoneEvent(
                    page_count=result.page_count,
                    slide_count=result.slide_count,
                    sheet_count=result.sheet_count,
                    text_characters=result.text_characters,
                    ocr_required=True,
                )
            )
            return
        failed_pages: list[int] = []
        text_characters = 0
        engine = ocr_engine_factory()
        async for page_event in ocr_pdf(
            path,
            engine,
            asyncio.Event(),
            page_numbers=request.ocr_page_numbers or None,
            continue_on_error=True,
        ):
            if page_event.block is None:
                failed_pages.append(page_event.page)
            elif page_event.block.text:
                text_characters += len(page_event.block.text)
                emit_event(
                    BlockEvent(
                        ordinal=page_event.page - 1,
                        text=page_event.block.text,
                        heading_path=list(page_event.block.heading_path),
                        locator_type=page_event.block.locator_type,
                        locator_start=page_event.block.locator_start,
                        locator_end=page_event.block.locator_end,
                        sheet_name=page_event.block.sheet_name,
                    )
                )
            emit_event(
                ProgressEvent(
                    progress=min(90, 10 + int(page_event.progress * 0.8)),
                    stage="ocr",
                    current_page=page_event.page,
                    page_count=page_event.page_count,
                    eta_seconds=page_event.eta_seconds,
                    failed_pages=failed_pages,
                )
            )
        emit_event(
            DoneEvent(
                page_count=result.page_count,
                slide_count=result.slide_count,
                sheet_count=result.sheet_count,
                text_characters=text_characters,
                ocr_performed=True,
                failed_pages=failed_pages,
            )
        )
        return

    total = max(len(result.blocks), 1)
    for ordinal, block in enumerate(result.blocks):
        emit_event(
            BlockEvent(
                ordinal=ordinal,
                text=block.text,
                heading_path=list(block.heading_path),
                locator_type=block.locator_type,
                locator_start=block.locator_start,
                locator_end=block.locator_end,
                sheet_name=block.sheet_name,
            )
        )
        emit_event(
            ProgressEvent(
                progress=min(90, 65 + int((ordinal + 1) * 25 / total)),
                stage="parsing",
            )
        )
    emit_event(
        DoneEvent(
            page_count=result.page_count,
            slide_count=result.slide_count,
            sheet_count=result.sheet_count,
            text_characters=result.text_characters,
            ocr_required=False,
        )
    )


def main() -> int:
    scrub_sensitive_environment(os.environ)
    disable_network()
    try:
        raw = sys.stdin.buffer.readline(131_073)
        request = WorkerRequest.model_validate_json(raw)
        path = safe_object_path(request)
        asyncio.run(process_document_request(request, path, emit))
        return 0
    except KnowledgeParseError as exc:
        emit(FailureEvent(code=exc.code, retryable=exc.retryable))
        return 2
    except Exception:
        emit(FailureEvent(code="KNOWLEDGE_PARSE_FAILED", retryable=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
