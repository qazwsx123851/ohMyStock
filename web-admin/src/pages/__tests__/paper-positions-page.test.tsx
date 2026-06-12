import * as React from 'react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PaperPositionsPage } from '../PaperPositionsPage'
import { useAuthStore } from '@/stores'
import type { OpenPosition } from '@/lib/api'

const POSITIONS_OK: OpenPosition[] = [
  {
    decision_id: 'd-1',
    symbol: '2330',
    sector: '半導體',
    entry_price: 600,
    qty_lots: 2,
    entry_ts: '2026-04-22T09:30:00+08:00',
    hold_days: 12,
    stop_loss: 570,
    t1_target: 660,
    time_stop_date: '2026-05-20',
  },
  {
    decision_id: 'd-2',
    symbol: '0050',
    sector: 'ETF',
    entry_price: 180,
    qty_lots: 1,
    entry_ts: '2026-04-30T10:00:00+08:00',
    hold_days: 8,
    stop_loss: null,
    t1_target: null,
    time_stop_date: null,
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

  it('resolved: renders rows, long-only 多 cells with up dual-encoding, — for null levels', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        ok: true,
        data: { items: POSITIONS_OK, asof_iso: '2026-05-10T09:30:00+08:00', count: POSITIONS_OK.length },
      }),
    )

    const { container } = renderWithQuery(<PaperPositionsPage />)
    await screen.findByText('2330')
    expect(screen.getByText('0050')).toBeInTheDocument()

    // v0 long-only：每列方向 cell 都是 多 + up 雙重編碼（色 + 箭頭 svg）。
    const upCells = container.querySelectorAll('[data-direction="up"]')
    expect(upCells.length).toBeGreaterThanOrEqual(2)
    let upHasUpClass = false
    let upHasArrowSvg = false
    upCells.forEach((el) => {
      if (el.className.includes('text-up')) upHasUpClass = true
      if (el.querySelector('svg')) upHasArrowSvg = true
    })
    expect(upHasUpClass).toBe(true)
    expect(upHasArrowSvg).toBe(true)

    // 0050 缺 stop_loss / t1_target → 該列以 — 呈現。
    const row0050 = screen.getByText('0050').closest('tr')!
    expect(row0050.textContent).toContain('—')
  })

  it('detail panel toggles when a row is clicked, 距離% 帶方向編碼', async () => {
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
    // 2330：停損 570 vs entry 600 → -5%（down）；T1 660 → +10%（up）。
    expect(panel!.textContent).toContain('半導體')
    expect(panel!.querySelector('[data-direction="down"]')).not.toBeNull()
    expect(panel!.querySelector('[data-direction="up"]')).not.toBeNull()
    expect(panel!.textContent).toContain('-5')
    expect(panel!.textContent).toContain('+10')
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
