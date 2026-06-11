/**
 * Static furniture pixel-art painters — Pokémon Gen 4 interior style,
 * matched to the reference design mockup. All coordinates are logical
 * canvas pixels (16-px grid, painters may overflow upward onto the wall).
 *
 * Spec: openspec/specs/web-public-pixel-office/spec.md
 *       (Requirement: Office Scene Layout)
 */

import {
  BLUE,
  BLUE_DARK,
  FLOOR_SHADOW,
  GRAY,
  GRAY_DARK,
  GRAY_LIGHT,
  GREEN_DARK,
  GREEN_LEAF,
  GREEN_LIGHT,
  INK,
  ORANGE,
  POT_CLAY,
  POT_CLAY_DARK,
  RED,
  RED_DARK,
  SCREEN_BEZEL,
  SCREEN_BLUE,
  SCREEN_BLUE_DARK,
  SCREEN_GLOW,
  TEAL,
  WATER_BLUE,
  WHITE,
  WOOD,
  WOOD_DARK,
  WOOD_DEEP,
  WOOD_LIGHT,
  YELLOW,
} from '@/styles/palette'

function px(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  c: string,
): void {
  ctx.fillStyle = c
  ctx.fillRect(x, y, w, h)
}

/** Tall potted plant, 16 wide × 30 tall (anchor = top-left). */
export function drawPlant(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  // Foliage (layered blobs)
  px(ctx, x + 5, y, 6, 3, GREEN_DARK)
  px(ctx, x + 2, y + 2, 12, 5, GREEN_LEAF)
  px(ctx, x + 1, y + 5, 14, 6, GREEN_LEAF)
  px(ctx, x + 3, y + 3, 4, 2, GREEN_LIGHT)
  px(ctx, x + 2, y + 9, 12, 3, GREEN_DARK)
  px(ctx, x + 4, y + 6, 3, 2, GREEN_DARK)
  px(ctx, x + 9, y + 4, 3, 2, GREEN_DARK)
  px(ctx, x + 7, y + 11, 2, 3, GREEN_DARK)
  // Pot
  px(ctx, x + 2, y + 14, 12, 3, POT_CLAY)
  px(ctx, x + 4, y + 17, 8, 9, POT_CLAY)
  px(ctx, x + 4, y + 23, 8, 3, POT_CLAY_DARK)
  px(ctx, x + 2, y + 13, 12, 1, INK)
  px(ctx, x + 4, y + 26, 8, 2, INK)
  // Shadow
  px(ctx, x + 2, y + 28, 12, 2, FLOOR_SHADOW)
}

/** Bookshelf with coloured spines, 48 × 42. */
export function drawBookshelf(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w = 48,
  h = 42,
): void {
  px(ctx, x, y, w, h, WOOD_DARK)
  px(ctx, x, y, w, 1, INK)
  px(ctx, x, y + 1, w, 3, WOOD_LIGHT)
  px(ctx, x, y + h - 3, w, 3, WOOD_DEEP)
  px(ctx, x, y + h - 1, w, 1, INK)
  px(ctx, x, y, 1, h, INK)
  px(ctx, x + w - 1, y, 1, h, INK)
  const spineColours = [RED, BLUE, GREEN_LEAF, YELLOW, TEAL, RED_DARK, BLUE_DARK]
  for (let row = 0; row < 2; row++) {
    const sy = y + 5 + row * 17
    px(ctx, x + 2, sy, w - 4, 14, WOOD_DEEP)
    let i = row * 3
    for (let bx = x + 3; bx + 3 < x + w - 2; bx += 4) {
      const tall = i % 3 === 0 ? 0 : 2
      px(ctx, bx, sy + 1 + tall, 3, 12 - tall, spineColours[i % spineColours.length]!)
      i++
    }
    px(ctx, x + 2, sy + 14, w - 4, 2, WOOD)
  }
}

