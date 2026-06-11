"""Extract web-public office assets from the UI design mockup.

The design mockup (UI_Design.png) is AI-generated faux pixel art — no clean
pixel grid — so the office background is used verbatim as a canvas image
asset, baked-in characters are patched out with cloned floor, and each
character is extracted as a transparent sprite.

Usage (from repo root):
    uv run --with pillow python web-public/scripts/extract_office_assets.py \
        --src "C:/Users/Oolong/Desktop/ohMyStock_UI/UI_Design.png" \
        --out web-public/public/office

Outputs:
    office-bg.png      cropped office (frame included), characters removed
    char_<name>.png    transparent character sprites
    debug_grid.png     16-px grid overlay for coordinate calibration (always)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

# Only the three STANDING characters are extracted as dynamic sprites; the
# four seated workers stay baked into the background (they are visually fused
# with their tall-back chairs and desks). Boxes in ORIGINAL image coordinates.
CHAR_BOXES: dict[str, tuple[int, int, int, int]] = {
    "proposer": (574, 216, 615, 273),
    "decider": (553, 317, 600, 367),
    "trader": (699, 255, 743, 309),
}

# Which box edges seed the background flood fill. The trader is cut off by
# the counter, so his bottom edge is body — not background.
SEED_EDGES: dict[str, tuple[bool, bool, bool, bool]] = {  # top, bottom, left, right
    "proposer": (True, True, True, True),
    "decider": (True, True, True, True),
    "trader": (True, False, True, True),
}

# Clean-floor source top-left per character for patching (same size as box).
PATCH_SRC: dict[str, tuple[int, int]] = {
    "proposer": (553, 369),
    "decider": (553, 369),
    "trader": (610, 255),
}

DARK_LUM = 70  # flood-fill stops at near-black sprite outlines


def find_frame_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    """Locate the dark office frame by scanning for near-black runs."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    px = rgb.load()

    def lum(p: tuple[int, int, int]) -> float:
        return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]

    # scan the row/column through the office centre (left half of the page)
    cy, cx = 300, 560
    xs = [x for x in range(200, min(1000, w)) if lum(px[x, cy]) < 50]
    ys = [y for y in range(60, min(700, h)) if lum(px[cx, y]) < 50]
    if not xs or not ys:
        raise SystemExit("frame not found — check --src image")
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def extract_sprite(
    img: Image.Image,
    box: tuple[int, int, int, int],
    seed_edges: tuple[bool, bool, bool, bool],
) -> Image.Image:
    """Cut a character box and remove the floor via border flood fill.

    Only floor-like pixels (low chroma, greenish-neutral, not dark) are
    removed — the AI art has soft anti-aliased outlines with gaps, so a pure
    luminance fill leaks into caps and shirts.
    """
    cell = img.convert("RGBA").crop(box)
    w, h = cell.size
    px = cell.load()

    def is_floor(p) -> bool:
        r, g, b = p[0], p[1], p[2]
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        chroma = max(r, g, b) - min(r, g, b)
        return lum >= DARK_LUM and chroma < 50 and g >= r - 10

    top, bottom, left, right = seed_edges
    stack: list[tuple[int, int]] = []
    if top:
        stack += [(x, 0) for x in range(w)]
    if bottom:
        stack += [(x, h - 1) for x in range(w)]
    if left:
        stack += [(0, y) for y in range(h)]
    if right:
        stack += [(w - 1, y) for y in range(h)]

    seen = [[False] * h for _ in range(w)]
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= w or y >= h or seen[x][y]:
            continue
        seen[x][y] = True
        if not is_floor(px[x, y]):
            continue  # outline or garment — stop
        px[x, y] = (0, 0, 0, 0)
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return cell


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--debug-only", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    img = Image.open(args.src)

    frame = find_frame_bbox(img)
    print(f"frame bbox: {frame}  size: {frame[2]-frame[0]}x{frame[3]-frame[1]}")

    # Debug overlay: 16-px grid in FRAME-relative coordinates
    dbg = img.crop(frame).convert("RGB")
    d = ImageDraw.Draw(dbg)
    for gx in range(0, dbg.width, 16):
        d.line([(gx, 0), (gx, dbg.height)], fill=(255, 0, 255), width=1)
        if gx % 64 == 0:
            d.text((gx + 1, 1), str(gx // 16), fill=(255, 0, 255))
    for gy in range(0, dbg.height, 16):
        d.line([(0, gy), (dbg.width, gy)], fill=(255, 0, 255), width=1)
        if gy % 64 == 0:
            d.text((1, gy + 1), str(gy // 16), fill=(255, 0, 255))
    dbg.save(out / "debug_grid.png")
    print(f"debug grid saved -> {out / 'debug_grid.png'}")
    if args.debug_only:
        return

    # Extract sprites BEFORE patching
    for name, box in CHAR_BOXES.items():
        sprite = extract_sprite(img, box, SEED_EDGES[name])
        sprite.save(out / f"char_{name}.png")
        print(f"char_{name}.png  {sprite.size}")

    # Patch characters out of the background with cloned floor
    bg_full = img.convert("RGB").copy()
    for name, box in CHAR_BOXES.items():
        sx, sy = PATCH_SRC[name]
        src_box = (sx, sy, sx + (box[2] - box[0]), sy + (box[3] - box[1]))
        patch = bg_full.crop(src_box)
        bg_full.paste(patch, (box[0], box[1]))

    bg = bg_full.crop(frame)
    bg.save(out / "office-bg.png")
    print(f"office-bg.png  {bg.size}")


if __name__ == "__main__":
    main()
