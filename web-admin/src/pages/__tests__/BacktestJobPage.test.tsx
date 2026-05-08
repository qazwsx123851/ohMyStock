import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
  type Mock,
} from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router'
import { BacktestJobPage } from '../BacktestJobPage'
import { useAuthStore } from '@/stores'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const COMPLETED_DETAIL = {
  id: 'a1b2c3d4e5f60718293a4b5c6d7e8f90',
  strategy: 'sma_cross',
  period_from: '2024-01-01',
  period_to: '2024-12-31',
  custom_symbols: ['2330'],
  initial_capital: 1_000_000,
  status: 'completed',
  elapsed_ms: 200,
  created_at: '2026-05-08T10:00:00+08:00',
  metrics: {
    annual_return_pct: 0.182,
    sharpe: 1.42,
    max_drawdown_pct: -0.083,
    win_rate_pct: 0.542,
  },
  equity_curve: Array.from({ length: 200 }).map((_, i) => ({
    date: `2024-01-${String((i % 28) + 1).padStart(2, '0')}`,
    equity: 1_000_000 + i * 1000,
  })),
  drawdown: Array.from({ length: 200 }).map((_, i) => ({
    date: `2024-01-${String((i % 28) + 1).padStart(2, '0')}`,
    dd: 0,
  })),
  trades: [
    {
      entry_date: '2024-01-15',
      exit_date: '2024-01-22',
      symbol: '2330',
      side: 'long',
      qty: 1,
      entry_price: 600,
      exit_price: 612,
      pnl_twd: 12000,
      hold_days: 7,
      pattern: 'SEPA breakout',
    },
    {
      entry_date: '2024-02-03',
      exit_date: '2024-02-04',
      symbol: '2454',
      side: 'long',
      qty: 1,
      entry_price: 1200,
      exit_price: 1180,
      pnl_twd: -20000,
      hold_days: 1,
      pattern: 'failed entry',
    },
  ],
  error: null,
}

const FAILED_DETAIL = {
  ...COMPLETED_DETAIL,
  id: 'failed-1234567890abcdef1234567890abcd',
  status: 'failed',
  metrics: null,
  equity_curve: [],
  drawdown: [],
  trades: [],
  error: { code: 'INVALID_INPUT', message: 'warmup not satisfied' },
}

let fetchMock: Mock

function buildFetch(behavior: {
  detail?: typeof COMPLETED_DETAIL | typeof FAILED_DETAIL
  status?: number
  errorCode?: string
}) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : (input as Request).url
    if (url.includes('/api/admin/backtest/jobs/')) {
      if (behavior.errorCode) {
        return jsonResponse(
          {
            ok: false,
            error: { code: behavior.errorCode, message: behavior.errorCode },
          },
          behavior.status ?? 500,
        )
      }
      return jsonResponse({ ok: true, data: behavior.detail })
    }
    return jsonResponse(
      { ok: false, error: { code: 'unhandled', message: url } },
      404,
    )
  })
}

beforeEach(() => {
  useAuthStore.getState().setToken('test-token-aaaaaaaaaaaaaaaaaaaaaaaa')
  fetchMock = buildFetch({ detail: COMPLETED_DETAIL })
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
})

afterEach(() => {
  vi.restoreAllMocks()
})

function makeQc() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
}