/** Small wooden side table with a radio + book stack, 32 × 24. */
export function drawSideTable(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  // Items on top (drawn above table surface)
  px(ctx, x + 3, y - 8, 10, 8, WOOD_DEEP) // radio
  px(ctx, x + 4, y - 6, 3, 3, YELLOW)
  px(ctx, x + 9, y - 6, 3, 3, GRAY_LIGHT)
  px(ctx, x + 3, y - 9, 10, 1, INK)
  px(ctx, x + 18, y - 5, 10, 2, RED_DARK) // book stack
  px(ctx, x + 18, y - 3, 10, 2, BLUE_DARK)
  px(ctx, x + 18, y - 1, 10, 1, INK)
  // Table
  px(ctx, x, y, 32, 4, WOOD_LIGHT)
  px(ctx, x, y, 32, 1, INK)
  px(ctx, x + 1, y + 4, 30, 12, WOOD)
  px(ctx, x + 1, y + 13, 30, 3, WOOD_DARK)
  px(ctx, x + 1, y + 16, 30, 1, INK)
  px(ctx, x, y, 1, 17, INK)
  px(ctx, x + 31, y, 1, 17, INK)
}

/** Wall-mounted whiteboard with rising red chart, 52 × 28. */
export function drawWhiteboard(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  const w = 52
  const h = 28
  px(ctx, x, y, w, h, GRAY)
  px(ctx, x + 2, y + 2, w - 4, h - 7, WHITE)
  px(ctx, x, y, w, 1, INK)
  px(ctx, x, y + h - 1, w, 1, INK)
  px(ctx, x, y, 1, h, INK)
  px(ctx, x + w - 1, y, 1, h, INK)
  // marker tray
  px(ctx, x + 4, y + h - 4, w - 8, 2, GRAY_LIGHT)
  // axis
  px(ctx, x + 5, y + 5, 1, 16, GRAY)
  px(ctx, x + 5, y + 20, 40, 1, GRAY)
  // rising red polyline
  const pts: ReadonlyArray<readonly [number, number]> = [
    [6, 18], [11, 15], [16, 17], [22, 12], [28, 13], [34, 8], [40, 9], [44, 5],
  ]
  for (let i = 0; i < pts.length - 1; i++) {
    const [x1, y1] = pts[i]!
    const [x2, y2] = pts[i + 1]!
    const steps = Math.max(Math.abs(x2 - x1), Math.abs(y2 - y1))
    for (let s = 0; s <= steps; s++) {
      const ix = Math.round(x1 + ((x2 - x1) * s) / steps)
      const iy = Math.round(y1 + ((y2 - y1) * s) / steps)
      px(ctx, x + ix, y + iy, 2, 2, RED)
    }
  }
}

/** Round wall clock, 12 × 12. */
export function drawWallClock(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  px(ctx, x + 2, y, 8, 12, WHITE)
  px(ctx, x, y + 2, 12, 8, WHITE)
  px(ctx, x + 1, y + 1, 10, 10, WHITE)
  // outline (octagon-ish)
  px(ctx, x + 2, y, 8, 1, INK)
  px(ctx, x + 2, y + 11, 8, 1, INK)
  px(ctx, x, y + 2, 1, 8, INK)
  px(ctx, x + 11, y + 2, 1, 8, INK)
  px(ctx, x + 1, y + 1, 1, 1, INK)
  px(ctx, x + 10, y + 1, 1, 1, INK)
  px(ctx, x + 1, y + 10, 1, 1, INK)
  px(ctx, x + 10, y + 10, 1, 1, INK)
  // hands
  px(ctx, x + 5, y + 3, 1, 3, INK)
  px(ctx, x + 6, y + 5, 3, 1, INK)
}

/** Two small picture frames, 20 × 12. */
export function drawWallFrames(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  px(ctx, x, y, 9, 11, WOOD_DARK)
  px(ctx, x + 1, y + 1, 7, 9, SCREEN_BLUE)
  px(ctx, x + 2, y + 5, 5, 4, GREEN_LEAF)
  px(ctx, x + 12, y + 2, 8, 8, WOOD_DARK)
  px(ctx, x + 13, y + 3, 6, 6, WHITE)
  px(ctx, x + 14, y + 5, 4, 3, POT_CLAY)
}

