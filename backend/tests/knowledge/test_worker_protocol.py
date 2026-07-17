from __future__ import annotations

import json

import pytest

from backend.knowledge.worker_protocol import (
    BlockEvent,
    DoneEvent,
    ProgressEvent,
    WorkerRequest,
    encode_worker_event,
    parse_worker_line,
)


def test_worker_protocol_round_trips_versioned_events() -> None:
    block = BlockEvent(
        ordinal=0,
        text="第一段",
        heading_path=["第一章"],
        locator_type="page",
        locator_start=1,
        locator_end=1,
    )
    parsed = parse_worker_line(encode_worker_event(block))
    assert parsed == block

    done = parse_worker_line(
        encode_worker_event(DoneEvent(page_count=1, text_characters=3))
    )
    assert isinstance(done, DoneEvent)
    assert done.page_count == 1


def test_worker_protocol_rejects_unknown_version_extra_fields_and_large_lines() -> None:
    with pytest.raises(ValueError):
        parse_worker_line('{"version":"knowledge-worker/v2","type":"done","text_characters":0}')
    with pytest.raises(ValueError):
        parse_worker_line(
            '{"version":"knowledge-worker/v1","type":"done","text_characters":0,"extra":1}'
        )
    with pytest.raises(ValueError):
        parse_worker_line(json.dumps({
            "version": "knowledge-worker/v1",
            "type": "block",
            "ordinal": 0,
            "text": "x" * 2_100_001,
            "heading_path": [],
            "locator_type": "paragraph",
            "locator_start": 1,
            "locator_end": 1,
        }))


def test_worker_protocol_rejects_invalid_locator_ranges() -> None:
    with pytest.raises(ValueError):
        BlockEvent(
            ordinal=0,
            text="bad",
            heading_path=[],
            locator_type="page",
            locator_start=3,
            locator_end=2,
        )


def test_worker_protocol_carries_ocr_progress_failures_and_retry_pages() -> None:
    request = WorkerRequest(
        job_id=7,
        object_relpath="objects/" + "a" * 64,
        extension=".pdf",
        ocr_page_numbers=[2, 5],
    )
    assert request.ocr_page_numbers == [2, 5]

    progress = ProgressEvent(
        progress=40,
        stage="ocr",
        current_page=2,
        page_count=5,
        eta_seconds=12,
        failed_pages=[1],
    )
    assert parse_worker_line(encode_worker_event(progress)) == progress

    done = DoneEvent(
        page_count=5,
        text_characters=800,
        ocr_performed=True,
        failed_pages=[2],
    )
    assert parse_worker_line(encode_worker_event(done)) == done


def test_worker_protocol_rejects_duplicate_or_unsorted_retry_pages() -> None:
    with pytest.raises(ValueError):
        WorkerRequest(
            job_id=7,
            object_relpath="objects/" + "a" * 64,
            extension=".pdf",
            ocr_page_numbers=[5, 2, 2],
        )
