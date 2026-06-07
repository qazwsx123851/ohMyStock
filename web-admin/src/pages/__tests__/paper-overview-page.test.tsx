import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
  type Mock,
} from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, RouterProvider, createMemoryRouter } from 'react-router'
import { PaperOverviewPage } from '../PaperOverviewPage'
import * as stubs from '../stubs'
import { useAuthStore, useLiveFeedStore } from '@/stores'

// Mock the SSE hook to a no-op so jsdom does not need EventSource. We drive
// the store directly via useLiveFeedStore.getState().pushEvent(...).
vi.mock('@/hooks/useAdminEvents', () => ({ useAdminEvents: () => {} }))

// ---------------------------------------------------------------------------
// Synthetic payloads
// ---------------------------------------------------------------------------

const STATS_OK = {
  asof_date: '2026-05-08',
  decisions_made: 3,
  entries_pending: 1,
  entries_filled: 2,
  rejects: 0,
  expires: 0,
  auto_execute_audits: 0,
}

function pendingItem(overrides: Record<string, unknown> = {}) {
  return {
    decision_id: 'd1',
    symbol: '2330',
    created_at: '2026-05-08T13:00:00+08:00',
    age_seconds: 30,
    ttl_seconds: 1800,
    current_price: 980,
    final_sizing_pct: 0.05,
    ...overrides,
  }
}

function positionItem(overrides: Record<string, unknown> = {}) {
  return {
    decision_id: 'p1',
    symbol: '2330',
    sector: 'semis',
    entry_price: 950,
    qty_lots: 2,
    entry_ts: '2026-05-06T09:00:00+08:00',
    hold_days: 2,
    stop_loss: 920,
    t1_target: 1010,
    time_stop_date: '2026-05-22',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Fetch routing helper
// ---------------------------------------------------------------------------

type RouteResult =
  | { kind: 'ok'; body: unknown }
  | { kind: 'err'; status: number; body: unknown }
  | { kind: 'pending' }

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function setupFetch(routes: {
  stats?: RouteResult
  positions?: RouteResult
  pending?: RouteResult
  confirm?: RouteResult
  reject?: RouteResult
  sweep?: RouteResult
}): Mock {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : (input as Request).url

    const pick = (r: RouteResult | undefined): Promise<Response> => {
      if (!r) {
        return Promise.resolve(
          jsonResponse(
            { ok: false, error: { code: 'unmocked', message: url } },
            404,
          ),
        )
      }
      if (r.kind === 'pending') return new Promise<Response>(() => undefined)
      if (r.kind === 'err') {
        return Promise.resolve(jsonResponse(r.body, r.status))
      }
      return Promise.resolve(jsonResponse(r.body, 200))
    }

    if (url.includes('/api/admin/stats/today')) return pick(routes.stats)
    if (url.includes('/api/admin/positions/open')) return pick(routes.positions)
    if (url.includes('/api/admin/confirm-gate/pending'))
      return pick(routes.pending)
    if (url.includes('/api/admin/confirm-gate/confirm'))
      return pick(routes.confirm)
    if (url.includes('/api/admin/confirm-gate/reject')) return pick(routes.reject)
    if (url.includes('/api/admin/confirm-gate/sweep-expired'))
      return pick(routes.sweep)
    return Promise.resolve(
      jsonResponse(
        { ok: false, error: { code: 'unhandled_in_test', message: url } },
        404,
      ),
    )
  })
  vi.spyOn(globalThis, 'fetch').mockImplementation(fn as never)
  return fn
}

// ---------------------------------------------------------------------------
// Render helpers
// ---------------------------------------------------------------------------

function makeQc() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
}

function renderPage() {
  const qc = makeQc()
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/paper']}>
        <PaperOverviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  useAuthStore.getState().setToken('test-token')
  useLiveFeedStore.getState().clear()
})

afterEach(() => {
  vi.restoreAllMocks()
  useLiveFeedStore.getState().clear()
})

// ===========================================================================
// 7.2 — router mounts real page; stubs no longer export PaperPage
// ===========================================================================

