/**
 * Runtime-generated Pokémon-style character sprites.
 *
 * 64×64 sheet = 4 facings × 4 frames × 16×16. Each character gets a
 * distinct hair / shirt / cap combination matched to the design mockup
 * (e.g. the decider is the red-capped trainer at the room centre).
 *
 * Frames: 0 = stand, 1 = left step, 2 = right step, 3 = acting (arm up).
 * Rows:   0 = down, 1 = up, 2 = left, 3 = right.
 *
 * Spec: openspec/specs/web-public-pixel-office/spec.md
 *       (Requirement: Character Roster)
 */

import {
  BLUE,
  BLUE_DARK,
  CYAN,
  GREEN_LEAF,
  HAIR_BLACK,
  HAIR_BLOND,
  HAIR_BROWN,
  INK,
  PANTS,
  PANTS_BROWN,
  RED,
  SHOES,
  SKIN,
  SKIN_SHADOW,
  TEAL,
  UNIFORM_NAVY,
  WHITE,
  type PaletteHex,
} from '@/styles/palette'
import type { CharacterId } from '@/types/public-event'

export interface CharacterStyle {
  hair: PaletteHex
  shirt: PaletteHex
  pants: PaletteHex
  cap?: PaletteHex
}

export const CHARACTER_STYLES: Record<CharacterId, CharacterStyle> = {
  scanner: { hair: HAIR_BLACK, shirt: RED, pants: PANTS },
  pattern_analyst: { hair: HAIR_BLACK, shirt: BLUE, pants: PANTS },
  decider: { hair: HAIR_BLACK, shirt: RED, pants: PANTS, cap: RED },
  trader: { hair: HAIR_BROWN, shirt: BLUE, pants: PANTS_BROWN },
  librarian: { hair: HAIR_BROWN, shirt: GREEN_LEAF, pants: PANTS_BROWN },
  reviewer_1: { hair: HAIR_BROWN, shirt: TEAL, pants: PANTS },
  reviewer_2: { hair: HAIR_BLACK, shirt: BLUE_DARK, pants: PANTS },
  reviewer_3: { hair: HAIR_BLOND, shirt: CYAN, pants: PANTS },
  reviewer_4: { hair: HAIR_BROWN, shirt: BLUE, pants: PANTS },
  reviewer_5: { hair: HAIR_BLACK, shirt: TEAL, pants: PANTS },
  proposer: { hair: HAIR_BLACK, shirt: BLUE_DARK, pants: PANTS },
  validator: { hair: HAIR_BLACK, shirt: CYAN, pants: PANTS },
  guard: { hair: HAIR_BLACK, shirt: UNIFORM_NAVY, pants: PANTS, cap: UNIFORM_NAVY },
}

export function shirtColourFor(id: CharacterId): PaletteHex {
  return CHARACTER_STYLES[id].shirt
}

type Facing = 0 | 1 | 2 | 3 // down, up, left, right

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

function drawLegs(
  ctx: CanvasRenderingContext2D,
  ox: number,
  oy: number,
  s: CharacterStyle,
  frame: number,
): void {
  px(ctx, ox + 4, oy + 12, 8, 2, s.pants)
  if (frame === 1) {
    // left leg forward
    px(ctx, ox + 5, oy + 14, 2, 1, s.pants)
    px(ctx, ox + 5, oy + 15, 2, 1, SHOES)
    px(ctx, ox + 9, oy + 14, 2, 2, SHOES)
  } else if (frame === 2) {
    // right leg forward
    px(ctx, ox + 5, oy + 14, 2, 2, SHOES)
    px(ctx, ox + 9, oy + 14, 2, 1, s.pants)
    px(ctx, ox + 9, oy + 15, 2, 1, SHOES)
  } else {
    px(ctx, ox + 5, oy + 14, 2, 1, s.pants)
    px(ctx, ox + 9, oy + 14, 2, 1, s.pants)
    px(ctx, ox + 5, oy + 15, 2, 1, SHOES)
    px(ctx, ox + 9, oy + 15, 2, 1, SHOES)
  }
}

function drawTorsoFront(
  ctx: CanvasRenderingContext2D,
  ox: number,
  oy: number,
  s: CharacterStyle,
  frame: number,
): void {
  px(ctx, ox + 4, oy + 8, 8, 4, s.shirt)
  if (frame === 3) {
    // acting: right arm raised
    px(ctx, ox + 3, oy + 8, 1, 3, s.shirt)
    px(ctx, ox + 3, oy + 11, 1, 1, SKIN)
    px(ctx, ox + 12, oy + 5, 1, 3, s.shirt)
    px(ctx, ox + 12, oy + 4, 1, 1, SKIN)
  } else {
    px(ctx, ox + 3, oy + 8, 1, 3, s.shirt)
    px(ctx, ox + 12, oy + 8, 1, 3, s.shirt)
    px(ctx, ox + 3, oy + 11, 1, 1, SKIN)
    px(ctx, ox + 12, oy + 11, 1, 1, SKIN)
  }
}

