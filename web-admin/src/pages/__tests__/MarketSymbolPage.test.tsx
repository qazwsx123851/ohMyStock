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
import { MemoryRouter, Routes, Route, useLocation } from 'react-router'
import { MarketSymbolPage } from '../MarketSymbolPage'
import { useAuthStore } from '@/stores'

vi.mock('@/hooks/useAdminEvents', () => ({ useAdminEvents: () => {} }))

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const HAPPY_DATA = {
  symbol: '2330',
  quote: {
    price: 1025,
    change: 12,
    change_pct: 0.012,
    volume: 18432000,
    asof: '2026-05-08',
  },
  bars_daily: Array.from({ length: 60 }).map((_, i) => ({
    date: `2026-05-${String((i % 28) + 1).padStart(2, '0')}`,
    open: 1000 + i,
    high: 1010 + i,
    low: 990 + i,
    close: 1000 + i,
    volume: 1_000_000,
  })),
  rs: { value: 92, asof: '2026-05-08' },
  sepa: { stage: 2, since: '2026-04-15' },
  institutional: [
    { date: '2026-05-04', foreign: 800, trust: -100, dealer: 30, total: 730 },
    { date: '2026-05-05', foreign: 900, trust: 50, dealer: 0, total: 950 },
    { date: '2026-05-06', foreign: 1000, trust: 100, dealer: 10, total: 1110 },
    { date: '2026-05-07', foreign: 1100, trust: 200, dealer: 20, total: 1320 },
    { date: '2026-05-08', foreign: 1200, trust: 300, dealer: -50, total: 1450 },
  ],
  recent_patterns: [
    {
      ts: '2026-04-22T13:30:00+08:00',
      pattern: 'SEPA breakout',
      score: 0.86,
      outcome: '+2.5% 持有中',
    },
    {
      ts: '2026-04-15T13:30:00+08:00',
      pattern: 'pullback',
      score: 0.62,
      outcome: '未進場',
    },
  ],
}

let fetchMock: Mock

beforeEach(() => {
  useAuthStore.getState().setToken('test-token-aaaaaaaaaaaaaaaaaaaaaaaa')
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : (input as Request).url
    if (url.includes('/api/admin/market/symbols/2330')) {
      return jsonResponse({ ok: true, data: HAPPY_DATA })
    }
    if (url.includes('/api/admin/market/symbols/9999')) {
      return jsonResponse(
        {
          ok: false,
          error: {
            code: 'market_symbol_not_found',
            message: 'no rows for 9999',
          },
        },
        404,
      )
    }
    if (url.includes('/api/admin/market/symbols/9998')) {
      return jsonResponse(
        { ok: false, error: { code: 'internal', message: 'db down' } },
        500,
      )
    }
    return jsonResponse(
      { ok: false, error: { code: 'unhandled', message: url } },
      404,
    )
  })
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

function LocationProbe() {
  const loc = useLocation()
  return (
    <span data-testid="location">
      {loc.pathname}
      {loc.search}
    </span>
  )
}

function renderAt(path: string) {
  const qc = makeQc()
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <LocationProbe />
        <Routes>
          <Route path="/market/:symbol" element={<MarketSymbolPage />} />
          <Route path="/market" element={<div data-testid="market-page" />} />
          <Route path="/audit" element={<div data-testid="audit-page" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ---------------------------------------------------------------------------
// Happy path
// ---------------------------------------------------------------------------

describe('Happy path', () => {
  it('issues GET against /api/admin/market/symbols/2330 with bearer auth', async () => {
    renderAt('/market/2330')
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((c) =>
          String(c[0]).includes('/api/admin/market/symbols/2330'),
        ),
      ).toBe(true)
    })
    const call = fetchMock.mock.calls.find((c) =>
      String(c[0]).includes('/api/admin/market/symbols/2330'),
    )!
    const headers = (call[1] as RequestInit)?.headers as
      | Record<string, string>
      | undefined
    expect(headers?.Authorization?.startsWith('Bearer ')).toBe(true)
  })

  it('renders header price 1,025 with text-up + ArrowUp + +1.20% + asof date', async () => {
    const { container } = renderAt('/market/2330')
    await screen.findByText(/1,025/)
    expect(screen.getAllByText(/2026-05-08/).length).toBeGreaterThan(0)
    const up = container.querySelector('[data-direction="up"]')
    expect(up).not.toBeNull()
    expect(up!.querySelector('svg')).not.toBeNull()
    expect(up!.textContent).toMatch(/1\.2%|1\.20%/)
  })

  it('change=0 → muted dash, no text-up / text-down', async () => {
    fetchMock.mockReset()
    fetchMock.mockImplementation(async () =>
      jsonResponse({
        ok: true,
        data: {
          ...HAPPY_DATA,
          quote: { ...HAPPY_DATA.quote, change: 0, change_pct: 0 },
        },
      }),
    )
    const { container } = renderAt('/market/2330')
    await screen.findByText(/1,025/)
    const neutral = container.querySelector('[data-direction="neutral"]')
    expect(neutral).not.toBeNull()
    expect(neutral!.textContent).toContain('—')
    expect(container.querySelector('[data-direction="up"]')).toBeNull()
    expect(container.querySelector('[data-direction="down"]')).toBeNull()
  })

  it('renders K-line placeholder Card with caption, no chart library import', async () => {
    renderAt('/market/2330')
    expect(
      await screen.findByText(/K 線圖（圖庫待定）/),
    ).toBeInTheDocument()
  })

  it('renders 3 KPI cards: RS 92 / Stage 2 / 連續買超', async () => {
    renderAt('/market/2330')
    await screen.findByText(/RS Rank/)
    expect(screen.getByText('92')).toBeInTheDocument()
    expect(screen.getByText('Stage 2')).toBeInTheDocument()
    expect(screen.getByText('連續買超')).toBeInTheDocument()
  })

  it('rs=null → RS card shows — and not the literal string null', async () => {
    fetchMock.mockReset()
    fetchMock.mockImplementation(async () =>
      jsonResponse({
        ok: true,
        data: { ...HAPPY_DATA, rs: null },
      }),
    )
    renderAt('/market/2330')
    await screen.findByText('RS Rank')
    const rsCard = screen.getByText('RS Rank').parentElement!
    expect(rsCard.textContent).not.toContain('null')
    expect(rsCard.textContent).toContain('—')
  })
})

