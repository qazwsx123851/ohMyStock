/**
 * Runtime-generated Gen 2-style sprite placeholder.
 *
 * 64×64 sheet = 4 facings × 4 frames × 16×16. Each cell draws a chibi:
 *   - body trapezoid (GB_FURNITURE)
 *   - head circle (GB_FLOOR_LIGHT)
 *   - hat block (per-character hat colour)
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirement: Character Roster — placeholder palette compliance)
 */

import {
  GB_ACCENT,
  GB_FURNITURE,
  GB_FURNITURE_SHADOW,
  GB_FLOOR_LIGHT,
  GB_HIGHLIGHT,
  GB_WALL,
  type PaletteHex,
} from '@/styles/palette'
import type { CharacterId } from '@/types/public-event'

const HAT_POOL: readonly PaletteHex[] = [
  GB_ACCENT,
  GB_HIGHLIGHT,
  GB_FURNITURE_SHADOW,
]

function hashCharId(id: string): number {
  let h = 0
  for (let i = 0; i < id.length; i++) {
    h = (h * 31 + id.charCodeAt(i)) >>> 0
  }
  return h
}

export function hatColourFor(id: CharacterId): PaletteHex {
  return HAT_POOL[hashCharId(id) % HAT_POOL.length]!
}

function fillCell(
  ctx: CanvasRenderingContext2D,
  ox: number,
  oy: number,
  hat: PaletteHex,
  frame: number,
): void {
  // Body trapezoid (legs slightly offset on walk frames).
  const legShift = frame === 1 ? -1 : frame === 2 ? 1 : 0
  ctx.fillStyle = GB_FURNITURE
  ctx.fillRect(ox + 5, oy + 9, 6, 5)
  ctx.fillStyle = GB_FURNITURE_SHADOW
  ctx.fillRect(ox + 5 + legShift, oy + 14, 2, 2)
  ctx.fillRect(ox + 9 - legShift, oy + 14, 2, 2)

  // Head circle (3×3 inside 5×5 with corners knocked off).
  ctx.fillStyle = GB_FLOOR_LIGHT
  ctx.fillRect(ox + 5, oy + 3, 6, 6)
  ctx.fillStyle = GB_WALL
  ctx.fillRect(ox + 4, oy + 3, 1, 1)
  ctx.fillRect(ox + 11, oy + 3, 1, 1)
  ctx.fillRect(ox + 4, oy + 8, 1, 1)
  ctx.fillRect(ox + 11, oy + 8, 1, 1)

  // Hat strip.
  ctx.fillStyle = hat
  ctx.fillRect(ox + 4, oy + 2, 8, 2)

  // Eyes (2 dark pixels).
  ctx.fillStyle = GB_WALL
  ctx.fillRect(ox + 6, oy + 6, 1, 1)
  ctx.fillRect(ox + 9, oy + 6, 1, 1)
}

export function generatePlaceholderSheet(
  id: CharacterId,
  doc: Document = document,
): HTMLCanvasElement {
  const canvas = doc.createElement('canvas')
  canvas.width = 64
  canvas.height = 64
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    throw new Error('generatePlaceholderSheet: 2D context unavailable')
  }
  ctx.imageSmoothingEnabled = false
  const hat = hatColourFor(id)
  for (let row = 0; row < 4; row++) {
    for (let col = 0; col < 4; col++) {
      fillCell(ctx, col * 16, row * 16, hat, col)
    }
  }
  return canvas
}
