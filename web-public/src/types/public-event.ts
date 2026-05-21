/**
 * Shared types for the web-public pixel office.
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 */

export const EVENT_TYPES = [
  'screener_started',
  'screener_completed',
  'pattern_detected',
  'decider_thinking',
  'decision_made',
  'awaiting_confirm',
  'order_sent',
  'journal_written',
  'journal_queried',
  'review_node_started',
  'review_completed',
  'proposal_created',
  'wfa_started',
  'wfa_passed',
  'wfa_failed',
  'risk_off_triggered',
] as const

export type EventType = (typeof EVENT_TYPES)[number]

export interface PublicEvent {
  event_id: string
  timestamp: string
  event_type: EventType | string
  agent: string
  payload: Record<string, unknown>
}

export type CharacterId =
  | 'scanner'
  | 'pattern_analyst'
  | 'decider'
  | 'trader'
  | 'librarian'
  | 'reviewer_1'
  | 'reviewer_2'
  | 'reviewer_3'
  | 'reviewer_4'
  | 'reviewer_5'
  | 'proposer'
  | 'validator'
  | 'guard'

export const ALL_CHARACTER_IDS: readonly CharacterId[] = [
  'scanner',
  'pattern_analyst',
  'decider',
  'trader',
  'librarian',
  'reviewer_1',
  'reviewer_2',
  'reviewer_3',
  'reviewer_4',
  'reviewer_5',
  'proposer',
  'validator',
  'guard',
]

export interface GridPos {
  x: number
  y: number
}

export type GridKey = `${number},${number}`

export function gridKey(p: GridPos): GridKey {
  return `${p.x},${p.y}`
}

export type Facing = 'down' | 'up' | 'left' | 'right'

export type CharacterState =
  | { kind: 'idle' }
  | { kind: 'walking'; path: GridPos[]; pathIdx: number; lastStepAt: number }
  | {
      kind: 'acting'
      action: string
      startedAt: number
      durationMs: number
      bubble?: string
    }

export interface CharacterAction {
  targetCharId: CharacterId
  action: string
  durationMs: number
  bubble?: string
  targetPos?: GridPos
}

export interface Character {
  id: CharacterId
  pos: GridPos
  facing: Facing
  state: CharacterState
  seat: GridPos
}

export interface Region {
  label: string
  x: number
  y: number
  w: number
  h: number
}

export const GRID_COLS = 24
export const GRID_ROWS = 16
export const TILE_PX = 16
export const CANVAS_LOGICAL_W = GRID_COLS * TILE_PX // 384
export const CANVAS_LOGICAL_H = GRID_ROWS * TILE_PX // 256
export const CSS_SCALE = 2