/** Chest of drawers, 30 × 40. */
export function drawCabinet(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  const w = 30
  const h = 40
  px(ctx, x, y, w, h, WOOD)
  px(ctx, x, y, w, 1, INK)
  px(ctx, x, y + 1, w, 3, WOOD_LIGHT)
  for (let row = 0; row < 3; row++) {
    const dy = y + 6 + row * 11
    px(ctx, x + 2, dy, w - 4, 9, WOOD_DARK)
    px(ctx, x + 2, dy, w - 4, 1, WOOD_DEEP)
    px(ctx, x + Math.floor(w / 2) - 3, dy + 3, 6, 2, INK)
  }
  px(ctx, x, y + h - 1, w, 1, INK)
  px(ctx, x, y, 1, h, INK)
  px(ctx, x + w - 1, y, 1, h, INK)
}

/** Narrow two-door locker cabinet, 16 × 40. */
export function drawLocker(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  const w = 16
  const h = 40
  px(ctx, x, y, w, h, WOOD)
  px(ctx, x, y + 1, w, 3, WOOD_LIGHT)
  px(ctx, x + 2, y + 6, w - 4, h - 10, WOOD_DARK)
  px(ctx, x + Math.floor(w / 2), y + 6, 1, h - 10, WOOD_DEEP)
  px(ctx, x + 4, y + 18, 2, 4, INK)
  px(ctx, x + 10, y + 18, 2, 4, INK)
  px(ctx, x, y, w, 1, INK)
  px(ctx, x, y + h - 1, w, 1, INK)
  px(ctx, x, y, 1, h, INK)
  px(ctx, x + w - 1, y, 1, h, INK)
}

/** Retro terminal / server machine, 30 × 40. */
export function drawRetroPC(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  const w = 30
  const h = 40
  px(ctx, x, y, w, h, GRAY_LIGHT)
  px(ctx, x + w - 4, y, 4, h, GRAY)
  px(ctx, x + 3, y + 4, w - 9, 14, SCREEN_BEZEL)
  px(ctx, x + 5, y + 6, w - 13, 10, SCREEN_BLUE_DARK)
  px(ctx, x + 6, y + 8, 6, 1, SCREEN_GLOW)
  px(ctx, x + 6, y + 11, 10, 1, SCREEN_BLUE)
  px(ctx, x + 6, y + 13, 4, 1, SCREEN_GLOW)
  for (let i = 0; i < 3; i++) {
    px(ctx, x + 4, y + 22 + i * 4, w - 11, 2, GRAY)
  }
  px(ctx, x + 4, y + 34, 8, 2, GREEN_LEAF)
  px(ctx, x, y, w, 1, INK)
  px(ctx, x, y + h - 1, w, 1, INK)
  px(ctx, x, y, 1, h, INK)
  px(ctx, x + w - 1, y, 1, h, INK)
}

/** Bright window, 32 × 26. */
export function drawWindow(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  const w = 32
  const h = 26
  px(ctx, x, y, w, h, GRAY_LIGHT)
  px(ctx, x + 2, y + 2, w - 4, h - 4, WATER_BLUE)
  // shine
  px(ctx, x + 4, y + 4, 4, 8, SCREEN_GLOW)
  px(ctx, x + 8, y + 4, 2, 4, SCREEN_GLOW)
  px(ctx, x + 22, y + 12, 4, 8, SCREEN_GLOW)
  // cross divider
  px(ctx, x + Math.floor(w / 2) - 1, y + 2, 2, h - 4, GRAY_LIGHT)
  px(ctx, x + 2, y + Math.floor(h / 2) - 1, w - 4, 2, GRAY_LIGHT)
  px(ctx, x, y, w, 1, INK)
  px(ctx, x, y + h - 1, w, 1, INK)
  px(ctx, x, y, 1, h, INK)
  px(ctx, x + w - 1, y, 1, h, INK)
}

