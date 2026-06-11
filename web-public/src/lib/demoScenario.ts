/**
 * Demo scenario driver — loops a scripted trading day through the same
 * routeEvent → enqueueAction path the SSE feed uses, so the office can be
 * exercised without a backend. Enabled via `/?demo=1`.
 *
 * Long real-world durations (e.g. awaiting_confirm 30 min) are clamped so
 * the loop stays watchable.
 */

import { routeEvent } from '@/lib/eventToAction'
import { useSceneStore } from '@/stores/scene'
import type { PublicEvent } from '@/types/public-event'

const MAX_ACTION_MS = 6000

interface DemoStep {
  delayMs: number
  event_type: string
  payload: Record<string, unknown>
}

const SCRIPT: DemoStep[] = [
  { delayMs: 1000, event_type: 'screener_started', payload: { universe_size: 1742 } },
  { delayMs: 4000, event_type: 'screener_completed', payload: { candidate_count: 12 } },
  { delayMs: 3000, event_type: 'pattern_detected', payload: { pattern: 'VCP', masked_symbol: 'STK-A', score: 0.82 } },
  { delayMs: 3000, event_type: 'decider_thinking', payload: { masked_symbol: 'STK-A' } },
  { delayMs: 5000, event_type: 'decision_made', payload: { masked_symbol: 'STK-A', confidence: 0.78, action: 'entry' } },
  // give the decider time to walk to the counter, speak, and walk home
  { delayMs: 9000, event_type: 'awaiting_confirm', payload: { masked_symbol: 'STK-A' } },
  { delayMs: 5000, event_type: 'order_sent', payload: { masked_symbol: 'STK-A' } },
  { delayMs: 4000, event_type: 'journal_written', payload: { journal_kind: 'entry_record' } },
  { delayMs: 4000, event_type: 'review_node_started', payload: { node_index: 1, node_name: 'execution_review' } },
  { delayMs: 4000, event_type: 'review_node_started', payload: { node_index: 3, node_name: 'aggregator' } },
  { delayMs: 4000, event_type: 'review_completed', payload: { proposals_created_count: 2 } },
  { delayMs: 4000, event_type: 'proposal_created', payload: { priority: 'P1', target_section: 'sizing' } },
  { delayMs: 9000, event_type: 'wfa_started', payload: {} },
  { delayMs: 5000, event_type: 'wfa_passed', payload: {} },
  { delayMs: 4000, event_type: 'journal_queried', payload: { result_count: 37 } },
  { delayMs: 4000, event_type: 'risk_off_triggered', payload: { reason_category: 'drawdown', severity: 'medium' } },
  { delayMs: 6000, event_type: 'screener_started', payload: { universe_size: 1742 } },
]

export function isDemoMode(search: string = window.location.search): boolean {
  return new URLSearchParams(search).has('demo')
}

/** Start the looping scenario. Returns a stop function. */
export function startDemo(): () => void {
  let timer = 0
  let cycle = 0
  let idx = 0

  function fire(): void {
    const step = SCRIPT[idx]!
    const event: PublicEvent = {
      event_id: `demo-${cycle}-${idx}`,
      timestamp: new Date().toISOString(),
      event_type: step.event_type,
      agent: 'demo',
      payload: step.payload,
    }
    const action = routeEvent(event)
    const store = useSceneStore.getState()
    if (action) {
      store.enqueueAction({
        ...action,
        durationMs: Math.min(action.durationMs, MAX_ACTION_MS),
      })
    }
    store.pushTimeline(event)

    idx += 1
    if (idx >= SCRIPT.length) {
      idx = 0
      cycle += 1
    }
    timer = window.setTimeout(fire, SCRIPT[idx]!.delayMs)
  }

  timer = window.setTimeout(fire, SCRIPT[0]!.delayMs)
  return () => window.clearTimeout(timer)
}
