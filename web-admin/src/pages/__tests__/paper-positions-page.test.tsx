import * as React from 'react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PaperPositionsPage } from '../PaperPositionsPage'
import { useAuthStore } from '@/stores'
import type { OpenPosition } from '@/lib/api'

const POSITIONS_OK: OpenPosition[] = [
  {
    symbol: '2330',
    side: 'long',
    qty: 100,
    entry_price: 1000.5,
    mark_price: 1025,
    unrealized_pnl_twd: 2450,
    unrealized_pnl_pct: 2.5,
    stop_loss: 970,
    t1_target: 1080,
    hold_days: 12,
    time_stop_date: '2026-05-20',
    entry_reason: 'SEPA breakout + RS≥80',
    entry_at: '2026-04-22T09:30:00+08:00',
  },
  {
    symbol: '6505',
    side: 'short',
    qty: 500,
    entry_price: 33.5,
    mark_price: 32.8,
    unrealized_pnl_twd: -350,
    unrealized_pnl_pct: -2.1,
    stop_loss: 31,
    t1_target: 35.5,
    hold_days: 8,
    time_stop_date: '2026-05-15',
    entry_reason: 'breakdown retest',
    entry_at: '2026-04-30T10:00:00+08:00',
  },
]

function renderWithQuery(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  useAuthStore.getState().setToken('test-token')
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('PaperPositionsPage', () => {
  it('loading: renders ≥3 Skeleton elements while fetch is pending', () => {
    let resolveFetch!: (r: Response) => void
    const pending = new Promise<Response>((res) => {
      resolveFetch = res
    })
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => pending)

    const { container } = renderWithQuery(<PaperPositionsPage />)
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThanOrEqual(3)

    resolveFetch(jsonResponse({ ok: true, data: [] }))
  })

  it('resolved: renders both rows with --up/--down dual-encoding (color + arrow svg)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        ok: true,
        data: { items: POSITIONS_OK, asof_iso: '2026-05-10T09:30:00+08:00', count: POSITIONS_OK.length },
      }),
    )

    const { container } = renderWithQuery(<PaperPositionsPage />)
    await screen.findByText('2330')
    expect(screen.getByText('6505')).toBeInTheDocument()

    const upCells = container.querySelectorAll('[data-direction="up"]')
    const downCells = container.querySelectorAll('[data-direction="down"]')
    expect(upCells.length).toBeGreaterThanOrEqual(2)
    expect(downCells.length).toBeGreaterThanOrEqual(2)

    let upHasUpClass = false
    let upHasArrowSvg = false
    upCells.forEach((el) => {
      if (el.className.includes('text-up')) upHasUpClass = true
      if (el.querySelector('svg')) upHasArrowSvg = true
    })
    expect(upHasUpClass).toBe(true)
    expect(upHasArrowSvg).toBe(true)

    let downHasDownClass = false
    let downHasArrowSvg = false
    downCells.forEach((el) => {
      if (el.className.includes('text-down')) downHasDownClass = true
      if (el.querySelector('svg')) downHasArrowSvg = true
    })
    expect(downHasDownClass).toBe(true)
    expect(downHasArrowSvg).toBe(true)
  })

  it('detail panel toggles when a row is clicked', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        ok: true,
        data: { items: POSITIONS_OK, asof_iso: '2026-05-10T09:30:00+08:00', count: POSITIONS_OK.length },
      }),
    )

    const { container } = renderWithQuery(<PaperPositionsPage />)
    await screen.findByText('2330')

    expect(
      container.querySelector('[data-testid="positions-detail-panel"]'),
    ).toBeNull()

    const dataRows = container.querySelectorAll('tbody tr')
    fireEvent.click(dataRows[0])
    const panel = container.querySelector(
      '[data-testid="positions-detail-panel"]',
    )
    expect(panel).not.toBeNull()
    expect(panel!.textContent).toContain('SEPA breakout + RS≥80')
  })

  it('empty: renders 目前無開倉 + ListOrdered icon when API returns []', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        ok: true,
        data: { items: [], asof_iso: '2026-05-10T09:30:00+08:00', count: 0 },
      }),
    )

    const { container } = renderWithQuery(<PaperPositionsPage />)
    await screen.findByText('目前無開倉')
    expect(container.querySelector('svg')).not.toBeNull()
  })

  it('error: renders --destructive panel with retry button on ApiError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(
        { ok: false, error: { code: 'db_unavailable', message: 'sqlite locked' } },
        500,
      ),
    )

    renderWithQuery(<PaperPositionsPage />)
    await waitFor(() => {
      expect(screen.getByText('載入失敗')).toBeInTheDocument()
    })
    expect(screen.getByText('sqlite locked')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重試/ })).toBeInTheDocument()
  })
})
