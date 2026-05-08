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
import { BacktestPage } from '../BacktestPage'
import { useAuthStore } from '@/stores'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const STRATEGIES = [{ name: 'sma_cross', description: 'SMA crossover' }]

const HISTORY = [
  {
    id: 'a1b2c3d4e5f60718293a4b5c6d7e8f90',
    strategy: 'sma_cross',
    period_from: '2024-01-01',
    period_to: '2024-12-31',
    status: 'completed',
    elapsed_ms: 200,
    created_at: '2026-05-08T10:00:00+08:00',
    annual_return_pct: 0.182,
    sharpe: 1.42,
    max_drawdown_pct: -0.083,
    win_rate_pct: 0.54,
  },
  {
    id: 'failed-1234567890abcdef1234567890abcd',
    strategy: 'sma_cross',
    period_from: '2024-07-01',
    period_to: '2024-12-31',
    status: 'failed',
    elapsed_ms: 5,
    created_at: '2026-05-07T10:00:00+08:00',
    annual_return_pct: null,
    sharpe: null,
    max_drawdown_pct: null,
    win_rate_pct: null,
  },
]

let fetchMock: Mock

function buildFetch(behavior: {
  history?: typeof HISTORY
  runError?: { code: string; message: string; status?: number }
}) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : (input as Request).url
    if (url.includes('/api/admin/backtest/strategies')) {
      return jsonResponse({ ok: true, data: { strategies: STRATEGIES } })
    }
    if (url.includes('/api/admin/backtest/jobs')) {
      const items = behavior.history ?? []
      return jsonResponse({
        ok: true,
        data: { items, count: items.length },
      })
    }
    if (url.includes('/api/admin/backtest/run')) {
      if (init?.method !== 'POST') {
        return jsonResponse(
          { ok: false, error: { code: 'method', message: 'method' } },
          405,
        )
      }
      if (behavior.runError) {
        return jsonResponse(
          {
            ok: false,
            error: {
              code: behavior.runError.code,
              message: behavior.runError.message,
            },
          },
          behavior.runError.status ?? 400,
        )
      }
      return jsonResponse({
        ok: true,
        data: { job_id: 'new1', status: 'completed', elapsed_ms: 200 },
      })
    }
    return jsonResponse(
      { ok: false, error: { code: 'unhandled', message: url } },
      404,
    )
  })
}

