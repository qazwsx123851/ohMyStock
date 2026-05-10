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
  getSkill,
  listBacktestJobs,
  listMemory,
  listSkills,
  listStrategies,
  runBacktest,
  runScreener,
  searchMemory,
  type MemoryRowsResponse,
  type Skill,
  type SkillDetail,
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

describe('listSkills', () => {
  it('hits /api/admin/skills and unwraps items', async () => {
    const items: Skill[] = [
      {
        name: 'alpha',
        description: 'alpha desc',
        category: 'data',
        body_preview: '# Body',
        body_truncated: false,
        cited_specs: ['spec-one'],
      },
    ]
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ ok: true, data: { items } }),
    )

    const result = await listSkills()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toBe('/api/admin/skills')
    expect(result.items).toEqual(items)
  })
})

describe('getSkill', () => {
  it('hits /api/admin/skills/{name} and returns SkillDetail', async () => {
    const detail: SkillDetail = {
      name: 'market-data',
      description: 'fetch bars',
      category: 'data',
      body: '# full body',
      cited_specs: ['market-data-cache'],
    }
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true, data: detail }))

    const result = await getSkill('market-data')

    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toBe('/api/admin/skills/market-data')
    expect(result).toEqual(detail)
  })

  it('encodes the path component (space → %20)', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ok: true,
        data: {
          name: 'foo bar',
          description: '',
          category: 'data',
          body: '',
          cited_specs: [],
        },
      }),
    )

    await getSkill('foo bar')

    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toBe('/api/admin/skills/foo%20bar')
  })

  it('throws ApiError with code "not_found" on 404 envelope', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { ok: false, error: { code: 'not_found', message: 'skill not found: x' } },
        404,
      ),
    )

    await expect(getSkill('x')).rejects.toMatchObject({
      code: 'not_found',
      httpStatus: 404,
    })
  })
})

const EMPTY_MEMORY: MemoryRowsResponse = {
  items: [],
  total: 0,
  limit: 50,
  offset: 0,
  has_more: false,
}

describe('listMemory', () => {
  it('hits /api/admin/memory/rows with no query string when params are empty', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true, data: EMPTY_MEMORY }))

    await listMemory({})

    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toBe('/api/admin/memory/rows')
  })

  it('builds URL with kind, tag, limit, offset all set', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true, data: EMPTY_MEMORY }))

    await listMemory({ kind: 'lesson', tag: 'vcp', limit: 20, offset: 40 })

    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toContain('/api/admin/memory/rows?')
    expect(url).toContain('kind=lesson')
    expect(url).toContain('tag=vcp')
    expect(url).toContain('limit=20')
    expect(url).toContain('offset=40')
  })

  it('omits empty-string tag from the query string', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true, data: EMPTY_MEMORY }))

    await listMemory({ kind: 'note', tag: '' })

    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).not.toContain('tag=')
    expect(url).toContain('kind=note')
  })

  it('returns the unwrapped MemoryRowsResponse', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true, data: EMPTY_MEMORY }))

    const result = await listMemory({})
    expect(result).toEqual(EMPTY_MEMORY)
  })

  it('throws ApiError on 400 invalid_input envelope', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { ok: false, error: { code: 'invalid_input', message: 'kind invalid' } },
        400,
      ),
    )

    await expect(listMemory({ kind: 'note' })).rejects.toBeInstanceOf(ApiError)
  })
})

describe('searchMemory', () => {
  it('encodes q correctly (CJK + spaces)', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true, data: EMPTY_MEMORY }))

    await searchMemory({ q: 'foo bar 中文' })

    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toBe('/api/admin/memory/search?q=foo%20bar%20%E4%B8%AD%E6%96%87')
  })

  it('always passes q through even when empty (server rejects)', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { ok: false, error: { code: 'invalid_input', message: 'empty q' } },
        400,
      ),
    )

    // The wrapper must not throw client-side — the server returns 400 and
    // react-query's error path picks it up.
    await expect(searchMemory({ q: '' })).rejects.toBeInstanceOf(ApiError)

    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toBe('/api/admin/memory/search?q=')
  })

  it('appends limit and offset when provided', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true, data: EMPTY_MEMORY }))

    await searchMemory({ q: 'breakout', limit: 30, offset: 60 })

    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toBe('/api/admin/memory/search?q=breakout&limit=30&offset=60')
  })

  it('throws ApiError with code "invalid_query" on FTS5 syntax error', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { ok: false, error: { code: 'invalid_query', message: 'FTS5 query syntax error' } },
        400,
      ),
    )

    await expect(searchMemory({ q: 'foo OR' })).rejects.toMatchObject({
      code: 'invalid_query',
      httpStatus: 400,
    })
  })
})
