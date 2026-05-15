import { afterEach, describe, it, expect, vi } from 'vitest'
import { render, screen, act, cleanup } from '@testing-library/react'
import { MaskedEventsFeed } from '@/components/MaskedEventsFeed'

/**
 * Fake EventSource that exposes a `pushMessage` so the test can synchronously
 * dispatch SSE-style messages without a real HTTP connection.
 */
class FakeEventSource {
  listeners: Record<string, ((ev: MessageEvent) => void)[]> = {}
  closed = false

  addEventListener(type: string, fn: (ev: MessageEvent) => void) {
    ;(this.listeners[type] ??= []).push(fn)
  }
  removeEventListener(type: string, fn: (ev: MessageEvent) => void) {
    this.listeners[type] = (this.listeners[type] ?? []).filter((f) => f !== fn)
  }
  close() {
    this.closed = true
  }

  pushMessage(payload: object) {
    const ev = { data: JSON.stringify(payload) } as MessageEvent
    for (const fn of this.listeners['message'] ?? []) {
      fn(ev)
    }
  }
}

function newSyntheticEvent(id: string, overrides: Partial<{
  event_type: string
  agent: string
  payload: Record<string, unknown>
}> = {}) {
  return {
    event_id: id,
    timestamp: '2026-05-15T13:30:00+08:00',
    event_type: overrides.event_type ?? 'decision_made',
    agent: overrides.agent ?? 'decider',
    payload: overrides.payload ?? { masked_symbol: 'STK-A', confidence: 0.7 },
  }
}

afterEach(() => {
  cleanup()
})

describe('MaskedEventsFeed', () => {
  it('shows idle state with zero rows on mount', () => {
    const factory = vi.fn(() => new FakeEventSource() as unknown as EventSource)
    render(<MaskedEventsFeed eventSourceFactory={factory} />)
    expect(screen.queryByTestId('masked-events-list')).toBeNull()
    expect(screen.getByText(/目前 idle/)).toBeInTheDocument()
  })

  it('prepends a new event when SSE pushes one', () => {
    const es = new FakeEventSource()
    render(
      <MaskedEventsFeed
        eventSourceFactory={() => es as unknown as EventSource}
      />,
    )
    act(() => {
      es.pushMessage(newSyntheticEvent('evt_1'))
    })
    const rows = screen.getAllByTestId('masked-event-row')
    expect(rows).toHaveLength(1)
    expect(rows[0].textContent).toContain('decision_made')
    expect(rows[0].textContent).toContain('STK-A')
  })

  it('evicts oldest when 51 events received (cap = 50)', () => {
    const es = new FakeEventSource()
    render(
      <MaskedEventsFeed
        eventSourceFactory={() => es as unknown as EventSource}
      />,
    )
    act(() => {
      for (let i = 0; i < 51; i++) {
        es.pushMessage(newSyntheticEvent(`evt_${i}`))
      }
    })
    const rows = screen.getAllByTestId('masked-event-row')
    expect(rows).toHaveLength(50)
    expect(rows[0].textContent).toContain('decision_made')
  })

  it('dedupes a duplicate event_id on SSE reconnect', () => {
    const es = new FakeEventSource()
    render(
      <MaskedEventsFeed
        eventSourceFactory={() => es as unknown as EventSource}
      />,
    )
    act(() => {
      es.pushMessage(newSyntheticEvent('evt_dup'))
      es.pushMessage(newSyntheticEvent('evt_dup'))
    })
    const rows = screen.getAllByTestId('masked-event-row')
    expect(rows).toHaveLength(1)
  })

  it('client-side strips DENYLIST keys even if server slips one through', () => {
    const es = new FakeEventSource()
    render(
      <MaskedEventsFeed
        eventSourceFactory={() => es as unknown as EventSource}
      />,
    )
    act(() => {
      es.pushMessage(
        newSyntheticEvent('evt_rogue', {
          payload: { symbol: '2330', masked_symbol: 'STK-A', confidence: 0.7 },
        }),
      )
    })
    const row = screen.getByTestId('masked-event-row')
    expect(row.textContent).toContain('STK-A')
    expect(row.textContent).not.toContain('"symbol":"2330"')
    expect(row.textContent).not.toMatch(/"symbol"\s*:\s*"2330"/)
  })

  it('closes the EventSource on unmount', () => {
    const es = new FakeEventSource()
    const { unmount } = render(
      <MaskedEventsFeed
        eventSourceFactory={() => es as unknown as EventSource}
      />,
    )
    unmount()
    expect(es.closed).toBe(true)
  })
})
