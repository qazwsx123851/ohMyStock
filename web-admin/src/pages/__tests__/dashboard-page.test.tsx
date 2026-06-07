import * as React from 'react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DashboardPage } from '../DashboardPage'
import { useAuthStore, useLiveFeedStore } from '@/stores'

// Mock the SSE hook to a no-op so we can drive events via the store directly
// without spinning up a real EventSource (which jsdom does not support).
vi.mock('@/hooks/useAdminEvents', () => ({ useAdminEvents: () => {} }))

type StatsData = {
  realized_pnl_twd: number
  open_positions: number
  pending_confirms: number
  llm_cost_usd: number
  monthly_breaker: { tripped: boolean; month_pnl_pct: number }
  cost: { used_usd: number; budget_usd: number; pct: number }
}

const DEFAULT_STATS: StatsData = {
  realized_pnl_twd: 12345,
  open_positions: 4,
  pending_confirms: 2,
  llm_cost_usd: 0.83,
  monthly_breaker: { tripped: false, month_pnl_pct: -1.2 },
  cost: { used_usd: 40, budget_usd: 100, pct: 40 },
}

// Mutable per-test stats payload. Reset to a copy of DEFAULT in beforeEach.
let statsData: StatsData = { ...DEFAULT_STATS }

function renderWithQuery(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  useAuthStore.getState().setToken('test-token')
  useLiveFeedStore.getState().clear()
  statsData = { ...DEFAULT_STATS }
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : (input as Request).url
    if (url.includes('/api/admin/stats/today')) {
      return new Response(JSON.stringify({ ok: true, data: statsData }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    return new Response(
      JSON.stringify({
        ok: false,
        error: { code: 'unhandled_in_test', message: url },
      }),
      { status: 404 },
    )
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('DashboardPage', () => {
  it('renders signed +12,345 with --up direction for positive realised P&L', async () => {
    renderWithQuery(<DashboardPage />)
    const el = await screen.findByText('+12,345')
    const row = el.closest('[data-direction]')
    expect(row).not.toBeNull()
    expect(row!.getAttribute('data-direction')).toBe('up')
    expect(row!.className).toMatch(/text-up/)
    // ArrowUp svg present alongside text — color-and-glyph dual encoding
    expect(row!.querySelector('svg')).not.toBeNull()
  })

  it('LiveFeed shows a confirm_gate.confirmed event pushed via SSE store', async () => {
    renderWithQuery(<DashboardPage />)
    // Wait for stats to settle so the page is fully painted
    await screen.findByText('+12,345')
    useLiveFeedStore.getState().pushEvent({
      event_type: 'confirm_gate.confirmed',
      timestamp: new Date().toISOString(),
      payload: { symbol: '2454' },
    })
    await waitFor(() => {
      expect(screen.getByText('confirm_gate.confirmed')).toBeInTheDocument()
    })
    // The companion symbol cell renders the payload symbol
    expect(screen.getByText('2454')).toBeInTheDocument()
  })
})

describe('MonthlyBreakerBanner', () => {
  it('shows the red banner when monthly_breaker.tripped is true', async () => {
    statsData = { ...DEFAULT_STATS, monthly_breaker: { tripped: true, month_pnl_pct: -9 } }
    renderWithQuery(<DashboardPage />)
    expect(await screen.findByText(/月度熔斷已觸發/)).toBeInTheDocument()
    expect(screen.getByText(/禁止新進場/)).toBeInTheDocument()
  })

  it('hides the banner when tripped is false', async () => {
    statsData = { ...DEFAULT_STATS, monthly_breaker: { tripped: false, month_pnl_pct: -1 } }
    renderWithQuery(<DashboardPage />)
    await screen.findByText('+12,345')
    expect(screen.queryByText(/月度熔斷已觸發/)).not.toBeInTheDocument()
  })
})

describe('CostBar', () => {
  it('turns orange when cost.pct >= 80', async () => {
    statsData = { ...DEFAULT_STATS, cost: { used_usd: 85, budget_usd: 100, pct: 85 } }
    renderWithQuery(<DashboardPage />)
    const bar = await screen.findByRole('progressbar')
    await waitFor(() => expect(bar.getAttribute('data-warn')).toBe('true'))
    expect(bar.className).toMatch(/bg-orange-500/)
  })

  it('stays normal color when cost.pct < 80', async () => {
    statsData = { ...DEFAULT_STATS, cost: { used_usd: 40, budget_usd: 100, pct: 40 } }
    renderWithQuery(<DashboardPage />)
    const bar = await screen.findByRole('progressbar')
    // wait until the loaded value is shown, then assert color stayed normal
    await screen.findByText(/40\.00 \/ 100\.00 USD/)
    expect(bar.getAttribute('data-warn')).toBe('false')
    expect(bar.className).not.toMatch(/bg-orange-500/)
  })
})
