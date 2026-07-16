from __future__ import annotations

import html
import re
import unicodedata


_INVISIBLE_CONTROLS = dict.fromkeys(
    [
        0x061C,
        0x200B,
        0x200C,
        0x200D,
        0x200E,
        0x200F,
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,
        0x2060,
        0x2061,
        0x2062,
        0x2063,
        0x2064,
        0x2066,
        0x2067,
        0x2068,
        0x2069,
        0xFEFF,
    ],
    None,
)
_WHITESPACE = re.compile(r"\s+")


def normalize_for_scan(text: str) -> str:
    decoded = html.unescape(text)
    normalized = unicodedata.normalize("NFKC", decoded)
    visible = normalized.translate(_INVISIBLE_CONTROLS)
    return _WHITESPACE.sub(" ", visible.casefold()).strip()
