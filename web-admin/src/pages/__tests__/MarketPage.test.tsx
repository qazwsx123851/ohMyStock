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
import { MemoryRouter, Routes, Route } from 'react-router'
import { MarketPage } from '../MarketPage'
import { useAuthStore, useLiveFeedStore } from '@/stores'

// Mock SSE hook so jsdom doesn't open EventSource. Tests drive the live-feed
// store directly through pushEvent() in the live-update tests.
vi.mock('@/hooks/useAdminEvents', () => ({ useAdminEvents: () => {} }))

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const HITS = [
  {
    symbol: '2330',
    name: '台積電',
    price: 1025,
    change_pct: 0.012,
    pattern: 'SEPA breakout',
    score: 0.86,
  },
  {
    symbol: '6505',
    name: '台塑化',
    price: 33.5,
    change_pct: -0.003,
    pattern: 'failed entry',
    score: 0.41,
  },
]

let fetchMock: Mock

beforeEach(() => {
  useAuthStore.getState().setToken('test-token-aaaaaaaaaaaaaaaaaaaaaaaa')
  useLiveFeedStore.getState().clear()
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : (input as Request).url
    if (url.includes('/api/admin/screener/run')) {
      return jsonResponse({
        ok: true,
        data: { run_id: 'r48', hits: HITS, elapsed_ms: 1800 },
      })
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
  useLiveFeedStore.getState().clear()
})

function makeQc() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
}

function renderPage(initialPath = '/market') {
  const qc = makeQc()
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/market" element={<MarketPage />} />
          <Route
            path="/market/:symbol"
            element={<div data-testid="symbol-page" />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ---------------------------------------------------------------------------
// Routing & form structure
// ---------------------------------------------------------------------------

describe('Routing & form structure', () => {
  it('renders the filter form (no <ComingSoon/>)', () => {
    renderPage()
    expect(screen.queryByText('建置中')).toBeNull()
    expect(
      screen.getByRole('form', { name: /screener filter form/i }),
    ).toBeInTheDocument()
  })

  it('exposes the universe select, chip input, 4 filter checkboxes, and a date input', () => {
    renderPage()
    expect(screen.getByLabelText('SEPA')).toBeInTheDocument()
    expect(screen.getByLabelText('RS≥80')).toBeInTheDocument()
    expect(screen.getByLabelText('法人連續買超')).toBeInTheDocument()
    expect(screen.getByLabelText('三角收斂')).toBeInTheDocument()
    expect(screen.getByLabelText('universe')).toBeInTheDocument()
    expect(screen.getByLabelText('custom symbols input')).toBeInTheDocument()
    expect(screen.getByLabelText('asof date')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Submit
// ---------------------------------------------------------------------------

describe('Run screener', () => {
  it('clicking 跑 screener with filters POSTs the right input', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByLabelText('SEPA'))
    await user.click(screen.getByLabelText('RS≥80'))
    await user.click(screen.getByRole('button', { name: /跑 screener/ }))
    await waitFor(() => {
      const calls = fetchMock.mock.calls.filter((c) =>
        String(c[0]).includes('/api/admin/screener/run'),
      )
      expect(calls.length).toBeGreaterThanOrEqual(1)
    })
    const callArgs = fetchMock.mock.calls.find((c) =>
      String(c[0]).includes('/api/admin/screener/run'),
    )!
    const body = JSON.parse(String((callArgs[1] as RequestInit).body))
    expect(body.universe).toBe('tw50')
    expect(body.filters).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ sepa: true }),
        expect.objectContaining({ rs_min: 80 }),
      ]),
    )
  })

  it('Cmd+Enter inside the form fires runScreener once', async () => {
    const user = userEvent.setup()
    renderPage()
    const universe = screen.getByLabelText('universe') as HTMLSelectElement
    universe.focus()
    await user.keyboard('{Meta>}{Enter}{/Meta}')
    await waitFor(() => {
      const calls = fetchMock.mock.calls.filter((c) =>
        String(c[0]).includes('/api/admin/screener/run'),
      )
      expect(calls.length).toBe(1)
    })
  })
})

// ---------------------------------------------------------------------------
// Result table
// ---------------------------------------------------------------------------

