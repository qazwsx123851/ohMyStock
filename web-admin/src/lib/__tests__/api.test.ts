import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
  type Mock,
} from 'vitest'
import { getMarketSymbol, runScreener } from '@/lib/api'
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
