from __future__ import annotations

import json

import pytest

from backend.knowledge.worker_protocol import (
    BlockEvent,
    DoneEvent,
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
