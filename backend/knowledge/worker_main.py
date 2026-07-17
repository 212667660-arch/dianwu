from __future__ import annotations

import os
from pathlib import Path
import socket
import sys
from typing import MutableMapping

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


def main() -> int:
    scrub_sensitive_environment(os.environ)
    disable_network()
    try:
        raw = sys.stdin.buffer.readline(131_073)
        request = WorkerRequest.model_validate_json(raw)
        path = safe_object_path(request)
        emit(ProgressEvent(progress=5, stage="parsing"))

        def report_parse_progress(current: int, total: int) -> None:
            emit(
                ProgressEvent(
                    progress=min(65, 5 + int(current * 60 / max(total, 1))),
                    stage="parsing",
                )
            )

        result = parse_document(
            path,
            ParserLimits(**request.limits),
            extension=request.extension,
            progress_callback=report_parse_progress,
        )
        total = max(len(result.blocks), 1)
        for ordinal, block in enumerate(result.blocks):
            emit(
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
            emit(
                ProgressEvent(
                    progress=min(90, 65 + int((ordinal + 1) * 25 / total)),
                    stage="parsing",
                )
            )
        emit(
            DoneEvent(
                page_count=result.page_count,
                slide_count=result.slide_count,
                sheet_count=result.sheet_count,
                text_characters=result.text_characters,
                ocr_required=result.ocr_required,
            )
        )
        return 0
    except KnowledgeParseError as exc:
        emit(FailureEvent(code=exc.code, retryable=exc.retryable))
        return 2
    except Exception:
        emit(FailureEvent(code="KNOWLEDGE_PARSE_FAILED", retryable=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
