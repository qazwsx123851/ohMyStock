/**
 * Single-pass scene renderer. Called every animation frame.
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirements: Office Scene Layout, Integer-Scale Pixel Rendering,
 *        Frozen Gen 2 Palette)
 */

import {
  CANVAS_LOGICAL_H,
  CANVAS_LOGICAL_W,
  TILE_PX,
  type Character,
  type GridPos,
  type Region,
} from '@/types/public-event'
import {
  GB_FLOOR_DARK,
  GB_FLOOR_LIGHT,
  GB_WALL,
} from '@/styles/palette'
import { drawBookshelf, drawCounter, drawScreen, drawTable } from './tiles'

export const REGIONS: readonly Region[] = [
  { label: '行情大廳', x: 0, y: 0, w: 12, h: 4 },
  { label: 'K 線分析室', x: 12, y: 0, w: 12, h: 4 },
  { label: '決策桌', x: 0, y: 4, w: 12, h: 8 },
  { label: '圖書館', x: 12, y: 4, w: 12, h: 8 },
  { label: '實驗室', x: 0, y: 12, w: 12, h: 4 },
  { label: '會議室', x: 12, y: 12, w: 12, h: 4 },
]

function gridToPx(p: GridPos): { x: number; y: number } {
  return { x: p.x * TILE_PX, y: p.y * TILE_PX }
}

function drawFloor(ctx: CanvasRenderingContext2D): void {
  for (let y = 0; y < CANVAS_LOGICAL_H; y++) {
    ctx.fillStyle = y % 2 === 0 ? GB_FLOOR_LIGHT : GB_FLOOR_DARK
    ctx.fillRect(0, y, CANVAS_LOGICAL_W, 1)
  }
}

function drawRegionFrames(ctx: CanvasRenderingContext2D): void {
  ctx.strokeStyle = GB_WALL
  ctx.lineWidth = 1
  ctx.font = '6px ui-monospace, monospace'
  ctx.fillStyle = GB_WALL
  ctx.textBaseline = 'top'
  for (const r of REGIONS) {
    const px = r.x * TILE_PX
    const py = r.y * TILE_PX
    const pw = r.w * TILE_PX
    const ph = r.h * TILE_PX
    ctx.strokeRect(px + 0.5, py + 0.5, pw - 1, ph - 1)
    ctx.fillText(r.label, px + 2, py + 1)
  }
}

function drawStaticFurniture(ctx: CanvasRenderingContext2D): void {
  drawScreen(ctx, 1 * TILE_PX, 1 * TILE_PX, 3 * TILE_PX, 2 * TILE_PX)
  drawScreen(ctx, 16 * TILE_PX, 1 * TILE_PX, 3 * TILE_PX, 2 * TILE_PX)
  drawCounter(ctx, 3 * TILE_PX, 6 * TILE_PX, 7 * TILE_PX, 2 * TILE_PX)
  drawBookshelf(ctx, 20 * TILE_PX, 5 * TILE_PX, 3 * TILE_PX, 6 * TILE_PX)
  drawBookshelf(ctx, 14 * TILE_PX, 5 * TILE_PX, 3 * TILE_PX, 6 * TILE_PX)
  drawTable(ctx, 3 * TILE_PX, 13 * TILE_PX, 5 * TILE_PX, 2 * TILE_PX)
  drawTable(ctx, 15 * TILE_PX, 13 * TILE_PX, 7 * TILE_PX, 2 * TILE_PX)
}

function frameIndex(char: Character, now: number): number {
  if (char.state.kind === 'walking') {
    return Math.floor((now - char.state.lastStepAt) / 150) % 4
  }
  if (char.state.kind === 'acting') {
    return 3
  }
  return Math.floor(now / 400) % 2
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

  drawFloor(ctx)
  drawStaticFurniture(ctx)
  drawRegionFrames(ctx)

  for (const char of snap.characters) {
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
      drawBubble(ctx, dest.x, dest.y, char.state.bubble)
    }
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
  ctx.fillStyle = GB_FLOOR_LIGHT
  ctx.fillRect(bx, by, w, h)
  ctx.strokeStyle = GB_WALL
  ctx.lineWidth = 1
  ctx.strokeRect(bx + 0.5, by + 0.5, w - 1, h - 1)
  ctx.fillStyle = GB_WALL
  ctx.textBaseline = 'top'
  ctx.fillText(text, bx + padding, by + padding)
}
