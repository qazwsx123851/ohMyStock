/**
 * Default seat for every character instance — matches
 * docs/frontend-public-pixel.md §4.2 (13 entries).
 */

import type { CharacterId, GridPos } from '@/types/public-event'

export const DEFAULT_SEATS: Record<CharacterId, GridPos> = {
  scanner: { x: 3, y: 2 },
  pattern_analyst: { x: 16, y: 2 },
  decider: { x: 4, y: 8 },
  trader: { x: 8, y: 8 },
  librarian: { x: 18, y: 8 },
  reviewer_1: { x: 14, y: 14 },
  reviewer_2: { x: 16, y: 14 },
  reviewer_3: { x: 18, y: 14 },
  reviewer_4: { x: 20, y: 14 },
  reviewer_5: { x: 22, y: 14 },
  proposer: { x: 10, y: 11 },
  validator: { x: 4, y: 14 },
  guard: { x: 0, y: 8 },
}
