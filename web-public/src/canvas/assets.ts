/**
 * Office art assets — extracted from the UI design mockup by
 * scripts/extract_office_assets.py.
 *
 * The background (frame + room + four seated workers) is a single image
 * drawn 1:1. Only the three standing protagonists are dynamic sprites;
 * the remaining roster characters are bubble-only (no body drawn).
 *
 * Spec: openspec/specs/web-public-pixel-office/spec.md
 *       (Requirements: Office Scene Layout, Character Roster)
 */

import { TILE_PX, type Character, type CharacterId } from '@/types/public-event'

export const BG_URL = '/office/office-bg.png'

/**
 * Sprite sheets: 4 rows = facing down / up / left / right, 4 cols = walk
 * cycle frames. Cell size = w × h. Built by
 * scripts/fetch_pixellab_sheets.py (PixelLab walking-4-frames).
 */
export interface SpriteMeta {
  url: string
  w: number
  h: number
  /** px offset that pixel-matches the mockup when idle at the default seat */
  dx: number
  dy: number
}

export const MOVABLE_SPRITES: Partial<Record<CharacterId, SpriteMeta>> = {
  proposer: { url: '/office/sheet_proposer.png', w: 23, h: 51, dx: 0, dy: 0 },
  decider: { url: '/office/sheet_decider.png', w: 25, h: 51, dx: 0, dy: 0 },
  trader: { url: '/office/sheet_trader.png', w: 22, h: 51, dx: 0, dy: 0 },
}

export const FACING_ROW = { down: 0, up: 1, left: 2, right: 3 } as const
export const WALK_FRAME_MS = 150
export const SHEET_COLS = 4

export function isMovable(id: CharacterId): boolean {
  return id in MOVABLE_SPRITES
}

/**
 * Top-left draw position for a movable sprite anchored at logical px
 * (tile centre-bottom = feet).
 */
export function spriteDrawPos(
  meta: SpriteMeta,
  px: number,
  py: number,
): { x: number; y: number } {
  return {
    x: Math.round(px + TILE_PX / 2 - meta.w / 2 + meta.dx),
    y: Math.round(py + TILE_PX - meta.h + meta.dy),
  }
}

/** Click hit boxes (logical px) for characters baked into the background. */
export const BAKED_HITBOXES: ReadonlyArray<{
  id: CharacterId
  x: number
  y: number
  w: number
  h: number
}> = [
  { id: 'scanner', x: 79, y: 198, w: 50, h: 76 },
  { id: 'pattern_analyst', x: 157, y: 202, w: 54, h: 80 },
  { id: 'reviewer_1', x: 342, y: 337, w: 55, h: 65 },
  { id: 'reviewer_2', x: 412, y: 332, w: 55, h: 70 },
]

export function hitTestCharacters(
  characters: ReadonlyArray<Character>,
  x: number,
  y: number,
): Character | null {
  for (const char of characters) {
    const meta = MOVABLE_SPRITES[char.id]
    if (!meta) continue
    const p = spriteDrawPos(meta, char.pos.x * TILE_PX, char.pos.y * TILE_PX)
    if (x >= p.x && x < p.x + meta.w && y >= p.y && y < p.y + meta.h) {
      return char
    }
  }
  for (const box of BAKED_HITBOXES) {
    if (x >= box.x && x < box.x + box.w && y >= box.y && y < box.y + box.h) {
      return characters.find((c) => c.id === box.id) ?? null
    }
  }
  return null
}

export function loadImage(url: string, doc: Document = document): HTMLImageElement {
  const img = doc.createElement('img')
  img.src = url
  return img
}