describe('Routing & stubs', () => {
  it('routes /paper to PaperOverviewPage (heading "模擬交易", no "建置中")', async () => {
    setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: {
          ok: true,
          data: { items: [], asof_iso: '2026-05-08T13:00:00+08:00', count: 0 },
        },
      },
      pending: {
        kind: 'ok',
        body: { ok: true, data: { items: [], timeout_minutes: 30 } },
      },
    })

    const qc = makeQc()
    const router = createMemoryRouter(
      [{ path: '/paper', element: <PaperOverviewPage /> }],
      { initialEntries: ['/paper'] },
    )
    render(
      <QueryClientProvider client={qc}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    expect(await screen.findByText('模擬交易')).toBeInTheDocument()
    expect(screen.queryByText('建置中')).toBeNull()
  })

  it('stubs.tsx no longer exports PaperPage', () => {
    expect(Object.keys(stubs)).not.toContain('PaperPage')
  })
})

// ===========================================================================
// 7.3 — KPI Row scenarios
// ===========================================================================

describe('KPI Row', () => {
  it('three endpoints succeed → cards show real counters', async () => {
    setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: {
          ok: true,
          data: {
            items: [positionItem({ decision_id: 'p1', symbol: '2330' })],
            asof_iso: '2026-05-08T13:00:00+08:00',
            count: 1,
          },
        },
      },
      pending: {
        kind: 'ok',
        body: {
          ok: true,
          data: {
            items: [pendingItem({ decision_id: 'd1', symbol: '2330' })],
            timeout_minutes: 30,
          },
        },
      },
    })

    renderPage()
    await screen.findByText('今日決策')
    await waitFor(() => {
      expect(
        screen.getByText('今日決策').parentElement!.textContent,
      ).toContain('3')
    })
    expect(
      screen.getByText('持倉檔數').parentElement!.textContent,
    ).toContain('1')
    expect(
      screen.getByText('待確認').parentElement!.textContent,
    ).toContain('1')
    expect(
      screen.getByText('今日已成交').parentElement!.textContent,
    ).toContain('2')
  })

  it('stats fails → its cards show error icon, others stay real', async () => {
    setupFetch({
      stats: {
        kind: 'err',
        status: 500,
        body: {
          ok: false,
          error: { code: 'db_locked', message: 'sqlite locked' },
        },
      },
      positions: {
        kind: 'ok',
        body: {
          ok: true,
          data: {
            items: [positionItem({ decision_id: 'p1' })],
            asof_iso: '...',
            count: 4,
          },
        },
      },
      pending: {
        kind: 'ok',
        body: {
          ok: true,
          data: {
            items: [pendingItem({ decision_id: 'd1' })],
            timeout_minutes: 30,
          },
        },
      },
    })

    const { container } = renderPage()
    await waitFor(() => {
      const errorTexts = container.querySelectorAll('.text-destructive')
      expect(errorTexts.length).toBeGreaterThanOrEqual(2)
    })
    expect(
      screen.getByText('持倉檔數').parentElement!.textContent,
    ).toContain('4')
  })

  it('all queries in-flight → 4 cards render skeleton (aria-busy)', () => {
    setupFetch({
      stats: { kind: 'pending' },
      positions: { kind: 'pending' },
      pending: { kind: 'pending' },
    })

    const { container } = renderPage()
    const skeletons = container.querySelectorAll('[aria-busy="true"]')
    expect(skeletons.length).toBeGreaterThanOrEqual(4)
  })
})

// ===========================================================================
// 7.4 — Pending list
// ===========================================================================

