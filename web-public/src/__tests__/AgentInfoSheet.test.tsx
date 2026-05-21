import { beforeAll, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AgentInfoSheet } from '@/components/AgentInfoSheet'
import { initI18n } from '@/lib/i18n'
import type { Character, PublicEvent } from '@/types/public-event'

beforeAll(() => {
  initI18n({ lng: 'en' })
})

function mkChar(): Character {
  return {
    id: 'decider',
    pos: { x: 4, y: 8 },
    seat: { x: 4, y: 8 },
    facing: 'down',
    state: { kind: 'idle' },
  }
}

function mkEvent(overrides: Partial<PublicEvent> = {}): PublicEvent {
  return {
    event_id: Math.random().toString(36).slice(2),
    timestamp: new Date().toISOString(),
    event_type: 'decision_made',
    agent: 'decider',
    payload: { masked_symbol: 'STK-A', confidence: 0.7, action: 'entry' },
    ...overrides,
  }
}

describe('AgentInfoSheet', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <AgentInfoSheet
        open={false}
        character={mkChar()}
        timeline={[]}
        onClose={() => {}}
      />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders the last 5 events for the matching character', () => {
    const events: PublicEvent[] = []
    for (let i = 0; i < 7; i++) {
      events.push(mkEvent({ event_id: `e${i}` }))
    }
    render(
      <AgentInfoSheet
        open
        character={mkChar()}
        timeline={events}
        onClose={() => {}}
      />,
    )
    const list = screen.getByTestId('agent-recent-events')
    expect(list.querySelectorAll('li').length).toBe(5)
  })

  it('never renders reasoning_full even if present in payload', () => {
    const ev = mkEvent({
      payload: {
        masked_symbol: 'STK-A',
        confidence: 0.7,
        action: 'entry',
        reasoning_full: 'SECRET CHAIN OF THOUGHT THAT SHOULD NEVER LEAK',
      },
    })
    const { container } = render(
      <AgentInfoSheet
        open
        character={mkChar()}
        timeline={[ev]}
        onClose={() => {}}
      />,
    )
    expect(container.innerHTML).not.toContain('SECRET CHAIN OF THOUGHT')
    expect(container.innerHTML).not.toContain('reasoning_full')
  })

  it('strips 4-digit symbols that slipped through', () => {
    const ev = mkEvent({
      payload: { masked_symbol: '2330', confidence: 0.7, action: 'entry' },
    })
    const { container } = render(
      <AgentInfoSheet
        open
        character={mkChar()}
        timeline={[ev]}
        onClose={() => {}}
      />,
    )
    expect(container.innerHTML).not.toContain('2330')
    expect(container.innerHTML).toContain('STK-?')
  })
})
