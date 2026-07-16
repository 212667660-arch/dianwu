from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field


class CitationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    used_references: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


_CITATION = re.compile(r"\[(资料[1-9]\d{0,2})\]")
_MARKDOWN_LINK = re.compile(r"\[[^\]\r\n]{1,300}\]\([^\)\r\n]{1,2048}\)")
_RAW_URL = re.compile(r"\b(?:https?|javascript|data|file|vbscript)\s*:[^\s<>{}]*", re.IGNORECASE)


def validate_citations(body: str, *, allowed: set[str]) -> CitationDecision:
    used = list(dict.fromkeys(match.group(1) for match in _CITATION.finditer(body)))
    reason_codes: list[str] = []
    if any(reference not in allowed for reference in used):
        reason_codes.append("CONTENT_CITATION_NOT_ALLOWED")
    if _MARKDOWN_LINK.search(body):
        reason_codes.append("MODEL_LINK_NOT_ALLOWED")
    if _RAW_URL.search(body):
        reason_codes.append("MODEL_URL_NOT_ALLOWED")
    reason_codes = list(dict.fromkeys(reason_codes))
    return CitationDecision(
        allowed=not reason_codes,
        used_references=used,
        reason_codes=reason_codes,
    )
