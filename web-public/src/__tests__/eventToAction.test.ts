import { describe, expect, it } from 'vitest'
import { EVENT_ROUTER, routeEvent } from '@/lib/eventToAction'
import { EVENT_TYPES, type PublicEvent } from '@/types/public-event'

function mkEvent(
  event_type: string,
  payload: Record<string, unknown> = {},
): PublicEvent {
  return {
    event_id: 'evt-1',
    timestamp: new Date().toISOString(),
    event_type,
    agent: 'test',
    payload,
  }
}

describe('EVENT_ROUTER', () => {
  it('covers all 16 declared event types', () => {
    for (const t of EVENT_TYPES) {
      expect(EVENT_ROUTER[t]).toBeTypeOf('function')
    }
  })

  it('routes decision_made to decider with action=decided and durationMs=3000', () => {
    const a = EVENT_ROUTER.decision_made(
      mkEvent('decision_made', {
        masked_symbol: 'STK-A',
        confidence: 0.7,
        action: 'entry',
      }),
    )
    expect(a.targetCharId).toBe('decider')
    expect(a.action).toBe('decided')
    expect(a.durationMs).toBe(3000)
    expect(a.bubble).toContain('STK-A')
    expect(a.bubble).toContain('0.70')
    expect(a.bubble).toContain('entry')
  })

  it('routes review_node_started with node_index → reviewer_<n>', () => {
    const a = EVENT_ROUTER.review_node_started(
      mkEvent('review_node_started', { node_index: 3, node_name: 'aggregator' }),
    )
    expect(a.targetCharId).toBe('reviewer_3')
    expect(a.bubble).toBe('aggregator')
  })

  it('clamps node_index outside 1..5 to a valid reviewer', () => {
    const lo = EVENT_ROUTER.review_node_started(
      mkEvent('review_node_started', { node_index: 0, node_name: 'x' }),
    )
    const hi = EVENT_ROUTER.review_node_started(
      mkEvent('review_node_started', { node_index: 99, node_name: 'y' }),
    )
    expect(lo.targetCharId).toBe('reviewer_1')
    expect(hi.targetCharId).toBe('reviewer_5')
  })

  it('routes risk_off_triggered to guard', () => {
    const a = EVENT_ROUTER.risk_off_triggered(
      mkEvent('risk_off_triggered', {
        reason_category: 'drawdown',
        severity: 'high',
      }),
    )
    expect(a.targetCharId).toBe('guard')
    expect(a.action).toBe('alarm')
  })

  it('runs bubble text through the 4-digit mask', () => {
    const a = EVENT_ROUTER.decision_made(
      mkEvent('decision_made', {
        masked_symbol: '2330',
        confidence: 0.5,
        action: 'entry',
      }),
    )
    expect(a.bubble).not.toContain('2330')
    expect(a.bubble).toContain('STK-?')
  })

  it('routeEvent returns undefined for unknown event_type', () => {
    expect(routeEvent(mkEvent('future_unknown_v2'))).toBeUndefined()
  })

  it('routeEvent returns an action for a known event_type', () => {
    const a = routeEvent(mkEvent('wfa_passed'))
    expect(a?.targetCharId).toBe('validator')
    expect(a?.action).toBe('pass')
  })
})