// ---------------------------------------------------------------------------
// Tables
// ---------------------------------------------------------------------------

describe('Tables', () => {
  it('renders the institutional table 5 cols + 5 rows with red/green NumCells', async () => {
    renderAt('/market/2330')
    await screen.findByText('外資')
    const institutionalSection = screen
      .getByText(/三大法人/)
      .closest('section')!
    const headers = institutionalSection.querySelectorAll('thead th')
    const headerLabels = Array.from(headers).map((h) =>
      (h.textContent ?? '').trim(),
    )
    for (const h of ['日期', '外資', '投信', '自營商', '合計']) {
      expect(headerLabels).toContain(h)
    }
    const rows = institutionalSection.querySelectorAll('tbody tr')
    expect(rows.length).toBe(5)

    const lastRow = rows[rows.length - 1]
    const cells = lastRow.querySelectorAll('td')
    expect(cells[1].querySelector('.text-up')).not.toBeNull()
    expect(cells[1].querySelector('.text-up svg')).not.toBeNull()
    expect(cells[3].querySelector('.text-down')).not.toBeNull()
    expect(cells[3].querySelector('.text-down svg')).not.toBeNull()
  })

  it('institutional empty → renders 近 5 日無法人資料', async () => {
    fetchMock.mockReset()
    fetchMock.mockImplementation(async () =>
      jsonResponse({
        ok: true,
        data: { ...HAPPY_DATA, institutional: [] },
      }),
    )
    renderAt('/market/2330')
    expect(await screen.findByText('近 5 日無法人資料')).toBeInTheDocument()
  })

  it('renders the patterns table 4 cols + 2 rows with proper outcome colouring', async () => {
    renderAt('/market/2330')
    await screen.findByText('近期偵測 Pattern')
    const section = screen.getByText('近期偵測 Pattern').closest('section')!
    const headerLabels = Array.from(
      section.querySelectorAll('thead th'),
    ).map((h) => (h.textContent ?? '').trim())
    for (const h of ['日期', 'Pattern', 'Score', '結局']) {
      expect(headerLabels).toContain(h)
    }
    const rows = section.querySelectorAll('tbody tr')
    expect(rows.length).toBe(2)
    expect(rows[0].querySelector('.text-up')).not.toBeNull()
    expect(rows[0].querySelector('.text-up svg')).not.toBeNull()
    expect(rows[1].querySelector('.text-up')).toBeNull()
    expect(rows[1].querySelector('.text-down')).toBeNull()
  })

  it('patterns row click navigates to /audit?symbol=...&date_from=...', async () => {
    const user = userEvent.setup()
    renderAt('/market/2330')
    await screen.findByText('SEPA breakout')
    const section = screen.getByText('近期偵測 Pattern').closest('section')!
    const firstDataRow = section.querySelectorAll('tbody tr')[0]
    await user.click(firstDataRow)
    expect(await screen.findByTestId('audit-page')).toBeInTheDocument()
    const loc = screen.getByTestId('location').textContent ?? ''
    expect(loc).toContain('/audit')
    expect(loc).toContain('symbol=2330')
    expect(loc).toContain('date_from=2026-04-22')
  })
})

// ---------------------------------------------------------------------------
// Three states
// ---------------------------------------------------------------------------

describe('Three states', () => {
  it('loading: skeletons across header / chart / KPIs / tables', () => {
    fetchMock.mockReset()
    fetchMock.mockImplementation(
      () => new Promise<Response>(() => undefined),
    )
    const { container } = renderAt('/market/2330')
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThanOrEqual(5)
  })

  it('404 not_found: shows 該 symbol 無資料 + back link to /market', async () => {
    renderAt('/market/9999')
    expect(await screen.findByText('該 symbol 無資料')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /返回 \/market/ }),
    ).toBeInTheDocument()
  })

  it('500 error: shows red alert with retry button', async () => {
    renderAt('/market/9998')
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重試/ })).toBeInTheDocument()
    expect(screen.getByText(/載入 9998 失敗/)).toBeInTheDocument()
  })
})