beforeEach(() => {
  useAuthStore.getState().setToken('test-token-aaaaaaaaaaaaaaaaaaaaaaaa')
  fetchMock = buildFetch({ history: HISTORY })
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

function renderPage(initialPath = '/backtest') {
  return render(
    <QueryClientProvider client={makeQc()}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/backtest" element={<BacktestPage />} />
          <Route
            path="/backtest/:jobId"
            element={<div data-testid="job-page" />}
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
  it('renders the filter form (no <ComingSoon/>)', async () => {
    renderPage()
    expect(screen.queryByText('建置中')).toBeNull()
    expect(
      await screen.findByRole('form', { name: /backtest filter form/i }),
    ).toBeInTheDocument()
  })

  it('exposes strategy select, chip input, two date inputs, initial capital input, 跑回測 + 清空 buttons', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText('strategy')).toBeInTheDocument(),
    )
    expect(screen.getByLabelText('custom symbols input')).toBeInTheDocument()
    expect(screen.getByLabelText('period from')).toBeInTheDocument()
    expect(screen.getByLabelText('period to')).toBeInTheDocument()
    const cap = screen.getByLabelText('initial capital') as HTMLInputElement
    expect(cap.value).toBe('1000000')
    expect(screen.getByRole('button', { name: /跑回測/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /清空/ })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Submit
// ---------------------------------------------------------------------------

describe('Run backtest', () => {
  it('clicking 跑回測 POSTs the right input', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText('strategy')).toBeInTheDocument(),
    )
    const symInput = screen.getByLabelText('custom symbols input')
    await user.click(symInput)
    await user.keyboard('2330{Enter}')

    await user.click(screen.getByRole('button', { name: /跑回測/ }))

    await waitFor(() => {
      const calls = fetchMock.mock.calls.filter((c) =>
        String(c[0]).includes('/api/admin/backtest/run'),
      )
      expect(calls.length).toBeGreaterThanOrEqual(1)
    })
    const callArgs = fetchMock.mock.calls.find((c) =>
      String(c[0]).includes('/api/admin/backtest/run'),
    )!
    const body = JSON.parse(String((callArgs[1] as RequestInit).body))
    expect(body).toMatchObject({
      strategy: 'sma_cross',
      symbols: ['2330'],
      initial_capital: 1000000,
    })
    expect(typeof body.period_from).toBe('string')
    expect(typeof body.period_to).toBe('string')
  })

  it('Cmd+Enter inside the form fires runBacktest once', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText('strategy')).toBeInTheDocument(),
    )
    const symInput = screen.getByLabelText('custom symbols input')
    await user.click(symInput)
    await user.keyboard('2330{Enter}')
    const strategy = screen.getByLabelText('strategy') as HTMLSelectElement
    strategy.focus()
    await user.keyboard('{Meta>}{Enter}{/Meta}')
    await waitFor(() => {
      const calls = fetchMock.mock.calls.filter((c) =>
        String(c[0]).includes('/api/admin/backtest/run'),
      )
      expect(calls.length).toBe(1)
    })
  })

  it('「清空」resets chips and dates', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText('strategy')).toBeInTheDocument(),
    )
    const sym = screen.getByLabelText('custom symbols input')
    await user.click(sym)
    await user.keyboard('2330{Enter}')
    expect(screen.getByText('2330')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /清空/ }))
    expect(screen.queryByText('2330')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// History table
// ---------------------------------------------------------------------------

describe('History table', () => {
  it('renders 8 column headers + 2 data rows', async () => {
    renderPage()
    for (const h of [
      'JobId',
      '策略',
      '期間',
      '年化',
      'Sharpe',
      'MaxDD',
      '狀態',
      '建立時間',
    ]) {
      expect(
        await screen.findByRole('columnheader', { name: h }),
      ).toBeInTheDocument()
    }
    await waitFor(() => {
      expect(screen.getAllByRole('row').length).toBeGreaterThanOrEqual(3)
    })
  })

  it('completed row uses text-up + ArrowUp on 年化 / Sharpe and text-down + glyph on MaxDD', async () => {
    renderPage()
    const completedCell = await screen.findByText(/a1b2c3d4/)
    const row = completedCell.closest('tr')!
    expect(row.querySelector('.text-up')).not.toBeNull()
    expect(row.querySelector('.text-up svg')).not.toBeNull()
    expect(row.querySelector('.text-down')).not.toBeNull()
    expect(row.querySelector('.text-down svg')).not.toBeNull()
  })

  it('failed row shows — and no text-up / text-down', async () => {
    renderPage()
    const failedCell = await screen.findByText(/failed-1/)
    const row = failedCell.closest('tr')!
    const cells = Array.from(row.querySelectorAll('td')).slice(3, 6)
    for (const c of cells) {
      expect(c.textContent).toContain('—')
      expect(c.querySelector('.text-up')).toBeNull()
      expect(c.querySelector('.text-down')).toBeNull()
    }
    expect(row.textContent).toMatch(/失敗/)
  })

  it('clicking a row navigates to /backtest/<id>', async () => {
    const user = userEvent.setup()
    renderPage()
    const completedCell = await screen.findByText(/a1b2c3d4/)
    const row = completedCell.closest('tr')!
    await user.click(row)
    expect(await screen.findByTestId('job-page')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Three states
// ---------------------------------------------------------------------------

describe('Three states', () => {
  it('loading: 啟動中… while runBacktest is pending', async () => {
    const user = userEvent.setup()
    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : (input as Request).url
      if (url.includes('/run')) {
        return new Promise<Response>(() => undefined)
      }
      if (url.includes('/strategies')) {
        return jsonResponse({ ok: true, data: { strategies: STRATEGIES } })
      }
      return jsonResponse({ ok: true, data: { items: [], count: 0 } })
    })
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
    renderPage()
    const sym = await screen.findByLabelText('custom symbols input')
    await user.click(sym)
    await user.keyboard('2330{Enter}')
    await user.click(screen.getByRole('button', { name: /跑回測/ }))
    expect(await screen.findByText('啟動中…')).toBeInTheDocument()
  })

  it('empty: shows 尚未跑過回測 + hint when history is empty', async () => {
    fetchMock = buildFetch({ history: [] })
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
    renderPage()
    expect(await screen.findByText('尚未跑過回測')).toBeInTheDocument()
    expect(screen.getByText(/填上方表單/)).toBeInTheDocument()
  })

  it('error: shows red banner + 重試 button + chip preserved', async () => {
    const user = userEvent.setup()
    fetchMock = buildFetch({
      history: [],
      runError: { code: 'missing_bars', message: 'no bars for 9999' },
    })
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
    renderPage()
    const sym = await screen.findByLabelText('custom symbols input')
    await user.click(sym)
    await user.keyboard('9999{Enter}')
    await user.click(screen.getByRole('button', { name: /跑回測/ }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重試/ })).toBeInTheDocument()
    expect(screen.getByText('9999')).toBeInTheDocument()
  })

  it('run success → history is invalidated and refetched', async () => {
    const user = userEvent.setup()
    let called = 0
    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : (input as Request).url
      if (url.includes('/strategies')) {
        return jsonResponse({ ok: true, data: { strategies: STRATEGIES } })
      }
      if (url.includes('/api/admin/backtest/jobs')) {
        called += 1
        if (called === 1) {
          return jsonResponse({ ok: true, data: { items: [], count: 0 } })
        }
        return jsonResponse({
          ok: true,
          data: { items: HISTORY.slice(0, 1), count: 1 },
        })
      }
      if (url.includes('/api/admin/backtest/run')) {
        if (init?.method !== 'POST') {
          return jsonResponse(
            { ok: false, error: { code: 'm', message: 'm' } },
            405,
          )
        }
        return jsonResponse({
          ok: true,
          data: { job_id: 'new1', status: 'completed', elapsed_ms: 50 },
        })
      }
      return jsonResponse(
        { ok: false, error: { code: 'u', message: url } },
        404,
      )
    })
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)

    renderPage()
    expect(await screen.findByText('尚未跑過回測')).toBeInTheDocument()
    const sym = screen.getByLabelText('custom symbols input')
    await user.click(sym)
    await user.keyboard('2330{Enter}')
    await user.click(screen.getByRole('button', { name: /跑回測/ }))
    expect(await screen.findByText(/a1b2c3d4/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Chip input
// ---------------------------------------------------------------------------

describe('Chip input', () => {
  it('Enter pushes a chip and clears the textbox', async () => {
    const user = userEvent.setup()
    renderPage()
    const input = await screen.findByLabelText('custom symbols input')
    await user.click(input)
    await user.keyboard('2330{Enter}')
    expect(screen.getByText('2330')).toBeInTheDocument()
    expect((input as HTMLInputElement).value).toBe('')
  })

  it('Backspace on empty input removes the last chip', async () => {
    const user = userEvent.setup()
    renderPage()
    const input = await screen.findByLabelText('custom symbols input')
    await user.click(input)
    await user.keyboard('2330{Enter}2454{Enter}')
    expect(screen.getByText('2454')).toBeInTheDocument()
    await user.keyboard('{Backspace}')
    expect(screen.queryByText('2454')).toBeNull()
    expect(screen.getByText('2330')).toBeInTheDocument()
  })
})
