from __future__ import annotations

import asyncio

from backend.knowledge.ocr_engine import RapidOcrEngine, normalize_math_text


def test_normalize_math_text_preserves_formula_structure() -> None:
    assert normalize_math_text("  x²＋2x−1＝0  \n  α≤β  ") == "x^2+2x-1=0\nα≤β"
    assert normalize_math_text("当 × = 3 时，y = 7") == "当 x = 3 时,y = 7"


def test_rapid_ocr_engine_orders_lines_and_initializes_lazily() -> None:
    created = 0

    def factory():
        nonlocal created
        created += 1

        def runner(_image: bytes):
            return (
                [
                    [[[10, 40], [80, 40], [80, 60], [10, 60]], "第二行 x²", 0.98],
                    [[[10, 10], [80, 10], [80, 30], [10, 30]], "第一行 中文", 0.99],
                ],
                [0.01, 0.01, 0.01],
            )

        return runner

    async def exercise() -> None:
        engine = RapidOcrEngine(runner_factory=factory)
        first = await engine.recognize(b"png", page_number=1, width=100, height=100)
        second = await engine.recognize(b"png", page_number=2, width=100, height=100)
        assert first == "第一行 中文\n第二行 x^2"
        assert second == first
        assert created == 1
        await engine.close()

    asyncio.run(exercise())


def test_rapid_ocr_engine_returns_empty_text_for_no_detections() -> None:
    async def exercise() -> None:
        engine = RapidOcrEngine(runner_factory=lambda: lambda _image: (None, None))
        assert await engine.recognize(b"png", page_number=1, width=10, height=10) == ""
        await engine.close()

    asyncio.run(exercise())