describe('Pending list', () => {
  it('empty → renders 目前無待確認', async () => {
    setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: { ok: true, data: { items: [], asof_iso: '...', count: 0 } },
      },
      pending: {
        kind: 'ok',
        body: { ok: true, data: { items: [], timeout_minutes: 30 } },
      },
    })

    renderPage()
    expect(await screen.findByText('目前無待確認')).toBeInTheDocument()
  })

  it('2 items → renders both symbols', async () => {
    setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: { ok: true, data: { items: [], asof_iso: '...', count: 0 } },
      },
      pending: {
        kind: 'ok',
        body: {
          ok: true,
          data: {
            items: [
              pendingItem({ decision_id: 'd1', symbol: '2330' }),
              pendingItem({ decision_id: 'd2', symbol: '2454' }),
            ],
            timeout_minutes: 30,
          },
        },
      },
    })

    renderPage()
    expect(await screen.findByText('2330')).toBeInTheDocument()
    expect(screen.getByText('2454')).toBeInTheDocument()
  })

  it('clicking ✓ 確認 → POST /confirm-gate/confirm with {decision_id, user:"mark"}', async () => {
    const user = userEvent.setup()
    const fetchSpy = setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: { ok: true, data: { items: [], asof_iso: '...', count: 0 } },
      },
      pending: {
        kind: 'ok',
        body: {
          ok: true,
          data: {
            items: [pendingItem({ decision_id: 'd1', symbol: '2330' })],
            timeout_minutes: 30,
          },
        },
      },
      confirm: {
        kind: 'ok',
        body: { ok: true, data: { decision_id: 'd1', fill: {}, qty: 100 } },
      },
    })

    renderPage()
    const btn = await screen.findByRole('button', { name: /確認 2330/ })
    fetchSpy.mockClear()
    await user.click(btn)

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.filter((c) =>
        String(c[0]).includes('/api/admin/confirm-gate/confirm'),
      )
      expect(calls.length).toBe(1)
    })
    const call = fetchSpy.mock.calls.find((c) =>
      String(c[0]).includes('/api/admin/confirm-gate/confirm'),
    )!
    const init = call[1] as RequestInit
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      decision_id: 'd1',
      user: 'mark',
    })
  })
})

// ===========================================================================
// 7.5 — hotkeys
// ===========================================================================

describe('Hotkeys', () => {
  it('focused pending card + Y → POST confirm', async () => {
    const fetchSpy = setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: { ok: true, data: { items: [], asof_iso: '...', count: 0 } },
      },
      pending: {
        kind: 'ok',
        body: {
          ok: true,
          data: {
            items: [pendingItem({ decision_id: 'd1', symbol: '2330' })],
            timeout_minutes: 30,
          },
        },
      },
      confirm: {
        kind: 'ok',
        body: { ok: true, data: { decision_id: 'd1', fill: {}, qty: 100 } },
      },
    })

    renderPage()
    await screen.findByText('2330')
    fetchSpy.mockClear()

    const card = document.querySelector(
      '[data-pending-card][data-decision-id="d1"]',
    ) as HTMLElement
    expect(card).not.toBeNull()
    card.focus()

    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'y' }))
    })

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.filter((c) =>
        String(c[0]).includes('/api/admin/confirm-gate/confirm'),
      )
      expect(calls.length).toBe(1)
    })
  })

  it('focused <input> + Y → no confirm fired', async () => {
    const fetchSpy = setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: { ok: true, data: { items: [], asof_iso: '...', count: 0 } },
      },
      pending: {
        kind: 'ok',
        body: {
          ok: true,
          data: {
            items: [pendingItem({ decision_id: 'd1', symbol: '2330' })],
            timeout_minutes: 30,
          },
        },
      },
    })

    renderPage()
    await screen.findByText('2330')
    fetchSpy.mockClear()

    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()

    act(() => {
      input.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'y', bubbles: true }),
      )
    })

    await new Promise((r) => setTimeout(r, 0))
    const confirmCalls = fetchSpy.mock.calls.filter((c) =>
      String(c[0]).includes('/api/admin/confirm-gate/confirm'),
    )
    expect(confirmCalls.length).toBe(0)
    document.body.removeChild(input)
  })

  it('Cmd+Shift+E → confirm() prompt → POST sweep-expired', async () => {
    const fetchSpy = setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: { ok: true, data: { items: [], asof_iso: '...', count: 0 } },
      },
      pending: {
        kind: 'ok',
        body: { ok: true, data: { items: [], timeout_minutes: 30 } },
      },
      sweep: {
        kind: 'ok',
        body: {
          ok: true,
          data: {
            swept_decision_ids: [],
            swept_count: 0,
            timeout_minutes: 30,
          },
        },
      },
    })

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderPage()
    await screen.findByText('模擬交易')
    fetchSpy.mockClear()

    act(() => {
      window.dispatchEvent(
        new KeyboardEvent('keydown', {
          key: 'e',
          metaKey: true,
          shiftKey: true,
        }),
      )
    })

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.filter((c) =>
        String(c[0]).includes('/api/admin/confirm-gate/sweep-expired'),
      )
      expect(calls.length).toBe(1)
    })
    expect(confirmSpy).toHaveBeenCalled()
  })
})

