from __future__ import annotations

from backend.knowledge.chunking import (
    CHUNK_MAX,
    CHUNK_OVERLAP,
    chunk_blocks,
    cjk_search_tokens,
)
from backend.knowledge.parsers import StructuredBlock


def block(
    text: str,
    locator_type: str = "page",
    start: int = 1,
    end: int | None = None,
) -> StructuredBlock:
    return StructuredBlock(
        text=text,
        heading_path=("章节",),
        locator_type=locator_type,
        locator_start=start,
        locator_end=end or start,
    )


def test_chunks_do_not_cross_non_adjacent_pages() -> None:
    chunks = chunk_blocks(
        [
            block("第一章。" + "甲" * 700, start=1),
            block("第二章。" + "乙" * 700, start=3),
        ],
        parser_version="chunk-v1",
    )

    assert len(chunks) == 2
    assert [(item.locator_start, item.locator_end) for item in chunks] == [(1, 1), (3, 3)]
    assert all(600 <= len(item.text) <= CHUNK_MAX for item in chunks)


def test_long_paragraph_is_bounded_and_overlap_does_not_exceed_limit() -> None:
    text = "".join(f"句子{index:04d}。" for index in range(400))
    chunks = chunk_blocks([block(text, locator_type="paragraph")], parser_version="chunk-v1")

    assert len(chunks) > 2
    assert all(len(item.text) <= CHUNK_MAX for item in chunks)
    for previous, current in zip(chunks, chunks[1:]):
        suffix = previous.text[-CHUNK_OVERLAP:]
        overlap = max(
            (size for size in range(len(suffix) + 1) if current.text.startswith(suffix[-size:])),
            default=0,
        )
        assert overlap <= CHUNK_OVERLAP


def test_cjk_search_tokens_are_deterministic_single_and_bigram_terms() -> None:
    tokens = cjk_search_tokens("牛顿第二定律 Newton")
    values = tokens.split()

    assert "牛" in values
    assert "牛顿" in values
    assert "定律" in values
    assert "newton" in values
    assert tokens == cjk_search_tokens("牛顿第二定律 Newton")
