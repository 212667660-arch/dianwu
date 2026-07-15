from __future__ import annotations

from hashlib import sha256
import math
import re
import unicodedata

from backend.knowledge.parsers import StructuredBlock
from backend.knowledge.schemas import KnowledgeChunkInput


CHUNK_MIN = 600
CHUNK_TARGET = 900
CHUNK_MAX = 1_000
CHUNK_OVERLAP = 120
_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")
_LATIN_TERM = re.compile(r"[a-z0-9]+")
_BREAK_CHARACTERS = frozenset("。！？；.!?;\n")


def cjk_search_tokens(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    tokens: list[str] = _LATIN_TERM.findall(normalized)
    for run in _CJK_RUN.findall(normalized):
        tokens.extend(run)
        tokens.extend(run[index:index + 2] for index in range(len(run) - 1))
    return " ".join(dict.fromkeys(token for token in tokens if token))


def _split_text(value: str) -> list[str]:
    text = value.strip()
    if len(text) <= CHUNK_MAX:
        return [text] if text else []
    pieces: list[str] = []
    start = 0
    while start < len(text):
        remaining = len(text) - start
        if remaining <= CHUNK_MAX:
            piece = text[start:].strip()
            if piece:
                pieces.append(piece)
            break
        upper = start + CHUNK_MAX
        lower = start + CHUNK_MIN
        boundary = next(
            (
                index + 1
                for index in range(upper - 1, lower - 1, -1)
                if text[index] in _BREAK_CHARACTERS
            ),
            upper,
        )
        piece = text[start:boundary].strip()
        if piece:
            pieces.append(piece)
        next_start = max(boundary - CHUNK_OVERLAP, start + 1)
        start = next_start
    return pieces


def _compatible(left: StructuredBlock, right: StructuredBlock) -> bool:
    return (
        left.locator_type == right.locator_type
        and left.sheet_name == right.sheet_name
        and tuple(left.heading_path) == tuple(right.heading_path)
        and right.locator_start <= left.locator_end + 1
    )


def _expanded(blocks: list[StructuredBlock]) -> list[StructuredBlock]:
    result: list[StructuredBlock] = []
    for block in blocks:
        for piece in _split_text(block.text):
            result.append(
                StructuredBlock(
                    text=piece,
                    heading_path=tuple(block.heading_path),
                    locator_type=block.locator_type,
                    locator_start=block.locator_start,
                    locator_end=block.locator_end,
                    sheet_name=block.sheet_name,
                )
            )
    return result


def _merge_blocks(blocks: list[StructuredBlock]) -> list[StructuredBlock]:
    merged: list[StructuredBlock] = []
    for block in blocks:
        if not merged:
            merged.append(block)
            continue
        previous = merged[-1]
        combined = previous.text + "\n\n" + block.text
        if _compatible(previous, block) and len(combined) <= CHUNK_MAX:
            merged[-1] = StructuredBlock(
                text=combined,
                heading_path=previous.heading_path,
                locator_type=previous.locator_type,
                locator_start=previous.locator_start,
                locator_end=max(previous.locator_end, block.locator_end),
                sheet_name=previous.sheet_name,
            )
        else:
            merged.append(block)
    return merged


def chunk_blocks(
    blocks,
    *,
    parser_version: str,
) -> list[KnowledgeChunkInput]:
    normalized = [
        StructuredBlock(
            text=block.text,
            heading_path=tuple(block.heading_path),
            locator_type=block.locator_type,
            locator_start=block.locator_start,
            locator_end=block.locator_end,
            sheet_name=block.sheet_name,
        )
        for block in blocks
    ]
    merged = _merge_blocks(_expanded(normalized))
    return [
        KnowledgeChunkInput(
            ordinal=ordinal,
            text=block.text,
            text_sha256=sha256(block.text.encode("utf-8")).hexdigest(),
            heading_path=" > ".join(block.heading_path),
            locator_type=block.locator_type,
            locator_start=block.locator_start,
            locator_end=block.locator_end,
            sheet_name=block.sheet_name,
            token_estimate=max(1, math.ceil(len(block.text) / 4)),
            parser_version=parser_version,
        )
        for ordinal, block in enumerate(merged)
    ]
