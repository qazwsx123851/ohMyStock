import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider, createMemoryRouter } from 'react-router'
import * as stubs from '@/pages/stubs'
import { MarketPage } from '@/pages/MarketPage'
import { MarketSymbolPage } from '@/pages/MarketSymbolPage'
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
  it('stubs.tsx no longer exports MarketPage / MarketSymbolPage', () => {
    expect(Object.keys(stubs)).not.toContain('MarketPage')
    expect(Object.keys(stubs)).not.toContain('MarketSymbolPage')
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
})