// ===========================================================================
// 7.6 — Sweep button confirm true / false
// ===========================================================================

describe('Sweep button', () => {
  it('confirm() → true → POST sweep-expired', async () => {
    const user = userEvent.setup()
    const fetchSpy = setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: { ok: true, data: { items: [], asof_iso: '...', count: 0 } },
      },
      pending: {
        kind: 'ok',
        body: { ok: true, data: { items: [], timeout_minutes: 30 } },
      },
      sweep: {
        kind: 'ok',
        body: {
          ok: true,
          data: {
            swept_decision_ids: [],
            swept_count: 0,
            timeout_minutes: 30,
          },
        },
      },
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderPage()
    fetchSpy.mockClear()
    await user.click(
      await screen.findByRole('button', { name: /全部 sweep 過期/ }),
    )

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.filter((c) =>
        String(c[0]).includes('/api/admin/confirm-gate/sweep-expired'),
      )
      expect(calls.length).toBe(1)
    })
  })

  it('confirm() → false → no request', async () => {
    const user = userEvent.setup()
    const fetchSpy = setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: { ok: true, data: { items: [], asof_iso: '...', count: 0 } },
      },
      pending: {
        kind: 'ok',
        body: { ok: true, data: { items: [], timeout_minutes: 30 } },
      },
    })
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    renderPage()
    fetchSpy.mockClear()
    await user.click(
      await screen.findByRole('button', { name: /全部 sweep 過期/ }),
    )

    await new Promise((r) => setTimeout(r, 0))
    const sweepCalls = fetchSpy.mock.calls.filter((c) =>
      String(c[0]).includes('/api/admin/confirm-gate/sweep-expired'),
    )
    expect(sweepCalls.length).toBe(0)
  })
})

// ===========================================================================
// 7.7 — Open positions mini
// ===========================================================================

describe('Open positions mini', () => {
  it('0 items → empty 目前無開倉', async () => {
    setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: { ok: true, data: { items: [], asof_iso: '...', count: 0 } },
      },
      pending: {
        kind: 'ok',
        body: { ok: true, data: { items: [], timeout_minutes: 30 } },
      },
    })

    renderPage()
    expect(await screen.findByText('目前無開倉')).toBeInTheDocument()
  })

  it('3 items → 3 rows, no overflow link', async () => {
    setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: {
          ok: true,
          data: {
            items: [
              positionItem({ decision_id: 'p1', symbol: 'AAA' }),
              positionItem({ decision_id: 'p2', symbol: 'BBB' }),
              positionItem({ decision_id: 'p3', symbol: 'CCC' }),
            ],
            asof_iso: '...',
            count: 3,
          },
        },
      },
      pending: {
        kind: 'ok',
        body: { ok: true, data: { items: [], timeout_minutes: 30 } },
      },
    })

    renderPage()
    expect(await screen.findByText('AAA')).toBeInTheDocument()
    expect(screen.getByText('BBB')).toBeInTheDocument()
    expect(screen.getByText('CCC')).toBeInTheDocument()
    expect(screen.queryByText(/詳細看 \/paper\/positions/)).toBeNull()
  })

  it('7 items → only 5 rows + overflow link to /paper/positions', async () => {
    setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: {
          ok: true,
          data: {
            items: Array.from({ length: 7 }).map((_, i) =>
              positionItem({
                decision_id: `p${i}`,
                symbol: `S${i}`,
              }),
            ),
            asof_iso: '...',
            count: 7,
          },
        },
      },
      pending: {
        kind: 'ok',
        body: { ok: true, data: { items: [], timeout_minutes: 30 } },
      },
    })

    renderPage()
    await screen.findByText('S0')
    expect(screen.getByText('S0')).toBeInTheDocument()
    expect(screen.getByText('S4')).toBeInTheDocument()
    expect(screen.queryByText('S5')).toBeNull()
    expect(screen.queryByText('S6')).toBeNull()

    const link = screen.getByRole('link', {
      name: /詳細看 \/paper\/positions/,
    })
    expect(link.getAttribute('href')).toMatch(/\/paper\/positions$/)
  })
})