describe('Result table', () => {
  it('shows 6 column headers + 2 data rows after a successful run', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /跑 screener/ }))
    await screen.findByText('台積電')
    for (const h of ['Symbol', '名稱', '現價', '漲跌', 'Pattern', 'Score']) {
      expect(screen.getByRole('columnheader', { name: h })).toBeInTheDocument()
    }
    expect(screen.getAllByRole('row').length).toBeGreaterThanOrEqual(3)
  })

  it('「漲跌」cells use text-up + ArrowUp for >0 and text-down + ArrowDown for <0', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /跑 screener/ }))
    await screen.findByText('台積電')

    const row2330 = screen.getByText('2330').closest('tr')!
    expect(row2330.querySelector('.text-up')).not.toBeNull()
    expect(row2330.querySelector('.text-up svg')).not.toBeNull()

    const row6505 = screen.getByText('6505').closest('tr')!
    expect(row6505.querySelector('.text-down')).not.toBeNull()
    expect(row6505.querySelector('.text-down svg')).not.toBeNull()
  })

  it('Score column is bold for ≥0.7 and never coloured red/green', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /跑 screener/ }))
    await screen.findByText('台積電')

    const scoreCells = screen.getAllByTestId('score-cell')
    expect(scoreCells.length).toBe(2)
    const high = scoreCells.find((c) => c.textContent === '0.86')!
    const low = scoreCells.find((c) => c.textContent === '0.41')!
    expect(high.className).toContain('font-medium')
    expect(low.className).not.toContain('font-medium')
    for (const c of scoreCells) {
      expect(c.className).not.toContain('text-up')
      expect(c.className).not.toContain('text-down')
    }
  })

  it('clicking a result row navigates to /market/<symbol>', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /跑 screener/ }))
    await screen.findByText('台積電')

    const row2330 = screen.getByText('2330').closest('tr')!
    await user.click(row2330)
    expect(await screen.findByTestId('symbol-page')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Three states
// ---------------------------------------------------------------------------

describe('Three states', () => {
  it('loading: shows skeleton rows + 啟動中…', async () => {
    fetchMock.mockImplementationOnce(
      () => new Promise<Response>(() => undefined),
    )
    const user = userEvent.setup()
    const { container } = renderPage()
    await user.click(screen.getByRole('button', { name: /跑 screener/ }))
    await screen.findByText('啟動中…')
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThanOrEqual(3)
  })

  it('empty: shows 本次掃描無命中 + filter hint', async () => {
    fetchMock.mockReset()
    fetchMock.mockImplementation(async () =>
      jsonResponse({
        ok: true,
        data: { run_id: 'r0', hits: [], elapsed_ms: 50 },
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /跑 screener/ }))
    expect(await screen.findByText('本次掃描無命中')).toBeInTheDocument()
    expect(screen.getByText(/放寬 filter/)).toBeInTheDocument()
  })

  it('error: shows red banner + 重試 button; SEPA checkbox stays checked', async () => {
    fetchMock.mockReset()
    fetchMock.mockImplementation(async () =>
      jsonResponse(
        { ok: false, error: { code: 'screener_failed', message: 'timeout' } },
        500,
      ),
    )
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByLabelText('SEPA'))
    await user.click(screen.getByRole('button', { name: /跑 screener/ }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重試/ })).toBeInTheDocument()
    expect((screen.getByLabelText('SEPA') as HTMLInputElement).checked).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// SSE live update
// ---------------------------------------------------------------------------

describe('SSE live update', () => {
  it('pattern_detected SSE event prepends a row in the result table', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /跑 screener/ }))
    await screen.findByText('台積電')

    act(() => {
      useLiveFeedStore.getState().pushEvent({
        event_type: 'pattern_detected',
        timestamp: '2026-05-08T14:02:51+08:00',
        payload: {
          symbol: '2454',
          name: '聯發科',
          price: 1180,
          change_pct: 0.008,
          pattern: 'SEPA + RS=92',
          score: 0.82,
        },
      })
    })

    await screen.findByText('聯發科')
    const dataRows = screen.getAllByRole('row').slice(1)
    expect(dataRows.length).toBe(3)
    expect(dataRows[0].textContent).toContain('2454')
  })

  it('renders at most 5 live feed entries even if 8 are pushed', () => {
    renderPage()
    act(() => {
      const store = useLiveFeedStore.getState()
      for (let i = 0; i < 8; i++) {
        store.pushEvent({
          event_type: 'pattern_detected',
          timestamp: `2026-05-08T14:02:5${i}+08:00`,
          payload: { symbol: `1${i}`, pattern: 'SEPA breakout' },
        })
      }
    })
    const ul = document.querySelector('ul')!
    expect(ul.children.length).toBe(5)
  })
})

// ---------------------------------------------------------------------------
// Chip input keyboard
// ---------------------------------------------------------------------------

describe('Chip input', () => {
  it('Enter pushes a chip and clears the textbox', async () => {
    const user = userEvent.setup()
    renderPage()
    const input = screen.getByLabelText('custom symbols input')
    await user.click(input)
    await user.keyboard('1234{Enter}')
    expect(screen.getByText('1234')).toBeInTheDocument()
    expect((input as HTMLInputElement).value).toBe('')
  })

  it('Backspace on empty input removes the last chip', async () => {
    const user = userEvent.setup()
    renderPage()
    const input = screen.getByLabelText('custom symbols input')
    await user.click(input)
    await user.keyboard('1234{Enter}5678{Enter}')
    expect(screen.getByText('5678')).toBeInTheDocument()
    await user.keyboard('{Backspace}')
    expect(screen.queryByText('5678')).toBeNull()
    expect(screen.getByText('1234')).toBeInTheDocument()
  })
})