/** White fridge-like vending cabinet, 16 × 30. */
export function drawVending(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  const w = 16
  const h = 30
  px(ctx, x, y, w, h, WHITE)
  px(ctx, x + 1, y + 10, w - 2, 1, GRAY)
  px(ctx, x + w - 4, y + 3, 2, 5, GRAY)
  px(ctx, x + w - 4, y + 13, 2, 7, GRAY)
  px(ctx, x + 1, y + h - 4, w - 2, 3, GRAY_LIGHT)
  px(ctx, x, y, w, 1, INK)
  px(ctx, x, y + h - 1, w, 1, INK)
  px(ctx, x, y, 1, h, INK)
  px(ctx, x + w - 1, y, 1, h, INK)
}

/**
 * Workstation desk with two monitors + keyboard, 32 wide.
 * `y` is the top of the desk tile; monitors overflow 13 px above.
 */
export function drawWorkDesk(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  // Desk
  px(ctx, x, y - 2, 32, 8, GRAY_LIGHT)
  px(ctx, x, y - 2, 32, 1, INK)
  px(ctx, x, y + 6, 32, 8, GRAY)
  px(ctx, x, y + 13, 32, 1, INK)
  px(ctx, x, y - 2, 1, 16, INK)
  px(ctx, x + 31, y - 2, 1, 16, INK)
  // Monitors
  for (let m = 0; m < 2; m++) {
    const mx = x + 2 + m * 15
    px(ctx, mx, y - 13, 13, 11, SCREEN_BEZEL)
    px(ctx, mx + 1, y - 12, 11, 8, SCREEN_BLUE)
    // tiny candlestick chart
    px(ctx, mx + 2, y - 9, 1, 3, SCREEN_BLUE_DARK)
    px(ctx, mx + 4, y - 10, 1, 4, RED)
    px(ctx, mx + 6, y - 8, 1, 3, SCREEN_BLUE_DARK)
    px(ctx, mx + 8, y - 11, 1, 5, RED)
    px(ctx, mx + 10, y - 9, 1, 3, SCREEN_BLUE_DARK)
    px(ctx, mx + 5, y - 2, 3, 1, INK) // stand
  }
  // Keyboard
  px(ctx, x + 10, y + 1, 12, 3, WHITE)
  px(ctx, x + 10, y + 1, 12, 1, GRAY)
}

/** Office chair seat (drawn under the character). */
export function drawChairSeat(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  colour: string,
): void {
  px(ctx, x + 3, y + 4, 10, 9, colour)
  px(ctx, x + 3, y + 4, 10, 1, INK)
  px(ctx, x + 3, y + 12, 10, 1, INK)
  px(ctx, x + 3, y + 4, 1, 9, INK)
  px(ctx, x + 12, y + 4, 1, 9, INK)
  px(ctx, x + 6, y + 13, 4, 2, GRAY_DARK)
}

/** Office chair backrest (drawn over the character, faces the desk). */
export function drawChairBack(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  colour: string,
): void {
  px(ctx, x + 3, y + 12, 10, 3, colour)
  px(ctx, x + 3, y + 11, 10, 1, INK)
  px(ctx, x + 3, y + 15, 10, 1, INK)
  px(ctx, x + 3, y + 12, 1, 3, INK)
  px(ctx, x + 12, y + 12, 1, 3, INK)
}

