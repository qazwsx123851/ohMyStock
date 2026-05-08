import * as React from 'react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DashboardPage } from '../DashboardPage'
import { useAuthStore, useLiveFeedStore } from '@/stores'

// Mock the SSE hook to a no-op so we can drive events via the store directly
// without spinning up a real EventSource (which jsdom does not support).
vi.mock('@/hooks/useAdminEvents', () => ({ useAdminEvents: () => {} }))

const STATS_OK_BODY = {
  ok: true,
  data: {
    realized_pnl_twd: 12345,
    open_positions: 4,
    pending_confirms: 2,
    llm_cost_usd: 0.83,
  },
}

function renderWithQuery(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  useAuthStore.getState().setToken('test-token')
  useLiveFeedStore.getState().clear()
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : (input as Request).url
    if (url.includes('/api/admin/stats/today')) {
      return new Response(JSON.stringify(STATS_OK_BODY), {
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
