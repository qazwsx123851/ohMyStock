/**
 * EVENT_ROUTER — maps masked PublicEvent (16 event_type values) to a
 * CharacterAction for the scene. Speech-bubble text is run through
 * stripFourDigit() defensively.
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirement: Event Router)
 */

import { stripFourDigit } from '@/lib/maskBubble'
import { DEFAULT_SEATS } from '@/canvas/characters/seats'
import {
  EVENT_TYPES,
  type CharacterAction,
  type CharacterId,
  type EventType,
  type PublicEvent,
} from '@/types/public-event'

function asNum(v: unknown, fallback = 0): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback
}

function asStr(v: unknown, fallback = ''): string {
  return typeof v === 'string' ? v : fallback
}

function bubble(text: string): string {
  return stripFourDigit(text)
}

function actionAt(
  charId: CharacterId,
  action: string,
  durationMs: number,
  bubbleText?: string,
  targetPos?: { x: number; y: number },
): CharacterAction {
  return {
    targetCharId: charId,
    action,
    durationMs,
    bubble: bubbleText !== undefined ? bubble(bubbleText) : undefined,
    targetPos: targetPos ?? DEFAULT_SEATS[charId],
  }
}

/**
 * Walk choreography (movable characters only — the state machine walks
 * them back to their seat automatically once the action finishes):
 *   decision_made    → decider crosses to the counter to brief the trader
 *   proposal_created → proposer steps to the centre floor to announce
 */
const COUNTER_FRONT = { x: 24, y: 16 }
const CENTRE_FLOOR = { x: 15, y: 14 }

export const EVENT_ROUTER: Record<
  EventType,
  (event: PublicEvent) => CharacterAction
> = {
  screener_started: (e) =>
    actionAt(
      'scanner',
      'scanning',
      5000,
      `掃 ${asNum(e.payload.universe_size)} 檔...`,
    ),
  screener_completed: (e) =>
    actionAt(
      'scanner',
      'report',
      3000,
      `找到 ${asNum(e.payload.candidate_count)} 檔候選`,
    ),
  pattern_detected: (e) =>
    actionAt(
      'pattern_analyst',
      'marking',
      2000,
      `${asStr(e.payload.pattern)} ${asStr(e.payload.masked_symbol)} (score ${asNum(e.payload.score).toFixed(2)})`,
    ),
  decider_thinking: (e) =>
    actionAt(
      'decider',
      'thinking',
      4000,
      `scoring ${asStr(e.payload.masked_symbol)}...`,
    ),
  decision_made: (e) =>
    actionAt(
      'decider',
      'decided',
      3000,
      `${asStr(e.payload.masked_symbol)} (conf ${asNum(e.payload.confidence).toFixed(2)}) → ${asStr(e.payload.action)}`,
      COUNTER_FRONT,
    ),
  awaiting_confirm: (e) =>
    actionAt(
      'trader',
      'waiting_confirm',
      30 * 60 * 1000,
      `等待 confirm: ${asStr(e.payload.masked_symbol)}`,
    ),
  order_sent: (e) =>
    actionAt(
      'trader',
      'sending_order',
      2000,
      `送單 ${asStr(e.payload.masked_symbol)}`,
    ),
  journal_written: (e) =>
    actionAt(
      'librarian',
      'writing',
      1500,
      `寫入 ${asStr(e.payload.journal_kind)}`,
    ),
  journal_queried: (e) =>
    actionAt(
      'librarian',
      'searching',
      1500,
      `查詢 (${asNum(e.payload.result_count)} 筆)`,
    ),
  review_node_started: (e) => {
    const nodeIdx = asNum(e.payload.node_index, 1)
    const clamped = Math.min(5, Math.max(1, nodeIdx))
    const id = `reviewer_${clamped}` as CharacterId
    return actionAt(id, 'speaking', 5000, asStr(e.payload.node_name))
  },
  review_completed: (e) =>
    actionAt(
      'reviewer_1',
      'dispersing',
      3000,
      `產出 ${asNum(e.payload.proposals_created_count)} 提案`,
    ),
  proposal_created: (e) =>
    actionAt(
      'proposer',
      'pinning',
      4000,
      `[${asStr(e.payload.priority)}] ${asStr(e.payload.target_section)}`,
      CENTRE_FLOOR,
    ),
  wfa_started: () =>
    actionAt('validator', 'experimenting', 6000, 'WFA 驗證中...'),
  wfa_passed: () => actionAt('validator', 'pass', 2000, '✓ 通過'),
  wfa_failed: () => actionAt('validator', 'fail', 2000, '✗ 失敗'),
  risk_off_triggered: (e) =>
    actionAt(
      'guard',
      'alarm',
      8000,
      `⚠ ${asStr(e.payload.reason_category)} (${asStr(e.payload.severity)})`,
    ),
}

export function routeEvent(event: PublicEvent): CharacterAction | undefined {
  if (!EVENT_TYPES.includes(event.event_type as EventType)) return undefined
  const handler = EVENT_ROUTER[event.event_type as EventType]
  if (!handler) return undefined
  return handler(event)
}
