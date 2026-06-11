/**
 * Single-pass scene renderer. Called every animation frame.
 *
 * The office is the design-mockup background image drawn 1:1; only the
 * three standing protagonists (proposer / decider / trader) are drawn as
 * dynamic sprites on top. Every character — drawn or baked — can show an
 * action speech bubble anchored at its seat.
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
import { INK, WHITE } from '@/styles/palette'
import {
  FACING_ROW,
  MOVABLE_SPRITES,
  SHEET_COLS,
  WALK_FRAME_MS,
  spriteDrawPos,
} from './assets'

function gridToPx(p: GridPos): { x: number; y: number } {
  return { x: p.x * TILE_PX, y: p.y * TILE_PX }
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

function imageReady(img: CanvasImageSource | null | undefined): img is HTMLImageElement {
  return (
    !!img &&
    img instanceof HTMLImageElement &&
    img.complete &&
    img.naturalWidth > 0
  )
}

export interface SceneSnapshot {
  characters: ReadonlyArray<Character>
  sprites: ReadonlyMap<string, CanvasImageSource>
  bg: HTMLImageElement | null
}

export function drawScene(
  ctx: CanvasRenderingContext2D,
  snap: SceneSnapshot,
  now: number,
): void {
  ctx.imageSmoothingEnabled = false

  if (imageReady(snap.bg)) {
    ctx.drawImage(snap.bg, 0, 0)
  } else {
    ctx.fillStyle = INK
    ctx.fillRect(0, 0, CANVAS_LOGICAL_W, CANVAS_LOGICAL_H)
  }

  // Movable sprites, lower characters drawn later for correct overlap.
  const movable = snap.characters
    .filter((c) => MOVABLE_SPRITES[c.id])
    .sort((a, b) => a.pos.y - b.pos.y)
  const bubbles: Array<{ x: number; y: number; text: string }> = []
  for (const char of movable) {
    const meta = MOVABLE_SPRITES[char.id]!
    const img = snap.sprites.get(char.id)
    const dest = lerpPos(char, now)
    const draw = spriteDrawPos(meta, dest.x, dest.y)
    const row = FACING_ROW[char.facing]
    const col =
      char.state.kind === 'walking'
        ? Math.floor(now / WALK_FRAME_MS) % SHEET_COLS
        : 0
    if (imageReady(img)) {
      ctx.drawImage(
        img,
        col * meta.w,
        row * meta.h,
        meta.w,
        meta.h,
        draw.x,
        draw.y,
        meta.w,
        meta.h,
      )
    }
    if (char.state.kind === 'acting' && char.state.bubble) {
      bubbles.push({ x: draw.x + meta.w / 2, y: draw.y, text: char.state.bubble })
    }
  }

  // Baked / bubble-only characters still speak.
  for (const char of snap.characters) {
    if (MOVABLE_SPRITES[char.id]) continue
    if (char.state.kind === 'acting' && char.state.bubble) {
      const p = gridToPx(char.pos)
      bubbles.push({ x: p.x + TILE_PX / 2, y: p.y, text: char.state.bubble })
    }
  }

  for (const b of bubbles) {
    drawBubble(ctx, b.x, b.y, b.text)
  }
}

function drawBubble(
  ctx: CanvasRenderingContext2D,
  cx: number,
  topY: number,
  text: string,
): void {
  const padding = 3
  ctx.font = '10px ui-monospace, monospace'
  const w = Math.ceil(ctx.measureText(text).width) + padding * 2
  const h = 16
  const bx = Math.min(CANVAS_LOGICAL_W - w - 1, Math.max(1, cx - w / 2))
  const by = Math.max(1, topY - h - 2)
  ctx.fillStyle = WHITE
  ctx.fillRect(bx, by, w, h)
  ctx.strokeStyle = INK
  ctx.lineWidth = 1
  ctx.strokeRect(bx + 0.5, by + 0.5, w - 1, h - 1)
  ctx.fillStyle = INK
  ctx.textBaseline = 'top'
  ctx.fillText(text, bx + padding, by + padding)
}