function renderPage(jobId = COMPLETED_DETAIL.id) {
  return render(
    <QueryClientProvider client={makeQc()}>
      <MemoryRouter initialEntries={[`/backtest/${jobId}`]}>
        <Routes>
          <Route path="/backtest/:jobId" element={<BacktestJobPage />} />
          <Route
            path="/backtest"
            element={<div data-testid="backtest-list" />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ---------------------------------------------------------------------------
// Routing & header
// ---------------------------------------------------------------------------

describe('Routing & header', () => {
  it('renders header (no <ComingSoon/>)', async () => {
    renderPage()
    await screen.findByText(/sma_cross/)
    expect(screen.queryByText('建置中')).toBeNull()
  })

  it('issues GET /api/admin/backtest/jobs/<id> with Authorization header', async () => {
    renderPage()
    await waitFor(() => {
      const calls = fetchMock.mock.calls.filter((c) =>
        String(c[0]).includes(`/api/admin/backtest/jobs/${COMPLETED_DETAIL.id}`),
      )
      expect(calls.length).toBeGreaterThanOrEqual(1)
    })
    const call = fetchMock.mock.calls.find((c) =>
      String(c[0]).includes(`/api/admin/backtest/jobs/${COMPLETED_DETAIL.id}`),
    )!
    const init = call[1] as RequestInit | undefined
    const headers = (init?.headers ?? {}) as Record<string, string>
    expect(headers.Authorization).toMatch(/^Bearer /)
  })

  it('shows back link, jobId truncation, strategy + period', async () => {
    renderPage()
    expect(await screen.findByText(/sma_cross/)).toBeInTheDocument()
    expect(screen.getByText(/2024-01-01/)).toBeInTheDocument()
    expect(screen.getByText(/2024-12-31/)).toBeInTheDocument()
    expect(screen.getByText(/a1b2c3d4/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /\/backtest/ })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// KPI cards
// ---------------------------------------------------------------------------

describe('KPI cards', () => {
  it('shows 4 KPI cards with correct directions and glyphs', async () => {
    const { container } = renderPage()
    await screen.findByText(/sma_cross/)

    const annualCard = screen.getByText('年化').closest('div')!
      .parentElement as HTMLElement
    expect(annualCard.querySelector('.text-up')).not.toBeNull()
    expect(annualCard.querySelector('.text-up svg')).not.toBeNull()

    const sharpeCard = screen.getByText('Sharpe').closest('div')!
      .parentElement as HTMLElement
    expect(sharpeCard.querySelector('.text-up')).not.toBeNull()

    const maxddCard = screen.getByText('MaxDD').closest('div')!
      .parentElement as HTMLElement
    expect(maxddCard.querySelector('.text-down')).not.toBeNull()
    expect(maxddCard.querySelector('.text-down svg')).not.toBeNull()

    const winCard = screen.getByText('勝率').closest('div')!
      .parentElement as HTMLElement
    expect(winCard.querySelector('.text-up')).toBeNull()
    expect(winCard.querySelector('.text-down')).toBeNull()

    expect(container).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Chart placeholder cards
// ---------------------------------------------------------------------------

describe('Chart placeholders', () => {
  it('renders two labelled placeholder cards (no chart lib)', async () => {
    renderPage()
    expect(await screen.findByText(/資金曲線（圖庫待定）/)).toBeInTheDocument()
    expect(screen.getByText(/回撤曲線（圖庫待定）/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Trades table
// ---------------------------------------------------------------------------

describe('Trades table', () => {
  it('shows 7 column headers + 2 rows; P&L direction colour + glyph', async () => {
    renderPage()
    for (const h of [
      '進場日',
      '出場日',
      'Symbol',
      '方向',
      'P&L',
      '持倉',
      'Pattern',
    ]) {
      expect(
        await screen.findByRole('columnheader', { name: h }),
      ).toBeInTheDocument()
    }
    const winRow = (await screen.findByText('2330')).closest('tr')!
    expect(winRow.querySelector('.text-up')).not.toBeNull()
    expect(winRow.querySelector('.text-up svg')).not.toBeNull()
    const lossRow = screen.getByText('2454').closest('tr')!
    expect(lossRow.querySelector('.text-down')).not.toBeNull()
    expect(lossRow.querySelector('.text-down svg')).not.toBeNull()
  })

  it('empty trades → 本 job 區間無交易訊號', async () => {
    fetchMock = buildFetch({
      detail: { ...COMPLETED_DETAIL, trades: [] },
    })
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
    renderPage()
    expect(
      await screen.findByText('本 job 區間無交易訊號'),
    ).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// States
// ---------------------------------------------------------------------------

describe('States', () => {
  it('loading: skeletons before fetch resolves', async () => {
    fetchMock = vi.fn(
      () => new Promise<Response>(() => undefined) as never,
    )
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
    const { container } = renderPage()
    await waitFor(() => {
      expect(
        container.querySelectorAll('.animate-pulse').length,
      ).toBeGreaterThanOrEqual(3)
    })
  })

  it('404 not_found → 該 job 不存在 + back link', async () => {
    fetchMock = buildFetch({ errorCode: 'not_found', status: 404 })
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
    renderPage()
    expect(await screen.findByText(/該 job 不存在/)).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /返回 \/backtest/ }),
    ).toBeInTheDocument()
  })

  it('generic error → red banner + 重試 button', async () => {
    const user = userEvent.setup()
    fetchMock = buildFetch({ errorCode: 'internal_error', status: 500 })
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
    renderPage()
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    const retry = screen.getByRole('button', { name: /重試/ })
    expect(retry).toBeInTheDocument()
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ ok: true, data: COMPLETED_DETAIL }),
    )
    await user.click(retry)
  })

  it('failed job: KPIs show — , chart areas show 無資料 — job 失敗, banner with error message', async () => {
    fetchMock = buildFetch({ detail: FAILED_DETAIL })
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
    renderPage(FAILED_DETAIL.id)
    await screen.findByText(/sma_cross/)
    const annualCard = screen.getByText('年化').closest('div')!
      .parentElement as HTMLElement
    expect(annualCard.textContent).toContain('—')
    expect(
      screen.getAllByText(/無資料 — job 失敗/).length,
    ).toBeGreaterThanOrEqual(2)
    expect(screen.getByRole('alert').textContent).toMatch(
      /warmup not satisfied/,
    )
  })
})
