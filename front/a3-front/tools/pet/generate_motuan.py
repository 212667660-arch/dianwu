#!/usr/bin/env python3
"""Generate the original Mo Tuan desktop-pet atlas and manifest."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

CELL = (192, 208)
GRID = (8, 9)
SCALE = 3
ROWS = {
    "idle": [280, 110, 110, 140, 140, 320],
    "running-right": [120, 120, 120, 120, 120, 120, 120, 220],
    "running-left": [120, 120, 120, 120, 120, 120, 120, 220],
    "waving": [140, 140, 140, 280],
    "jumping": [140, 140, 140, 140, 280],
    "failed": [140, 140, 140, 140, 140, 140, 140, 240],
    "waiting": [150, 150, 150, 150, 150, 260],
    "running": [120, 120, 120, 120, 120, 220],
    "review": [150, 150, 150, 150, 150, 280],
}

INK = "#244f55"
INK_DARK = "#17383d"
INK_LIGHT = "#3d7073"
PAPER = "#fff4d8"
PAPER_SHADE = "#ead9ae"
AMBER = "#e2a34d"
AMBER_DARK = "#aa672b"
BLUSH = "#d97d77"
HIGHLIGHT = "#d9f0e8"


def sx(value: float) -> int:
    return round(value * SCALE)


def box(values: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return tuple(sx(value) for value in values)


def line(draw: ImageDraw.ImageDraw, values, *, fill, width=1, joint="curve") -> None:
    draw.line([(sx(x), sx(y)) for x, y in values], fill=fill, width=sx(width), joint=joint)


def ellipse(draw: ImageDraw.ImageDraw, values, *, fill, outline=None, width=1) -> None:
    draw.ellipse(box(values), fill=fill, outline=outline, width=sx(width))


def polygon(draw: ImageDraw.ImageDraw, values, *, fill) -> None:
    draw.polygon([(sx(x), sx(y)) for x, y in values], fill=fill)


def rounded(draw: ImageDraw.ImageDraw, values, radius, *, fill, outline=None, width=1) -> None:
    draw.rounded_rectangle(box(values), radius=sx(radius), fill=fill, outline=outline, width=sx(width))


def draw_frame(state: str, index: int, count: int) -> Image.Image:
    image = Image.new("RGBA", (CELL[0] * SCALE, CELL[1] * SCALE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    phase = index / max(1, count - 1)
    cycle = math.sin(phase * math.tau)
    bob = cycle * 2
    lean = 0
    facing = 1
    jump = 0
    eyes = "open"
    arm = None
    prop = None

    if state == "idle":
        bob = [0, -1, -2, -1, 0, 1][index]
        eyes = "closed" if index == 2 else "open"
    elif state.startswith("running-"):
        facing = 1 if state.endswith("right") else -1
        bob = -abs(cycle) * 4
        lean = facing * 5
    elif state == "waving":
        bob = [0, -1, 0, 1][index]
        arm = "wave-high" if index % 2 else "wave-side"
    elif state == "jumping":
        jump = [0, 18, 34, 18, 0][index]
        bob = -jump
        arm = "up"
    elif state == "failed":
        bob = [0, 1, 2, 3, 3, 2, 1, 0][index]
        lean = -3
        eyes = "sad"
        prop = "tear"
    elif state == "waiting":
        bob = [0, -1, -2, -1, 0, 1][index]
        eyes = "blink" if index == 4 else "open"
        prop = "question"
    elif state == "running":
        bob = -abs(cycle) * 2
        eyes = "focus"
        prop = "pencil"
    elif state == "review":
        bob = [0, -1, -1, 0, 1, 0][index]
        eyes = "focus"
        prop = "lens"

    cx = 96 + lean
    cy = 116 + bob
    draw_shadow(draw, cx, 185, jump)
    draw_tail(draw, cx, cy, facing, state, cycle)
    draw_body(draw, cx, cy, state, cycle)
    draw_cape(draw, cx, cy, lean)
    draw_legs(draw, cx, cy, state, facing, index)
    draw_arms(draw, cx, cy, arm, facing, state, index)
    draw_face(draw, cx, cy, eyes, state)
    draw_prop(draw, cx, cy, prop, index, count)

    return image.resize(CELL, Image.Resampling.LANCZOS)


def draw_shadow(draw, cx, ground, jump):
    width = max(22, 52 - jump * 0.55)
    alpha = max(20, 66 - round(jump * 1.2))
    ellipse(draw, (cx - width / 2, ground - 4, cx + width / 2, ground + 3), fill=(23, 56, 61, alpha))


def draw_tail(draw, cx, cy, facing, state, cycle):
    sway = cycle * 5
    if state.startswith("running-"):
        sway = -facing * 10
    start = (cx + facing * 35, cy + 29)
    end = (cx + facing * (55 + sway), cy + 54)
    line(draw, [start, (cx + facing * 48, cy + 40), end], fill=AMBER_DARK, width=8)
    rounded(draw, (end[0] - 6, end[1] - 8, end[0] + 6, end[1] + 9), 3, fill=AMBER)


def draw_body(draw, cx, cy, state, cycle):
    squash = 2 if state.startswith("running-") else 0
    polygon(draw, [
        (cx - 47, cy + 17), (cx - 41, cy - 25), (cx - 23, cy - 52),
        (cx, cy - 61 + squash), (cx + 25, cy - 51), (cx + 43, cy - 24),
        (cx + 48, cy + 22), (cx + 34, cy + 49), (cx, cy + 57 - squash),
        (cx - 34, cy + 48),
    ], fill=INK)
    ellipse(draw, (cx - 29, cy - 47, cx + 16, cy - 10), fill=INK_LIGHT)
    ellipse(draw, (cx - 18, cy - 43, cx - 4, cy - 28), fill=HIGHLIGHT)


def draw_cape(draw, cx, cy, lean):
    polygon(draw, [
        (cx - 38, cy - 7), (cx - 21, cy - 19), (cx + 25, cy - 16),
        (cx + 41, cy - 2), (cx + 28, cy + 20), (cx + 6, cy + 13),
        (cx - 13, cy + 24), (cx - 34, cy + 14),
    ], fill=PAPER)
    line(draw, [(cx - 30, cy + 4), (cx - 13, cy + 12), (cx + 5, cy + 3), (cx + 27, cy + 10)], fill=PAPER_SHADE, width=2)
    polygon(draw, [(cx + 20, cy + 13), (cx + 30, cy + 17), (cx + 24, cy + 38)], fill=AMBER)


def draw_legs(draw, cx, cy, state, facing, index):
    if state.startswith("running-"):
        step = 9 if index % 2 == 0 else -9
        line(draw, [(cx - 15, cy + 46), (cx - 18 + facing * step, cy + 63)], fill=INK_DARK, width=8)
        line(draw, [(cx + 15, cy + 46), (cx + 18 - facing * step, cy + 63)], fill=INK_DARK, width=8)
    else:
        line(draw, [(cx - 15, cy + 48), (cx - 18, cy + 61)], fill=INK_DARK, width=8)
        line(draw, [(cx + 15, cy + 48), (cx + 18, cy + 61)], fill=INK_DARK, width=8)
    ellipse(draw, (cx - 29, cy + 57, cx - 9, cy + 65), fill=INK_DARK)
    ellipse(draw, (cx + 9, cy + 57, cx + 29, cy + 65), fill=INK_DARK)


def draw_arms(draw, cx, cy, arm, facing, state, index):
    left_end = (cx - 48, cy + 18)
    right_end = (cx + 48, cy + 18)
    if arm == "wave-high":
        right_end = (cx + 48, cy - 46)
    elif arm == "wave-side":
        right_end = (cx + 60, cy - 25)
    elif arm == "up":
        left_end = (cx - 46, cy - 35)
        right_end = (cx + 46, cy - 35)
    elif state == "running":
        left_end = (cx - 36, cy + 28)
        right_end = (cx + 36, cy + 28)
    elif state == "review":
        right_end = (cx + 44, cy + 30)
    line(draw, [(cx - 31, cy + 3), left_end], fill=INK_DARK, width=9)
    line(draw, [(cx + 31, cy + 3), right_end], fill=INK_DARK, width=9)
    ellipse(draw, (left_end[0] - 6, left_end[1] - 6, left_end[0] + 6, left_end[1] + 6), fill=INK_LIGHT)
    ellipse(draw, (right_end[0] - 6, right_end[1] - 6, right_end[0] + 6, right_end[1] + 6), fill=INK_LIGHT)


def draw_face(draw, cx, cy, eyes, state):
    eye_y = cy - 28
    if eyes in {"closed", "blink"}:
        line(draw, [(cx - 21, eye_y), (cx - 11, eye_y + 2)], fill=INK_DARK, width=3)
        line(draw, [(cx + 11, eye_y + 2), (cx + 21, eye_y)], fill=INK_DARK, width=3)
    elif eyes == "sad":
        line(draw, [(cx - 22, eye_y + 2), (cx - 12, eye_y - 2)], fill=INK_DARK, width=3)
        line(draw, [(cx + 12, eye_y - 2), (cx + 22, eye_y + 2)], fill=INK_DARK, width=3)
    else:
        ellipse(draw, (cx - 23, eye_y - 5, cx - 11, eye_y + 8), fill=INK_DARK)
        ellipse(draw, (cx + 11, eye_y - 5, cx + 23, eye_y + 8), fill=INK_DARK)
        if eyes == "focus":
            ellipse(draw, (cx - 19, eye_y - 2, cx - 15, eye_y + 2), fill=AMBER)
            ellipse(draw, (cx + 15, eye_y - 2, cx + 19, eye_y + 2), fill=AMBER)
        else:
            ellipse(draw, (cx - 20, eye_y - 2, cx - 16, eye_y + 2), fill=PAPER)
            ellipse(draw, (cx + 14, eye_y - 2, cx + 18, eye_y + 2), fill=PAPER)
    ellipse(draw, (cx - 34, cy - 17, cx - 26, cy - 10), fill=BLUSH)
    ellipse(draw, (cx + 26, cy - 17, cx + 34, cy - 10), fill=BLUSH)
    if state == "failed":
        line(draw, [(cx - 6, cy - 10), (cx, cy - 14), (cx + 6, cy - 10)], fill=INK_DARK, width=2)
    else:
        line(draw, [(cx - 6, cy - 12), (cx, cy - 8), (cx + 6, cy - 12)], fill=INK_DARK, width=2)


def draw_prop(draw, cx, cy, prop, index, count):
    phase = index / max(1, count - 1)
    if prop == "tear":
        drop = 4 + phase * 17
        polygon(draw, [(cx + 20, cy - 18 + drop), (cx + 15, cy - 7 + drop), (cx + 25, cy - 7 + drop)], fill="#8dcfd5")
    elif prop == "question":
        float_y = -5 + math.sin(phase * math.tau) * 3
        ellipse(draw, (cx + 43, cy - 73 + float_y, cx + 68, cy - 48 + float_y), fill=PAPER, outline=AMBER_DARK, width=2)
        line(draw, [(cx + 54, cy - 67 + float_y), (cx + 59, cy - 63 + float_y), (cx + 54, cy - 57 + float_y)], fill=AMBER_DARK, width=2)
        ellipse(draw, (cx + 52, cy - 54 + float_y, cx + 56, cy - 50 + float_y), fill=AMBER_DARK)
    elif prop == "pencil":
        offset = math.sin(phase * math.tau) * 5
        line(draw, [(cx - 29, cy + 23), (cx + 30 + offset, cy + 6)], fill=AMBER, width=6)
        polygon(draw, [(cx + 30 + offset, cy + 6), (cx + 38 + offset, cy + 2), (cx + 34 + offset, cy + 11)], fill=PAPER_SHADE)
        line(draw, [(cx - 15, cy + 35), (cx + 23, cy + 35)], fill=PAPER, width=4)
    elif prop == "lens":
        sweep = math.sin(phase * math.tau) * 4
        ellipse(draw, (cx + 20 + sweep, cy + 5, cx + 52 + sweep, cy + 37), fill=(217, 240, 232, 105), outline=AMBER, width=5)
        line(draw, [(cx + 45 + sweep, cy + 31), (cx + 58 + sweep, cy + 46)], fill=AMBER_DARK, width=6)
        line(draw, [(cx - 29, cy + 31), (cx + 4, cy + 31)], fill=PAPER, width=5)


def manifest() -> dict[str, object]:
    return {
        "id": "motuan",
        "displayName": "墨团",
        "description": "住在书页边缘的青墨学习精灵，会陪你等待、创作与复核。",
        "spritesheetPath": "spritesheet.webp",
        "cell": {"width": CELL[0], "height": CELL[1]},
        "grid": {"columns": GRID[0], "rows": GRID[1]},
        "animations": {
            state: {"row": row, "durations": durations}
            for row, (state, durations) in enumerate(ROWS.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "electron" / "pets" / "motuan",
    )
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    atlas = Image.new("RGBA", (CELL[0] * GRID[0], CELL[1] * GRID[1]), (0, 0, 0, 0))
    for row, (state, durations) in enumerate(ROWS.items()):
        for column in range(len(durations)):
            atlas.alpha_composite(draw_frame(state, column, len(durations)), (column * CELL[0], row * CELL[1]))

    atlas.save(output / "spritesheet.webp", "WEBP", lossless=True, method=6, exact=True)
    (output / "pet.json").write_text(json.dumps(manifest(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output / 'spritesheet.webp'}")
    print(f"wrote {output / 'pet.json'}")


if __name__ == "__main__":
    main()
