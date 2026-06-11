/**
 * Single-pass scene renderer. Called every animation frame.
 *
 * Layout mirrors the reference design mockup: cream wall with furniture
 * along the top, sage checkered floor, workstations mid-left, L-shaped
 * reception counter right, review desks bottom-right, library table
 * bottom-left. Obstacle footprints live in characters/obstacles.ts and
 * MUST stay in sync with the geometry drawn here.
 *
 * Spec: openspec/specs/web-public-pixel-office/spec.md
 *       (Requirements: Office Scene Layout, Integer-Scale Pixel Rendering)
 */

import {
  CANVAS_LOGICAL_H,
  CANVAS_LOGICAL_W,
  TILE_PX,
  type Character,
  type GridPos,
} from '@/types/public-event'
import {
  BLUE,
  FLOOR_A,
  FLOOR_A_DITHER,
  FLOOR_B,
  FLOOR_B_DITHER,
  INK,
  RED,
  WALL_CREAM,
  WALL_CREAM_SHADOW,
  WALL_TRIM,
  WALL_TRIM_DARK,
  WHITE,
} from '@/styles/palette'
import {
  drawBookshelf,
  drawCabinet,
  drawChairBack,
  drawChairSeat,
  drawCounterH,
  drawCounterPlant,
  drawCounterV,
  drawDrawerUnit,
  drawLibraryTable,
  drawLocker,
  drawPapers,
  drawPlant,
  drawPrinter,
  drawRetroPC,
  drawSideTable,
  drawStool,
  drawTrashBin,
  drawVending,
  drawWallClock,
  drawWallFrames,
  drawWaterCooler,
  drawWhiteboard,
  drawWindow,
  drawWorkDesk,
} from './tiles'

const WALL_ROWS = 3

/** Desk chairs (seat under the character, backrest over it). */
const CHAIRS: ReadonlyArray<{ pos: GridPos; colour: string }> = [
  { pos: { x: 2, y: 7 }, colour: RED },
  { pos: { x: 5, y: 7 }, colour: BLUE },
  { pos: { x: 13, y: 13 }, colour: BLUE },
  { pos: { x: 16, y: 13 }, colour: BLUE },
]

function gridToPx(p: GridPos): { x: number; y: number } {
  return { x: p.x * TILE_PX, y: p.y * TILE_PX }
}

function drawWallAndFloor(ctx: CanvasRenderingContext2D): void {
  const wallH = WALL_ROWS * TILE_PX
  // Cream wall + wood baseboard
  ctx.fillStyle = WALL_CREAM
  ctx.fillRect(0, 0, CANVAS_LOGICAL_W, wallH)
  ctx.fillStyle = WALL_CREAM_SHADOW
  ctx.fillRect(0, wallH - 17, CANVAS_LOGICAL_W, 4)
  ctx.fillStyle = WALL_TRIM
  ctx.fillRect(0, wallH - 13, CANVAS_LOGICAL_W, 11)
  ctx.fillStyle = WALL_TRIM_DARK
  ctx.fillRect(0, wallH - 3, CANVAS_LOGICAL_W, 2)
  ctx.fillStyle = INK
  ctx.fillRect(0, wallH - 1, CANVAS_LOGICAL_W, 1)

  // Sage checkered floor with diagonal dither texture
  for (let gy = WALL_ROWS; gy < CANVAS_LOGICAL_H / TILE_PX; gy++) {
    for (let gx = 0; gx < CANVAS_LOGICAL_W / TILE_PX; gx++) {
      const light = (gx + gy) % 2 === 0
      const tx = gx * TILE_PX
      const ty = gy * TILE_PX
      ctx.fillStyle = light ? FLOOR_A : FLOOR_B
      ctx.fillRect(tx, ty, TILE_PX, TILE_PX)
      ctx.fillStyle = light ? FLOOR_A_DITHER : FLOOR_B_DITHER
      for (let i = 0; i < 4; i++) {
        ctx.fillRect(tx + i * 4 + (light ? 0 : 2), ty + i * 4, 2, 2)
      }
    }
  }
}