function drawHeadDown(
  ctx: CanvasRenderingContext2D,
  ox: number,
  oy: number,
  s: CharacterStyle,
): void {
  if (s.cap) {
    px(ctx, ox + 5, oy + 1, 6, 1, s.cap)
    px(ctx, ox + 4, oy + 2, 8, 2, s.cap)
    px(ctx, ox + 3, oy + 4, 10, 1, s.cap) // brim
    px(ctx, ox + 4, oy + 5, 8, 3, SKIN)
  } else {
    px(ctx, ox + 5, oy + 1, 6, 1, s.hair)
    px(ctx, ox + 4, oy + 2, 8, 3, s.hair)
    px(ctx, ox + 3, oy + 3, 1, 3, s.hair)
    px(ctx, ox + 12, oy + 3, 1, 3, s.hair)
    px(ctx, ox + 4, oy + 5, 8, 3, SKIN)
    px(ctx, ox + 4, oy + 5, 1, 1, s.hair) // bang corners
    px(ctx, ox + 11, oy + 5, 1, 1, s.hair)
  }
  // eyes + chin shade
  px(ctx, ox + 6, oy + 6, 1, 1, INK)
  px(ctx, ox + 9, oy + 6, 1, 1, INK)
  px(ctx, ox + 6, oy + 7, 4, 1, SKIN_SHADOW)
}

function drawHeadUp(
  ctx: CanvasRenderingContext2D,
  ox: number,
  oy: number,
  s: CharacterStyle,
): void {
  const top = s.cap ?? s.hair
  px(ctx, ox + 5, oy + 1, 6, 1, top)
  px(ctx, ox + 4, oy + 2, 8, 4, top)
  px(ctx, ox + 3, oy + 3, 10, 3, top)
  px(ctx, ox + 4, oy + 6, 8, 2, s.hair)
}

function drawHeadSide(
  ctx: CanvasRenderingContext2D,
  ox: number,
  oy: number,
  s: CharacterStyle,
  left: boolean,
): void {
  const faceX = left ? ox + 4 : ox + 8
  const backX = left ? ox + 9 : ox + 3
  if (s.cap) {
    px(ctx, ox + 5, oy + 1, 6, 1, s.cap)
    px(ctx, ox + 4, oy + 2, 8, 2, s.cap)
    // brim points the way the sprite faces
    px(ctx, left ? ox + 2 : ox + 9, oy + 3, 5, 1, s.cap)
    px(ctx, ox + 4, oy + 4, 8, 1, s.hair)
  } else {
    px(ctx, ox + 5, oy + 1, 6, 1, s.hair)
    px(ctx, ox + 4, oy + 2, 8, 3, s.hair)
    px(ctx, left ? ox + 3 : ox + 12, oy + 3, 1, 3, s.hair)
  }
  px(ctx, faceX, oy + 5, 4, 3, SKIN)
  px(ctx, backX, oy + 5, 4, 3, s.hair)
  px(ctx, left ? ox + 5 : ox + 10, oy + 6, 1, 1, INK)
}

function fillCell(
  ctx: CanvasRenderingContext2D,
  ox: number,
  oy: number,
  s: CharacterStyle,
  facing: Facing,
  frame: number,
): void {
  switch (facing) {
    case 0:
      drawHeadDown(ctx, ox, oy, s)
      drawTorsoFront(ctx, ox, oy, s, frame)
      break
    case 1:
      drawHeadUp(ctx, ox, oy, s)
      drawTorsoFront(ctx, ox, oy, s, frame === 3 ? 0 : frame)
      break
    case 2:
      drawHeadSide(ctx, ox, oy, s, true)
      px(ctx, ox + 4, oy + 8, 8, 4, s.shirt)
      px(ctx, ox + 7, oy + 9, 2, 2, frame === 3 ? SKIN : s.shirt)
      break
    case 3:
      drawHeadSide(ctx, ox, oy, s, false)
      px(ctx, ox + 4, oy + 8, 8, 4, s.shirt)
      px(ctx, ox + 7, oy + 9, 2, 2, frame === 3 ? SKIN : s.shirt)
      break
  }
  drawLegs(ctx, ox, oy, s, frame)
  // collar highlight keeps the silhouette readable on dark shirts
  if (facing === 0 && s.shirt !== WHITE) {
    px(ctx, ox + 7, oy + 8, 2, 1, WHITE)
  }
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
  const style = CHARACTER_STYLES[id]
  for (let row = 0; row < 4; row++) {
    for (let col = 0; col < 4; col++) {
      fillCell(ctx, col * 16, row * 16, style, row as Facing, col)
    }
  }
  return canvas
}
