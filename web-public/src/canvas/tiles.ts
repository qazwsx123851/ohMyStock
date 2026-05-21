/**
 * Static furniture tile renderers — palette-constrained, 16-px grid aligned.
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirement: Frozen Gen 2 Palette)
 */

import {
  GB_ACCENT,
  GB_FLOOR_LIGHT,
  GB_FURNITURE,
  GB_FURNITURE_SHADOW,
  GB_HIGHLIGHT,
  GB_WALL,
} from '@/styles/palette'

export function drawCounter(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
): void {
  ctx.fillStyle = GB_FURNITURE
  ctx.fillRect(x, y, w, h)
  ctx.fillStyle = GB_FURNITURE_SHADOW
  ctx.fillRect(x, y + h - 2, w, 2)
  ctx.strokeStyle = GB_WALL
  ctx.lineWidth = 1
  ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1)
}

export function drawBookshelf(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
): void {
  ctx.fillStyle = GB_FURNITURE
  ctx.fillRect(x, y, w, h)
  ctx.fillStyle = GB_FURNITURE_SHADOW
  const shelfH = Math.floor(h / 2)
  for (let row = 0; row < 2; row++) {
    const sy = y + row * shelfH + 2
    for (let bx = x + 2; bx < x + w - 2; bx += 3) {
      ctx.fillRect(bx, sy, 2, shelfH - 4)
    }
  }
  ctx.strokeStyle = GB_WALL
  ctx.lineWidth = 1
  ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1)
}

export function drawTable(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
): void {
  ctx.fillStyle = GB_FURNITURE
  ctx.fillRect(x, y, w, h - 2)
  ctx.fillStyle = GB_FURNITURE_SHADOW
  ctx.fillRect(x, y + h - 2, w, 2)
  ctx.strokeStyle = GB_WALL
  ctx.lineWidth = 1
  ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1)
}

export function drawScreen(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
): void {
  ctx.fillStyle = GB_WALL
  ctx.fillRect(x, y, w, h)
  ctx.fillStyle = GB_HIGHLIGHT
  ctx.fillRect(x + 1, y + 1, w - 2, h - 4)
  ctx.fillStyle = GB_ACCENT
  ctx.fillRect(x + 2, y + 2, w - 4, 1)
}

export function drawPokeballSlot(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
): void {
  ctx.fillStyle = GB_ACCENT
  ctx.fillRect(x, y, 5, 3)
  ctx.fillStyle = GB_FLOOR_LIGHT
  ctx.fillRect(x, y + 3, 5, 2)
  ctx.fillStyle = GB_WALL
  ctx.fillRect(x + 2, y + 2, 1, 1)
}
