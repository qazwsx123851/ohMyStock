import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
  type Mock,
} from 'vitest'
import {
  ApiError,
  getBacktestJob,
  getMarketSymbol,
  getSettings,
  listBacktestJobs,
  listStrategies,
  runBacktest,
  runScreener,
} from '@/lib/api'
import { useAuthStore } from '@/stores'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

let fetchMock: Mock

beforeEach(() => {
  useAuthStore.getState().setToken('test-token-aaaaaaaaaaaaaaaaaaaaaaaa')
  fetchMock = vi.fn(async () =>
    jsonResponse({ ok: true, data: { stub: true } }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
})

afterEach(() => {
  vi.restoreAllMocks()
})

function urlOf(call: Parameters<typeof fetch>): string {
  const input = call[0]
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.toString()
  return (input as Request).url
}

describe('getMarketSymbol', () => {
  it('hits /api/admin/market/symbols/{symbol} with days query when days option provided', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ok: true,
        data: {
          symbol: '2330',
          quote: {
            price: 1059,
            change: 1,
            change_pct: 0.001,
            volume: 1,
            asof: '2026-05-08',
          },
          bars_daily: [],
          rs: null,
          sepa: null,
          institutional: [],
          recent_patterns: [],
        },
      }),
    )

    const result = await getMarketSymbol('2330', { days: 90 })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toContain('/api/admin/market/symbols/2330')
    expect(url).toContain('days=90')
    expect(result.symbol).toBe('2330')
  })

  it('omits the days query string when no options are passed', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ok: true,
        data: {
          symbol: '2330',
          quote: {
            price: 0,
            change: null,
            change_pct: null,
            volume: 0,
            asof: '2026-05-08',
          },
          bars_daily: [],
          rs: null,
          sepa: null,
          institutional: [],
          recent_patterns: [],
        },
      }),
    )

    await getMarketSymbol('2330')

    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toContain('/api/admin/market/symbols/2330')
    expect(url).not.toContain('days=')
  })
})

describe('runScreener', () => {
  it('POSTs the input body to /api/admin/screener/run', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ok: true,
        data: { run_id: 'r1', hits: [] },
      }),
    )

    const input = {
      universe: 'tw50',
      filters: [{ sepa: true }, { rs_min: 80 }],
    }
    await runScreener(input)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [first, init] = fetchMock.mock.calls[0] as [
      RequestInfo,
      RequestInit | undefined,
    ]
    const url = typeof first === 'string' ? first : (first as Request).url
    expect(url).toContain('/api/admin/screener/run')
    expect(init?.method).toBe('POST')
    expect(typeof init?.body).toBe('string')
    expect(JSON.parse(String(init?.body))).toEqual(input)
  })
})

describe('runBacktest', () => {
  it('POSTs JSON body to /api/admin/backtest/run', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ok: true,
        data: { job_id: 'abc', status: 'completed', elapsed_ms: 100 },
      }),
    )
    const input = {
      strategy: 'sma_cross',
      symbols: ['2330'],
      period_from: '2024-01-01',
      period_to: '2024-12-31',
    }
    await runBacktest(input)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [first, init] = fetchMock.mock.calls[0] as [
      RequestInfo,
      RequestInit | undefined,
    ]
    const url = typeof first === 'string' ? first : (first as Request).url
    expect(url).toContain('/api/admin/backtest/run')
    expect(init?.method).toBe('POST')
    const decoded = JSON.parse(String(init?.body))
    expect(decoded).toMatchObject({
      strategy: 'sma_cross',
      symbols: ['2330'],
      period_from: '2024-01-01',
      period_to: '2024-12-31',
    })
  })
})

describe('listBacktestJobs', () => {
  it('appends ?limit=50 when limit is provided', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ ok: true, data: { items: [], count: 0 } }),
    )
    await listBacktestJobs(50)
    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toContain('/api/admin/backtest/jobs')
    expect(url).toContain('limit=50')
  })

  it('omits the limit query string when no argument is passed', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ ok: true, data: { items: [], count: 0 } }),
    )
    await listBacktestJobs()
    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toContain('/api/admin/backtest/jobs')
    expect(url).not.toContain('limit=')
  })
})

describe('getBacktestJob', () => {
  it('hits /api/admin/backtest/jobs/{jobId}', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ok: true,
        data: {
          id: 'a1b2c3d4e5f60718293a4b5c6d7e8f90',
          strategy: 'sma_cross',
          period_from: '2024-01-01',
          period_to: '2024-12-31',
          custom_symbols: ['2330'],
          initial_capital: 1000000,
          status: 'completed',
          elapsed_ms: 200,
          created_at: '2026-05-08T10:00:00+08:00',
          metrics: null,
          equity_curve: [],
          drawdown: [],
          trades: [],
          error: null,
        },
      }),
    )
    await getBacktestJob('a1b2c3d4e5f60718293a4b5c6d7e8f90')
    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toContain(
      '/api/admin/backtest/jobs/a1b2c3d4e5f60718293a4b5c6d7e8f90',
    )
  })
})

describe('listStrategies', () => {
  it('hits /api/admin/backtest/strategies', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ok: true,
        data: { strategies: [{ name: 'sma_cross', description: 'SMA' }] },
      }),
    )
    await listStrategies()
    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toContain('/api/admin/backtest/strategies')
  })
})

describe('getSettings', () => {
  const HAPPY_PAYLOAD = {
    api_keys: { anthropic: true, finmind: false, shioaji: true },
    theme: { mode: 'system' as const },
    safety: { auto_execute: false, broker: 'shioaji-sim' as const },
    breakers: {
      min_confidence: 0.7,
      daily_limit: 5,
      max_notional_pct: 0.25,
      max_sizing_deviation: 0.3,
      loss_lockout_hours: 24,
      loss_pct_threshold: -0.05,
      account_equity_twd: 1_000_000,
    },
  }

  it('hits /api/admin/settings and resolves to data (not the envelope)', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ ok: true, data: HAPPY_PAYLOAD }),
    )
    const result = await getSettings()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toContain('/api/admin/settings')
    expect(result).toEqual(HAPPY_PAYLOAD)
    expect(result.api_keys.anthropic).toBe(true)
  })

  it('rejects with ApiError when envelope.ok is false, propagating error.code', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ok: false,
        error: { code: 'internal_error', message: 'boom' },
      }),
    )
    await expect(getSettings()).rejects.toBeInstanceOf(ApiError)
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ok: false,
        error: { code: 'internal_error', message: 'boom' },
      }),
    )
    try {
      await getSettings()
    } catch (e) {
      expect((e as ApiError).code).toBe('internal_error')
    }
  })

  it('triggers logout on 401', async () => {
    useAuthStore.getState().setToken('test-token-aaaaaaaaaaaaaaaaaaaaaaaa')
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { ok: false, error: { code: 'auth_invalid', message: 'no' } },
        401,
      ),
    )
    await expect(getSettings()).rejects.toBeInstanceOf(ApiError)
    expect(useAuthStore.getState().token).toBeNull()
  })
})
