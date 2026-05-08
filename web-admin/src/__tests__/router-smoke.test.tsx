import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider, createMemoryRouter } from 'react-router'
import * as stubs from '@/pages/stubs'
import { MarketPage } from '@/pages/MarketPage'
import { MarketSymbolPage } from '@/pages/MarketSymbolPage'
import { BacktestPage } from '@/pages/BacktestPage'
import { BacktestJobPage } from '@/pages/BacktestJobPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { useAuthStore } from '@/stores'

vi.mock('@/hooks/useAdminEvents', () => ({ useAdminEvents: () => {} }))

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  useAuthStore.getState().setToken('test-token-aaaaaaaaaaaaaaaaaaaaaaaa')
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    (async (input: RequestInfo | URL) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.toString()
            : (input as Request).url
      if (url.includes('/api/admin/market/symbols/2330')) {
        return jsonResponse({
          ok: true,
          data: {
            symbol: '2330',
            quote: {
              price: 1025,
              change: 12,
              change_pct: 0.012,
              volume: 18432000,
              asof: '2026-05-08',
            },
            bars_daily: [],
            rs: null,
            sepa: null,
            institutional: [],
            recent_patterns: [],
          },
        })
      }
      if (url.includes('/api/admin/backtest/strategies')) {
        return jsonResponse({
          ok: true,
          data: { strategies: [{ name: 'sma_cross', description: 'SMA' }] },
        })
      }
      if (url.includes('/api/admin/backtest/jobs/')) {
        return jsonResponse({
          ok: true,
          data: {
            id: 'a1b2c3d4e5f60718293a4b5c6d7e8f90',
            strategy: 'sma_cross',
            period_from: '2024-01-01',
            period_to: '2024-12-31',
            custom_symbols: ['2330'],
            initial_capital: 1_000_000,
            status: 'completed',
            elapsed_ms: 200,
            created_at: '2026-05-08T10:00:00+08:00',
            metrics: null,
            equity_curve: [],
            drawdown: [],
            trades: [],
            error: null,
          },
        })
      }
      if (url.includes('/api/admin/backtest/jobs')) {
        return jsonResponse({
          ok: true,
          data: { items: [], count: 0 },
        })
      }
      return jsonResponse(
        { ok: false, error: { code: 'unhandled', message: url } },
        404,
      )
    }) as never,
  )
})

afterEach(() => {
  vi.restoreAllMocks()
})

function makeQc() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
}

describe('Router smoke: /market and /market/:symbol render real pages', () => {
  it('stubs.tsx no longer exports MarketPage / MarketSymbolPage / BacktestPage / BacktestJobPage / SettingsPage', () => {
    expect(Object.keys(stubs)).not.toContain('MarketPage')
    expect(Object.keys(stubs)).not.toContain('MarketSymbolPage')
    expect(Object.keys(stubs)).not.toContain('BacktestPage')
    expect(Object.keys(stubs)).not.toContain('BacktestJobPage')
    expect(Object.keys(stubs)).not.toContain('SettingsPage')
  })

  it('/market renders MarketPage (filter form, not <ComingSoon>)', async () => {
    const router = createMemoryRouter(
      [{ path: '/market', element: <MarketPage /> }],
      { initialEntries: ['/market'] },
    )
    render(
      <QueryClientProvider client={makeQc()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    await waitFor(() => {
      expect(
        screen.getByRole('form', { name: /screener filter form/i }),
      ).toBeInTheDocument()
    })
    expect(screen.queryByText('建置中')).toBeNull()
  })

  it('/market/2330 renders MarketSymbolPage (price header, not <ComingSoon>)', async () => {
    const router = createMemoryRouter(
      [{ path: '/market/:symbol', element: <MarketSymbolPage /> }],
      { initialEntries: ['/market/2330'] },
    )
    render(
      <QueryClientProvider client={makeQc()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    await screen.findByText(/1,025/)
    expect(screen.queryByText('建置中')).toBeNull()
  })

  it('/backtest renders BacktestPage (filter form, not <ComingSoon>)', async () => {
    const router = createMemoryRouter(
      [{ path: '/backtest', element: <BacktestPage /> }],
      { initialEntries: ['/backtest'] },
    )
    render(
      <QueryClientProvider client={makeQc()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    await waitFor(() => {
      expect(
        screen.getByRole('form', { name: /backtest filter form/i }),
      ).toBeInTheDocument()
    })
    expect(screen.queryByText('建置中')).toBeNull()
  })

  it('/backtest/<id> renders BacktestJobPage (header, not <ComingSoon>)', async () => {
    const router = createMemoryRouter(
      [{ path: '/backtest/:jobId', element: <BacktestJobPage /> }],
      { initialEntries: ['/backtest/a1b2c3d4e5f60718293a4b5c6d7e8f90'] },
    )
    render(
      <QueryClientProvider client={makeQc()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    await screen.findByText(/sma_cross/)
    expect(screen.queryByText('建置中')).toBeNull()
  })

  it('/settings renders SettingsPage (4 cards, not <ComingSoon>)', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (async () =>
        jsonResponse({
          ok: true,
          data: {
            api_keys: { anthropic: false, finmind: false, shioaji: false },
            theme: { mode: 'system' },
            safety: { auto_execute: false, broker: 'shioaji-sim' },
            breakers: {
              min_confidence: 0.7,
              daily_limit: 5,
              max_notional_pct: 0.25,
              max_sizing_deviation: 0.3,
              loss_lockout_hours: 24,
              loss_pct_threshold: -0.05,
              account_equity_twd: 1_000_000,
            },
          },
        })) as never,
    )
    const router = createMemoryRouter(
      [{ path: '/settings', element: <SettingsPage /> }],
      { initialEntries: ['/settings'] },
    )
    render(
      <QueryClientProvider client={makeQc()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    await screen.findByText('API keys')
    expect(screen.queryByText('建置中')).toBeNull()
  })
})