/** Horizontal reception counter segment (overflows 6 px into the row below). */
export function drawCounterH(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
): void {
  px(ctx, x, y, w, 8, WOOD_LIGHT)
  px(ctx, x, y, w, 1, INK)
  px(ctx, x + 2, y + 3, w - 4, 1, WOOD)
  px(ctx, x, y + 8, w, 11, WOOD)
  for (let gx = x + 10; gx < x + w - 6; gx += 16) {
    px(ctx, gx, y + 10, 1, 7, WOOD_DARK)
  }
  px(ctx, x, y + 8, w, 1, WOOD_DARK)
  px(ctx, x, y + 19, w, 2, WOOD_DEEP)
  px(ctx, x, y + 21, w, 1, INK)
  px(ctx, x, y, 1, 22, INK)
  px(ctx, x + w - 1, y, 1, 22, INK)
}

/** Vertical reception counter arm, 16 wide (top surface + right side shading). */
export function drawCounterV(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  h: number,
): void {
  px(ctx, x, y, 16, h, WOOD_LIGHT)
  px(ctx, x + 12, y, 4, h, WOOD)
  px(ctx, x + 2, y + 4, 1, h - 8, WOOD)
  px(ctx, x, y + h - 8, 16, 6, WOOD)
  px(ctx, x, y + h - 2, 16, 1, WOOD_DEEP)
  px(ctx, x, y + h - 1, 16, 1, INK)
  px(ctx, x, y, 1, h, INK)
  px(ctx, x + 15, y, 1, h, INK)
}

/** Small potted plant sitting on the counter, 12 × 12. */
export function drawCounterPlant(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  px(ctx, x + 2, y, 8, 5, GREEN_LEAF)
  px(ctx, x + 1, y + 2, 10, 3, GREEN_LEAF)
  px(ctx, x + 3, y + 1, 2, 2, GREEN_DARK)
  px(ctx, x + 7, y + 3, 2, 2, GREEN_DARK)
  px(ctx, x + 3, y + 5, 6, 4, POT_CLAY)
  px(ctx, x + 3, y + 8, 6, 1, INK)
}

/** Loose papers on a surface, 12 × 8. */
export function drawPapers(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  px(ctx, x + 2, y + 1, 9, 6, WHITE)
  px(ctx, x, y, 9, 6, WHITE)
  px(ctx, x, y, 9, 1, GRAY)
  px(ctx, x + 1, y + 2, 6, 1, GRAY_LIGHT)
  px(ctx, x + 1, y + 4, 6, 1, GRAY_LIGHT)
}

/** Printer / copier on the right wall, 28 × 24. */
export function drawPrinter(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  const w = 28
  px(ctx, x, y + 4, w, 16, WHITE)
  px(ctx, x + 2, y, w - 4, 5, GRAY_LIGHT)
  px(ctx, x + 2, y, w - 4, 1, INK)
  px(ctx, x + 4, y + 7, 8, 3, SCREEN_BLUE)
  px(ctx, x + 4, y + 12, w - 8, 2, GRAY_DARK)
  px(ctx, x + 2, y + 20, w - 4, 3, GRAY_LIGHT)
  px(ctx, x, y + 4, w, 1, INK)
  px(ctx, x, y + 19, w, 1, INK)
  px(ctx, x + 2, y + 23, w - 4, 1, INK)
  px(ctx, x, y + 4, 1, 16, INK)
  px(ctx, x + w - 1, y + 4, 1, 16, INK)
}

/** Two-by-two drawer unit, 28 × 26. */
export function drawDrawerUnit(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  const w = 28
  const h = 26
  px(ctx, x, y, w, h, WOOD)
  px(ctx, x, y + 1, w, 2, WOOD_LIGHT)
  for (let r = 0; r < 2; r++) {
    for (let c = 0; c < 2; c++) {
      const dx = x + 2 + c * 13
      const dy = y + 4 + r * 10
      px(ctx, dx, dy, 11, 8, WOOD_DARK)
      px(ctx, dx + 3, dy + 3, 5, 2, INK)
    }
  }
  px(ctx, x, y, w, 1, INK)
  px(ctx, x, y + h - 1, w, 1, INK)
  px(ctx, x, y, 1, h, INK)
  px(ctx, x + w - 1, y, 1, h, INK)
}

