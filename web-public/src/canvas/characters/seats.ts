/**
 * Default seat + facing for every character instance, on the 35×27 grid of
 * the design-mockup background.
 *
 * Movable characters (proposer / decider / trader) stand at their mockup
 * spots; baked characters (scanner / pattern_analyst / reviewer_1 / _2) are
 * anchored over their painted bodies for click + bubble placement; the rest
 * are bubble-only anchors near their themed furniture.
 */

import type { CharacterId, Facing, GridPos } from '@/types/public-event'

export const DEFAULT_SEATS: Record<CharacterId, GridPos> = {
  // dynamic sprites
  proposer: { x: 18, y: 10 },
  decider: { x: 17, y: 16 },
  trader: { x: 26, y: 12 },
  // baked into the background
  scanner: { x: 6, y: 12 },
  pattern_analyst: { x: 11, y: 12 },
  reviewer_1: { x: 23, y: 21 },
  reviewer_2: { x: 27, y: 21 },
  // bubble-only anchors
  librarian: { x: 6, y: 21 },
  validator: { x: 15, y: 22 },
  guard: { x: 0, y: 15 },
  reviewer_3: { x: 25, y: 24 },
  reviewer_4: { x: 21, y: 24 },
  reviewer_5: { x: 28, y: 24 },
}

export const DEFAULT_FACINGS: Record<CharacterId, Facing> = {
  scanner: 'up',
  pattern_analyst: 'up',
  decider: 'down',
  trader: 'down',
  librarian: 'up',
  reviewer_1: 'up',
  reviewer_2: 'up',
  reviewer_3: 'up',
  reviewer_4: 'up',
  reviewer_5: 'up',
  proposer: 'down',
  validator: 'up',
  guard: 'right',
}
