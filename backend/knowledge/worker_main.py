from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys

from backend.knowledge.worker_protocol import (
    FailureEvent,
    WorkerRequest,
    encode_worker_event,
)


class NetworkDisabledError(OSError):
    pass


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
    sys.stdout.write(encode_worker_event(event) + "\n")
    sys.stdout.flush()


def main() -> int:
    disable_network()
    try:
        raw = sys.stdin.buffer.readline(131_073)
        request = WorkerRequest.model_validate_json(raw)
        safe_object_path(request)
        emit(FailureEvent(code="KNOWLEDGE_PARSER_NOT_IMPLEMENTED", retryable=True))
        return 2
    except Exception:
        emit(FailureEvent(code="KNOWLEDGE_PARSE_FAILED", retryable=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