/** Water cooler, 16 × 28. */
export function drawWaterCooler(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  // bottle (prominent, like the design mockup)
  px(ctx, x + 3, y + 1, 10, 10, WATER_BLUE)
  px(ctx, x + 2, y + 3, 12, 7, WATER_BLUE)
  px(ctx, x + 4, y + 2, 3, 6, SCREEN_GLOW)
  px(ctx, x + 3, y, 10, 1, INK)
  px(ctx, x + 2, y + 2, 1, 8, INK)
  px(ctx, x + 13, y + 2, 1, 8, INK)
  // body
  px(ctx, x + 2, y + 11, 12, 11, GRAY_LIGHT)
  px(ctx, x + 4, y + 13, 3, 3, RED)
  px(ctx, x + 9, y + 13, 3, 3, BLUE)
  px(ctx, x + 2, y + 22, 12, 4, GRAY_DARK)
  px(ctx, x + 2, y + 11, 12, 1, INK)
  px(ctx, x + 2, y + 26, 12, 1, INK)
  px(ctx, x + 2, y + 11, 1, 16, INK)
  px(ctx, x + 13, y + 11, 1, 16, INK)
}

/** Round orange waste bin, 14 × 14. */
export function drawTrashBin(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  px(ctx, x + 2, y, 10, 3, POT_CLAY_DARK)
  px(ctx, x + 1, y + 1, 12, 2, POT_CLAY_DARK)
  px(ctx, x + 2, y + 3, 10, 9, ORANGE)
  px(ctx, x + 3, y + 4, 2, 7, YELLOW)
  px(ctx, x + 2, y + 11, 10, 2, POT_CLAY_DARK)
  px(ctx, x + 2, y, 10, 1, INK)
  px(ctx, x + 2, y + 13, 10, 1, INK)
  px(ctx, x + 1, y + 1, 1, 12, INK)
  px(ctx, x + 12, y + 1, 1, 12, INK)
}

/** Library reading table with open book + jar, 48 × 30. */
export function drawLibraryTable(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  const w = 48
  px(ctx, x, y, w, 12, WOOD_LIGHT)
  px(ctx, x, y, w, 1, INK)
  px(ctx, x + 1, y + 12, w - 2, 14, WOOD)
  px(ctx, x + 1, y + 23, w - 2, 3, WOOD_DARK)
  px(ctx, x + 1, y + 26, w - 2, 1, INK)
  px(ctx, x, y, 1, 27, INK)
  px(ctx, x + w - 1, y, 1, 27, INK)
  // open book
  px(ctx, x + 22, y + 2, 16, 9, WHITE)
  px(ctx, x + 29, y + 2, 1, 9, GRAY)
  px(ctx, x + 24, y + 4, 4, 1, GRAY_LIGHT)
  px(ctx, x + 24, y + 6, 4, 1, GRAY_LIGHT)
  px(ctx, x + 32, y + 4, 4, 1, GRAY_LIGHT)
  px(ctx, x + 32, y + 6, 4, 1, GRAY_LIGHT)
  px(ctx, x + 22, y + 1, 16, 1, INK)
  px(ctx, x + 22, y + 11, 16, 1, INK)
  // ink jar + lamp
  px(ctx, x + 8, y + 3, 7, 7, WOOD_DEEP)
  px(ctx, x + 9, y + 2, 5, 2, YELLOW)
  px(ctx, x + 8, y + 9, 7, 1, INK)
}

/** Small wooden stool, 12 × 10 (anchor centred in a 16-px tile). */
export function drawStool(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  px(ctx, x + 3, y + 4, 10, 6, WOOD_LIGHT)
  px(ctx, x + 3, y + 4, 10, 1, INK)
  px(ctx, x + 3, y + 9, 10, 1, WOOD_DARK)
  px(ctx, x + 4, y + 10, 2, 4, WOOD_DEEP)
  px(ctx, x + 10, y + 10, 2, 4, WOOD_DEEP)
}
