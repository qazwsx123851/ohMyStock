/**
 * Default seat + facing for every character instance — positions match the
 * reference design mockup (desks mid-left, counter right, review desks
 * bottom-right, library table bottom-left).
 */

import type { CharacterId, Facing, GridPos } from '@/types/public-event'

export const DEFAULT_SEATS: Record<CharacterId, GridPos> = {
  scanner: { x: 2, y: 7 },
  pattern_analyst: { x: 5, y: 7 },
  decider: { x: 9, y: 9 },
  trader: { x: 16, y: 7 },
  librarian: { x: 5, y: 13 },
  reviewer_1: { x: 13, y: 13 },
  reviewer_2: { x: 16, y: 13 },
  reviewer_3: { x: 18, y: 13 },
  reviewer_4: { x: 12, y: 14 },
  reviewer_5: { x: 20, y: 13 },
  proposer: { x: 8, y: 4 },
  validator: { x: 10, y: 13 },
  guard: { x: 0, y: 8 },
}

export const DEFAULT_FACINGS: Record<CharacterId, Facing> = {
  scanner: 'up',
  pattern_analyst: 'up',
  decider: 'down',
  trader: 'down',
  librarian: 'up',
  reviewer_1: 'up',
  reviewer_2: 'up',
  reviewer_3: 'left',
  reviewer_4: 'up',
  reviewer_5: 'right',
  proposer: 'down',
  validator: 'up',
  guard: 'right',
}
