from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
import inspect
from importlib.metadata import PackageNotFoundError, version
import re
import unicodedata


_SUPERSCRIPTS = str.maketrans(
    {
        "⁰": "^0",
        "¹": "^1",
        "²": "^2",
        "³": "^3",
        "⁴": "^4",
        "⁵": "^5",
        "⁶": "^6",
        "⁷": "^7",
        "⁸": "^8",
        "⁹": "^9",
        "⁺": "^+",
        "⁻": "^-",
        "⁼": "^=",
        "⁽": "^(",
        "⁾": "^)",
    }
)
_SUBSCRIPTS = str.maketrans(
    {
        "₀": "_0",
        "₁": "_1",
        "₂": "_2",
        "₃": "_3",
        "₄": "_4",
        "₅": "_5",
        "₆": "_6",
        "₇": "_7",
        "₈": "_8",
        "₉": "_9",
        "₊": "_+",
        "₋": "_-",
        "₌": "_=",
        "₍": "_(",
        "₎": "_)",
    }
)
_MATH_PUNCTUATION = str.maketrans(
    {
        "−": "-",
        "–": "-",
        "—": "-",
        "﹣": "-",
        "＋": "+",
        "＝": "=",
        "／": "/",
        "＊": "*",
        "（": "(",
        "）": ")",
        "［": "[",
        "］": "]",
        "｛": "{",
        "｝": "}",
    }
)


def normalize_math_text(value: str) -> str:
    translated = str(value or "").translate(_SUPERSCRIPTS).translate(_SUBSCRIPTS)
    translated = unicodedata.normalize("NFKC", translated).translate(_MATH_PUNCTUATION)
    lines = []
    for raw_line in translated.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"[\t \u3000]+", " ", raw_line).strip()
        line = re.sub(r"(?<!\d)×(?=\s*=)", "x", line)
        if line:
            lines.append(line)
    return "\n".join(lines)


def rapidocr_diagnostics() -> dict[str, str | bool | None]:
    try:
        from rapidocr_onnxruntime import RapidOCR  # noqa: F401
    except (ImportError, OSError) as exc:
        message = re.sub(r"[A-Za-z]:\\[^\r\n]+", "<local-path>", str(exc))
        return {
            "available": False,
            "version": rapidocr_version(),
            "error_type": type(exc).__name__,
            "error": message[:240],
        }
    return {
        "available": True,
        "version": rapidocr_version(),
        "error_type": None,
        "error": None,
    }


def rapidocr_available() -> bool:
    return bool(rapidocr_diagnostics()["available"])


def rapidocr_version() -> str | None:
    try:
        return version("rapidocr-onnxruntime")
    except PackageNotFoundError:
        return None


def _default_runner_factory():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _coordinates(item) -> tuple[float, float]:
    try:
        box = item[0]
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        return min(ys), min(xs)
    except (IndexError, TypeError, ValueError):
        return float("inf"), float("inf")


def _recognized_lines(raw_result) -> list[str]:
    detections = raw_result[0] if isinstance(raw_result, tuple) else raw_result
    if not detections:
        return []
    ordered = sorted(detections, key=_coordinates)
    lines: list[str] = []
    for item in ordered:
        try:
            text = normalize_math_text(str(item[1]))
        except (IndexError, TypeError):
            continue
        if text:
            lines.append(text)
    return lines


class RapidOcrEngine:
    def __init__(self, *, runner_factory: Callable[[], object] | None = None) -> None:
        self._runner_factory = runner_factory or _default_runner_factory
        self._runner: object | None = None
        self._lock = asyncio.Lock()

    async def _get_runner(self):
        if self._runner is not None:
            return self._runner
        async with self._lock:
            if self._runner is None:
                self._runner = await asyncio.to_thread(self._runner_factory)
        return self._runner

    async def recognize(
        self,
        image: bytes,
        *,
        page_number: int,
        width: int,
        height: int,
    ) -> str:
        del page_number, width, height
        runner = await self._get_runner()
        result = await asyncio.to_thread(runner, image)
        return "\n".join(_recognized_lines(result))

    async def close(self) -> None:
        runner, self._runner = self._runner, None
        if runner is None:
            return
        close = getattr(runner, "close", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result
