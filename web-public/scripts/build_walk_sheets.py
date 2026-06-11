"""Build 4-direction walk sprite sheets from the extracted mockup sprites.

Placeholder synthesis until hand-curated / AI-generated (PixelLab etc.)
sheets replace the same files — the runtime only knows the sheet layout:

    4 rows  = facing down / up / left / right
    4 cols  = stand / step-A / stand / step-B
    cell    = original sprite size (w × h)

Base poses available from the mockup:
    proposer, trader  → front (down) view
    decider           → back (up) view

Derivations: front↔back via face paint / face removal, side views via a
1-px lean of the nearest available view, walk steps via alternating leg
lifts.

Usage (from repo root):
    uv run --with pillow python web-public/scripts/build_walk_sheets.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

OFFICE = Path(__file__).resolve().parent.parent / "public" / "office"

# base facing per character: which view the extracted sprite shows
BASE_FACING: dict[str, str] = {
    "proposer": "down",
    "decider": "up",
    "trader": "down",
}

ROW_ORDER = ["down", "up", "left", "right"]


def lum(p: tuple[int, int, int, int]) -> float:
    return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]


def is_skinish(p: tuple[int, int, int, int]) -> bool:
    r, g, b, a = p
    if a < 200:
        return False
    return r > 165 and g > 110 and b < 185 and r > b and (r - b) > 25


def opaque_rows(img: Image.Image) -> tuple[int, int]:
    px = img.load()
    w, h = img.size
    top, bottom = h, 0
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > 100:
                top = min(top, y)
                bottom = max(bottom, y)
                break
    return top, bottom


def dominant_hair(img: Image.Image, top: int) -> tuple[int, int, int, int]:
    """Most common opaque non-outline colour in the top rows (hair / cap)."""
    px = img.load()
    w = img.width
    counts: dict[tuple[int, int, int, int], int] = {}
    for y in range(top + 1, top + 7):
        for x in range(w):
            p = px[x, y]
            if p[3] > 200 and lum(p) > 45:
                counts[p] = counts.get(p, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else (40, 40, 50, 255)


def front_to_back(img: Image.Image) -> Image.Image:
    """Remove the face: skin / eyes / glasses in the head band → hair."""
    out = img.copy()
    px = out.load()
    w, h = out.size
    top, bottom = opaque_rows(out)
    hair = dominant_hair(out, top)
    head_end = top + int((bottom - top) * 0.55)
    for y in range(top, head_end):
        for x in range(w):
            p = px[x, y]
            if p[3] < 200:
                continue
            if is_skinish(p) or lum(p) > 190 or (lum(p) < 45 and top + 4 < y < head_end - 2):
                px[x, y] = hair
    return out


def back_to_front(img: Image.Image) -> Image.Image:
    """Paint a simple face band (skin + two eye dots) under the cap/hair."""
    out = img.copy()
    px = out.load()
    w, h = out.size
    top, bottom = opaque_rows(out)
    head_h = int((bottom - top) * 0.5)
    face_y0 = top + int(head_h * 0.6)
    face_y1 = top + int(head_h * 0.95)
    skin = (239, 200, 158, 255)
    for y in range(face_y0, face_y1):
        # span between the dark outline columns of this row
        xs = [x for x in range(w) if px[x, y][3] > 200 and lum(px[x, y]) > 40]
        if len(xs) < 6:
            continue
        x0, x1 = min(xs) + 3, max(xs) - 3
        for x in range(x0, x1 + 1):
            px[x, y] = skin
    # eyes
    mid = w // 2
    ey = face_y0 + max(1, (face_y1 - face_y0) // 3)
    for ex in (mid - 5, mid + 4):
        for dx in range(2):
            for dy in range(2):
                if 0 <= ex + dx < w:
                    px[ex + dx, ey + dy] = (25, 25, 30, 255)
    return out


def lean(img: Image.Image, dx: int) -> Image.Image:
    """Shift the upper body 1 px sideways — placeholder side view."""
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    top, bottom = opaque_rows(img)
    split = top + int((bottom - top) * 0.6)
    upper = img.crop((0, 0, img.width, split))
    lower = img.crop((0, split, img.width, img.height))
    out.paste(upper, (dx, 0), upper)
    out.paste(lower, (0, split), lower)
    return out


def step_frame(img: Image.Image, lift_left: bool) -> Image.Image:
    """Lift one leg half by 2 px and bob the body 1 px."""
    w, h = img.size
    top, bottom = opaque_rows(img)
    leg_y = top + int((bottom - top) * 0.78)
    mid = w // 2
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    body = img.crop((0, 0, w, leg_y))
    out.paste(body, (0, 1), body)  # bob down 1px
    lx0, lx1 = (0, mid) if lift_left else (mid, w)
    sx0, sx1 = (mid, w) if lift_left else (0, mid)
    lifted = img.crop((lx0, leg_y, lx1, h))
    planted = img.crop((sx0, leg_y, sx1, h))
    out.paste(lifted, (lx0, leg_y - 1), lifted)
    out.paste(planted, (sx0, leg_y + 1), planted)
    return out


def keep_largest_component(img: Image.Image) -> Image.Image:
    """Drop stray opaque fragments (e.g. leftover furniture edge columns)."""
    out = img.copy()
    px = out.load()
    w, h = out.size
    label = [[0] * h for _ in range(w)]
    sizes: dict[int, int] = {}
    next_label = 1
    for sx in range(w):
        for sy in range(h):
            if px[sx, sy][3] > 100 and label[sx][sy] == 0:
                stack = [(sx, sy)]
                label[sx][sy] = next_label
                count = 0
                while stack:
                    x, y = stack.pop()
                    count += 1
                    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if 0 <= nx < w and 0 <= ny < h and label[nx][ny] == 0 and px[nx, ny][3] > 100:
                            label[nx][ny] = next_label
                            stack.append((nx, ny))
                sizes[next_label] = count
                next_label += 1
    if not sizes:
        return out
    keep = max(sizes, key=lambda k: sizes[k])
    for x in range(w):
        for y in range(h):
            if px[x, y][3] > 100 and label[x][y] != keep:
                px[x, y] = (0, 0, 0, 0)
    return out


def build_sheet(name: str) -> None:
    base = Image.open(OFFICE / f"char_{name}.png").convert("RGBA")
    base = keep_largest_component(base)
    w, h = base.size

    if BASE_FACING[name] == "down":
        down = base
        up = front_to_back(base)
    else:
        up = base
        down = back_to_front(base)
    left = lean(down, -1)
    right = lean(down, 1)
    facings = {"down": down, "up": up, "left": left, "right": right}

    sheet = Image.new("RGBA", (w * 4, h * 4), (0, 0, 0, 0))
    for row, facing in enumerate(ROW_ORDER):
        f = facings[facing]
        frames = [f, step_frame(f, True), f, step_frame(f, False)]
        for col, frame in enumerate(frames):
            sheet.paste(frame, (col * w, row * h))
    sheet.save(OFFICE / f"sheet_{name}.png")
    print(f"sheet_{name}.png  cell {w}x{h}")


def main() -> None:
    for name in BASE_FACING:
        build_sheet(name)


if __name__ == "__main__":
    main()