function drawStaticFurniture(ctx: CanvasRenderingContext2D): void {
  const T = TILE_PX
  // --- Top wall, left to right ---
  drawPlant(ctx, 1 * T, 18)
  drawBookshelf(ctx, 2 * T, 6)
  drawSideTable(ctx, 5 * T, 30)
  drawWhiteboard(ctx, 7 * T, 6)
  drawWallClock(ctx, 172, 8)
  drawWallClock(ctx, 188, 8)
  drawWallFrames(ctx, 204, 8)
  drawCabinet(ctx, 224, 7)
  drawLocker(ctx, 256, 7)
  drawRetroPC(ctx, 274, 7)
  drawWindow(ctx, 308, 8)
  drawPlant(ctx, 344, 18)
  // --- Left wall ---
  drawVending(ctx, 0, 50)
  // --- Mid-left workstations ---
  drawWorkDesk(ctx, 2 * T, 6 * T)
  drawWorkDesk(ctx, 5 * T, 6 * T)
  // --- Reception counter (L-shape) ---
  drawCounterH(ctx, 13 * T, 8 * T, 9 * T)
  drawCounterV(ctx, 21 * T, 9 * T, 3 * T)
  drawCounterPlant(ctx, 14 * T + 2, 8 * T + 2)
  drawPapers(ctx, 19 * T, 8 * T + 3)
  // --- Right wall ---
  drawPrinter(ctx, 22 * T, 68)
  drawDrawerUnit(ctx, 22 * T + 2, 100)
  drawWaterCooler(ctx, 21 * T, 194)
  drawTrashBin(ctx, 22 * T + 1, 226)
  // --- Review desks bottom-right ---
  drawWorkDesk(ctx, 13 * T, 12 * T)
  drawWorkDesk(ctx, 16 * T, 12 * T)
  // --- Library corner bottom-left ---
  drawLibraryTable(ctx, 3 * T, 11 * T)
  drawStool(ctx, 5 * T, 13 * T)
  drawPlant(ctx, 1 * T, 194)
}

function frameIndex(char: Character, now: number): number {
  if (char.state.kind === 'walking') {
    const seq = [0, 1, 0, 2] as const
    return seq[Math.floor((now - char.state.lastStepAt) / 150) % 4]!
  }
  if (char.state.kind === 'acting') {
    return 3
  }
  return 0
}

function facingRow(char: Character): number {
  switch (char.facing) {
    case 'down':
      return 0
    case 'up':
      return 1
    case 'left':
      return 2
    case 'right':
      return 3
  }
}

function lerpPos(char: Character, now: number): { x: number; y: number } {
  const cur = gridToPx(char.pos)
  if (char.state.kind !== 'walking') {
    return cur
  }
  const next = char.state.path[char.state.pathIdx]
  if (!next) return cur
  const elapsed = now - char.state.lastStepAt
  const tickMs = 200
  const t = Math.min(1, elapsed / tickMs)
  const np = gridToPx(next)
  return {
    x: cur.x + (np.x - cur.x) * t,
    y: cur.y + (np.y - cur.y) * t,
  }
}

export interface SceneSnapshot {
  characters: ReadonlyArray<Character>
  sprites: ReadonlyMap<string, CanvasImageSource>
}

export function drawScene(
  ctx: CanvasRenderingContext2D,
  snap: SceneSnapshot,
  now: number,
): void {
  ctx.imageSmoothingEnabled = false

  drawWallAndFloor(ctx)
  drawStaticFurniture(ctx)
  for (const chair of CHAIRS) {
    const p = gridToPx(chair.pos)
    drawChairSeat(ctx, p.x, p.y, chair.colour)
  }

  // Painter's order: lower characters drawn later so they overlap upper ones.
  const sorted = [...snap.characters].sort((a, b) => a.pos.y - b.pos.y)
  const bubbles: Array<{ x: number; y: number; text: string }> = []
  for (const char of sorted) {
    const sheet = snap.sprites.get(char.id)
    if (!sheet) continue
    const row = facingRow(char)
    const col = frameIndex(char, now)
    const dest = lerpPos(char, now)
    ctx.drawImage(
      sheet,
      col * TILE_PX,
      row * TILE_PX,
      TILE_PX,
      TILE_PX,
      Math.round(dest.x),
      Math.round(dest.y),
      TILE_PX,
      TILE_PX,
    )
    if (char.state.kind === 'acting' && char.state.bubble) {
      bubbles.push({ x: dest.x, y: dest.y, text: char.state.bubble })
    }
  }

  // Chair backrests occlude seated characters' legs (they face the desk).
  for (const chair of CHAIRS) {
    const p = gridToPx(chair.pos)
    drawChairBack(ctx, p.x, p.y, chair.colour)
  }

  for (const b of bubbles) {
    drawBubble(ctx, b.x, b.y, b.text)
  }
}

function drawBubble(
  ctx: CanvasRenderingContext2D,
  px: number,
  py: number,
  text: string,
): void {
  const padding = 2
  ctx.font = '6px ui-monospace, monospace'
  const w = Math.ceil(ctx.measureText(text).width) + padding * 2
  const h = 9
  const bx = Math.min(CANVAS_LOGICAL_W - w - 1, Math.max(1, px - w / 2 + TILE_PX / 2))
  const by = Math.max(1, py - h - 1)
  ctx.fillStyle = WHITE
  ctx.fillRect(bx, by, w, h)
  ctx.strokeStyle = INK
  ctx.lineWidth = 1
  ctx.strokeRect(bx + 0.5, by + 0.5, w - 1, h - 1)
  ctx.fillStyle = INK
  ctx.textBaseline = 'top'
  ctx.fillText(text, bx + padding, by + padding)
}
