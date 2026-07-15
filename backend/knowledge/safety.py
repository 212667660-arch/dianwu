from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def _clean_label(value: object, limit: int) -> str:
    return _CONTROL_CHARACTERS.sub("", str(value or "")).strip()[:limit]


def safe_document_name(value: object) -> str:
    raw = _clean_label(value, 2048)
    if not raw:
        return "本地资料"

    candidate = raw
    if raw.lower().startswith("file://"):
        candidate = unquote(urlsplit(raw).path)
    elif _URI_SCHEME.match(raw) and not _WINDOWS_DRIVE_PATH.match(raw):
        return "本地资料"

    if "/" in candidate or "\\" in candidate:
        candidate = candidate.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    candidate = _clean_label(unquote(candidate), 255)
    if not candidate or candidate in {".", ".."}:
        return "本地资料"
    if "/" in candidate or "\\" in candidate or _URI_SCHEME.match(candidate):
        return "本地资料"
    return candidate


def safe_sheet_name(value: object) -> str:
    candidate = _clean_label(value, 128)
    if (
        not candidate
        or "/" in candidate
        or "\\" in candidate
        or _URI_SCHEME.match(candidate)
    ):
        return "工作表"
    return candidate


def build_locator_label(
    locator_type: str,
    start: int,
    end: int,
    sheet_name: str | None = None,
) -> str:
    if locator_type == "page":
        return f"第 {start} 页" if start == end else f"第 {start}–{end} 页"
    if locator_type == "slide":
        return f"第 {start} 张幻灯片" if start == end else f"第 {start}–{end} 张幻灯片"
    if locator_type == "sheet_rows":
        safe_name = safe_sheet_name(sheet_name)
        rows = f"第 {start} 行" if start == end else f"第 {start}–{end} 行"
        return f"{safe_name} · {rows}"
    return f"第 {start} 段" if start == end else f"第 {start}–{end} 段"
