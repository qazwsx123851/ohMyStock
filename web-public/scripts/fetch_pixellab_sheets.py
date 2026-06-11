"""Fetch PixelLab walk animation frames and build 4-direction walk sheets.

Replaces the placeholder sheets from build_walk_sheets.py with real
AI-generated walk cycles. Sheet layout (consumed by src/canvas/assets.ts):

    4 rows  = facing down / up / left / right
    4 cols  = walk cycle frames 0-3
    cell    = common tight bbox across all 16 frames of a character

Downloads each character zip from the PixelLab API (requires the
PIXELLAB_API_KEY env var). Zip layout:

    <Name>/animations/animating/<south|north|west|east>/frame_00N.png

Characters generated 2026-06-11 in Pokemon Gen 2 overworld style
(48px, custom chibi proportions, walking-4-frames template, 68x68 canvas).
Re-running is idempotent.

Usage (from repo root):
    uv run --with pillow python web-public/scripts/fetch_pixellab_sheets.py
"""

from __future__ import annotations

import io
import os
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image

OFFICE = Path(__file__).resolve().parent.parent / "public" / "office"

API = "https://api.pixellab.ai/mcp/characters/{char_id}/download"

ROW_ORDER = ["down", "up", "left", "right"]  # must match FACING_ROW in assets.ts
DIR_NAME = {"down": "south", "up": "north", "left": "west", "right": "east"}

CHAR_IDS: dict[str, str] = {
    "proposer": "de7aaa2d-fb14-4fed-83c0-034024cc03c4",
    "decider": "69ae4c53-b940-4826-a699-95ae3f4c1bcb",
    "trader": "f16182ec-094f-4bd2-8e6e-2ca42f0b9fa8",
}


def download_zip(char_id: str, api_key: str) -> zipfile.ZipFile:
    req = urllib.request.Request(
        API.format(char_id=char_id),
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req) as resp:
        return zipfile.ZipFile(io.BytesIO(resp.read()))


def load_frames(zf: zipfile.ZipFile) -> dict[str, list[Image.Image]]:
    frames: dict[str, list[Image.Image]] = {}
    for facing in ROW_ORDER:
        d = DIR_NAME[facing]
        names = sorted(
            n for n in zf.namelist()
            if f"/animations/animating/{d}/" in n and n.endswith(".png")
        )
        if len(names) != 4:
            raise SystemExit(f"expected 4 frames for {d}, got {names}")
        frames[facing] = [
            Image.open(io.BytesIO(zf.read(n))).convert("RGBA") for n in names
        ]
    return frames


def union_bbox(frames: list[Image.Image]) -> tuple[int, int, int, int]:
    boxes = [f.getbbox() for f in frames]
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def build_sheet(name: str, frames: dict[str, list[Image.Image]]) -> None:
    x0, y0, x1, y1 = union_bbox([f for fs in frames.values() for f in fs])
    w, h = x1 - x0, y1 - y0
    sheet = Image.new("RGBA", (w * 4, h * 4), (0, 0, 0, 0))
    for row, facing in enumerate(ROW_ORDER):
        for col, frame in enumerate(frames[facing]):
            sheet.paste(frame.crop((x0, y0, x1, y1)), (col * w, row * h))
    sheet.save(OFFICE / f"sheet_{name}.png")
    print(f"sheet_{name}.png  cell {w}x{h}")


def main() -> None:
    api_key = os.environ.get("PIXELLAB_API_KEY")
    if not api_key:
        raise SystemExit("PIXELLAB_API_KEY env var is required")
    for name, char_id in CHAR_IDS.items():
        build_sheet(name, load_frames(download_zip(char_id, api_key)))


if __name__ == "__main__":
    main()