// ===========================================================================
// 7.8 — Live Feed filtering
// ===========================================================================

describe('Live Feed', () => {
  function baseFetch() {
    setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: { ok: true, data: { items: [], asof_iso: '...', count: 0 } },
      },
      pending: {
        kind: 'ok',
        body: { ok: true, data: { items: [], timeout_minutes: 30 } },
      },
    })
  }

  it('empty store → renders 等待事件中…', async () => {
    baseFetch()
    renderPage()
    expect(await screen.findByText('等待事件中…')).toBeInTheDocument()
  })

  it('5 mixed events → only 3 whitelisted render', async () => {
    baseFetch()
    renderPage()
    await screen.findByText('等待事件中…')

    const ts = '2026-05-08T13:00:00+08:00'
    act(() => {
      const push = useLiveFeedStore.getState().pushEvent
      push({
        event_type: 'awaiting_confirm',
        timestamp: ts,
        payload: { symbol: 'A' },
      })
      push({
        event_type: 'order_sent',
        timestamp: ts,
        payload: { symbol: 'B' },
      })
      push({
        event_type: 'foo_bar',
        timestamp: ts,
        payload: { symbol: 'C' },
      })
      push({
        event_type: 'baz_qux',
        timestamp: ts,
        payload: { symbol: 'D' },
      })
      push({
        event_type: 'journal_written',
        timestamp: ts,
        payload: { symbol: 'E' },
      })
    })

    await waitFor(() => {
      expect(screen.getAllByText('awaiting_confirm').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('order_sent')).toBeInTheDocument()
    expect(screen.getByText('journal_written')).toBeInTheDocument()
    expect(screen.queryByText('foo_bar')).toBeNull()
    expect(screen.queryByText('baz_qux')).toBeNull()
  })

  it('12 awaiting_confirm → renders only 8', async () => {
    baseFetch()
    const { container } = renderPage()
    await screen.findByText('等待事件中…')

    act(() => {
      const push = useLiveFeedStore.getState().pushEvent
      for (let i = 0; i < 12; i++) {
        push({
          event_type: 'awaiting_confirm',
          timestamp: `2026-05-08T13:00:0${i % 10}+08:00`,
          payload: { symbol: `S${i}` },
        })
      }
    })

    await waitFor(() => {
      const lis = container.querySelectorAll('ul > li')
      expect(lis.length).toBe(8)
    })
  })
})

// ===========================================================================
// 7.9 — SSE invalidate
// ===========================================================================

describe('SSE invalidate', () => {
  it('push awaiting_confirm → triggers refetch on stats/positions/pending', async () => {
    const fetchSpy = setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: { ok: true, data: { items: [], asof_iso: '...', count: 0 } },
      },
      pending: {
        kind: 'ok',
        body: { ok: true, data: { items: [], timeout_minutes: 30 } },
      },
    })

    renderPage()
    await screen.findByText('等待事件中…')
    await new Promise((r) => setTimeout(r, 30))

    const initialStats = fetchSpy.mock.calls.filter((c) =>
      String(c[0]).includes('/api/admin/stats/today'),
    ).length
    const initialPositions = fetchSpy.mock.calls.filter((c) =>
      String(c[0]).includes('/api/admin/positions/open'),
    ).length
    const initialPending = fetchSpy.mock.calls.filter((c) =>
      String(c[0]).includes('/api/admin/confirm-gate/pending'),
    ).length

    act(() => {
      useLiveFeedStore.getState().pushEvent({
        event_type: 'awaiting_confirm',
        timestamp: '2026-05-08T13:00:00+08:00',
        payload: { symbol: '2330' },
      })
    })

    await waitFor(() => {
      const stats = fetchSpy.mock.calls.filter((c) =>
        String(c[0]).includes('/api/admin/stats/today'),
      ).length
      const positions = fetchSpy.mock.calls.filter((c) =>
        String(c[0]).includes('/api/admin/positions/open'),
      ).length
      const pending = fetchSpy.mock.calls.filter((c) =>
        String(c[0]).includes('/api/admin/confirm-gate/pending'),
      ).length
      expect(stats).toBeGreaterThan(initialStats)
      expect(positions).toBeGreaterThan(initialPositions)
      expect(pending).toBeGreaterThan(initialPending)
    })
  })

  it('push unrelated event → no refetch', async () => {
    const fetchSpy = setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: { ok: true, data: { items: [], asof_iso: '...', count: 0 } },
      },
      pending: {
        kind: 'ok',
        body: { ok: true, data: { items: [], timeout_minutes: 30 } },
      },
    })

    renderPage()
    await screen.findByText('等待事件中…')
    await new Promise((r) => setTimeout(r, 50))
    fetchSpy.mockClear()

    act(() => {
      useLiveFeedStore.getState().pushEvent({
        event_type: 'foo_bar',
        timestamp: '2026-05-08T13:00:00+08:00',
        payload: { symbol: '—' },
      })
    })

    await new Promise((r) => setTimeout(r, 50))
    const adminCalls = fetchSpy.mock.calls.filter((c) =>
      String(c[0]).includes('/api/admin/'),
    )
    expect(adminCalls.length).toBe(0)
  })
})

// ===========================================================================
// CG-B2 — reject reason dialog
// ===========================================================================

describe('Reject dialog', () => {
  it('clicking ✗ 拒絕 opens dialog; submitting POSTs the entered reason', async () => {
    const user = userEvent.setup()
    const fetchSpy = setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: { ok: true, data: { items: [], asof_iso: '...', count: 0 } },
      },
      pending: {
        kind: 'ok',
        body: {
          ok: true,
          data: {
            items: [pendingItem({ decision_id: 'd1', symbol: '2330' })],
            timeout_minutes: 30,
          },
        },
      },
      reject: {
        kind: 'ok',
        body: { ok: true, data: { decision_id: 'd1', reject_row_id: 1 } },
      },
    })

    renderPage()
    await user.click(await screen.findByRole('button', { name: /拒絕 2330/ }))

    const textarea = await screen.findByLabelText('拒絕原因')
    await user.type(textarea, '前年被套過')
    fetchSpy.mockClear()
    await user.click(screen.getByRole('button', { name: '確認拒絕' }))

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.filter((c) =>
        String(c[0]).includes('/api/admin/confirm-gate/reject'),
      )
      expect(calls.length).toBe(1)
    })
    const call = fetchSpy.mock.calls.find((c) =>
      String(c[0]).includes('/api/admin/confirm-gate/reject'),
    )!
    const init = call[1] as RequestInit
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      decision_id: 'd1',
      user: 'mark',
      reason: '前年被套過',
    })
  })

  it('確認拒絕 is disabled when reason is empty', async () => {
    const user = userEvent.setup()
    setupFetch({
      stats: { kind: 'ok', body: { ok: true, data: STATS_OK } },
      positions: {
        kind: 'ok',
        body: { ok: true, data: { items: [], asof_iso: '...', count: 0 } },
      },
      pending: {
        kind: 'ok',
        body: {
          ok: true,
          data: {
            items: [pendingItem({ decision_id: 'd1', symbol: '2330' })],
            timeout_minutes: 30,
          },
        },
      },
    })

    renderPage()
    await user.click(await screen.findByRole('button', { name: /拒絕 2330/ }))
    const submitBtn = await screen.findByRole('button', { name: '確認拒絕' })
    expect(submitBtn).toBeDisabled()
  })
})
