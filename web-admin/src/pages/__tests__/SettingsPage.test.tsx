import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
  type Mock,
} from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { SettingsPage } from '../SettingsPage'
import { useAuthStore } from '@/stores'

vi.mock('@/hooks/useAdminEvents', () => ({ useAdminEvents: () => {} }))

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const DEFAULT_PAYLOAD = {
  api_keys: { anthropic: false, finmind: false, shioaji: false },
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
  budget: {
    used_usd: 40,
    budget_usd: 100,
    remaining_usd: 60,
    model_mix: { opus: 0.5, sonnet: 0.3, haiku: 0.2 },
  },
}

const LIVE_PAYLOAD = {
  ...DEFAULT_PAYLOAD,
  api_keys: { anthropic: true, finmind: true, shioaji: true },
  safety: { auto_execute: true, broker: 'shioaji-sim' as const },
}

let fetchMock: Mock

function makeQc() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeQc()}>
      <MemoryRouter initialEntries={['/settings']}>
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useAuthStore.getState().setToken('test-token-aaaaaaaaaaaaaaaaaaaaaaaa')
  fetchMock = vi.fn(async () =>
    jsonResponse({ ok: true, data: DEFAULT_PAYLOAD }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

describe('SettingsPage loading state', () => {
  it('renders skeletons and no save buttons before fetch resolves', () => {
    fetchMock.mockImplementationOnce(
      () =>
        new Promise(() => {
          /* never resolves */
        }) as unknown as Promise<Response>,
    )
    const { container } = renderPage()
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]')
    expect(skeletons.length).toBeGreaterThanOrEqual(4)
    expect(screen.queryByText('儲存')).toBeNull()
    expect(screen.queryByText('啟用')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Default render (auto_execute=false)
// ---------------------------------------------------------------------------

describe('SettingsPage default render', () => {
  it('shows three "未設定" badges, warning border, AlertTriangle, and broker', async () => {
    const { container } = renderPage()
    await screen.findByText('API keys')

    const unsetBadges = screen.getAllByText('未設定')
    expect(unsetBadges).toHaveLength(3)

    const safetyCard = container.querySelector('[data-auto-execute="off"]')
    expect(safetyCard).not.toBeNull()
    expect(safetyCard!.className).toMatch(/border-warning/)
    const triangle = safetyCard!.querySelector(
      'svg.lucide-alert-triangle, svg.lucide-triangle-alert',
    )
    expect(triangle).not.toBeNull()
    expect(
      safetyCard!.querySelector(
        'svg.lucide-alert-circle, svg.lucide-circle-alert',
      ),
    ).toBeNull()

    expect(screen.getByText(/AUTO_EXECUTE 關閉/)).toBeInTheDocument()
    expect(screen.getByText(/shioaji-sim/)).toBeInTheDocument()
  })

  it('renders breakers default values (0.70, 1,000,000)', async () => {
    renderPage()
    await screen.findByText('Breakers')
    const minConf = screen.getByLabelText('信心下限') as HTMLInputElement
    expect(minConf.value).toBe('0.70')
    const equity = screen.getByLabelText('帳戶權益') as HTMLInputElement
    expect(equity.value).toBe('1,000,000')
  })

  it('every input/select on the page is disabled', async () => {
    const { container } = renderPage()
    await screen.findByText('Breakers')
    const inputs = container.querySelectorAll('input, select')
    expect(inputs.length).toBeGreaterThan(0)
    inputs.forEach((el) => {
      expect((el as HTMLInputElement | HTMLSelectElement).disabled).toBe(true)
    })
  })

  it('DOM never contains write-action strings', async () => {
    renderPage()
    await screen.findByText('Breakers')
    expect(screen.queryByText('儲存')).toBeNull()
    expect(screen.queryByText('啟用')).toBeNull()
    expect(screen.queryByText(/我已了解風險/)).toBeNull()
    expect(screen.queryByText(/^PUT$/)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// auto_execute=true
// ---------------------------------------------------------------------------

describe('SettingsPage with auto_execute=true', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    fetchMock = vi.fn(async () =>
      jsonResponse({ ok: true, data: LIVE_PAYLOAD }),
    )
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
  })

  it('renders destructive border, AlertCircle, and 已啟用 banner', async () => {
    const { container } = renderPage()
    await screen.findByText(/AUTO_EXECUTE 已啟用/)

    const safetyCard = container.querySelector('[data-auto-execute="on"]')
    expect(safetyCard).not.toBeNull()
    expect(safetyCard!.className).toMatch(/border-destructive/)
    const circle = safetyCard!.querySelector(
      'svg.lucide-alert-circle, svg.lucide-circle-alert',
    )
    expect(circle).not.toBeNull()
    expect(
      safetyCard!.querySelector(
        'svg.lucide-alert-triangle, svg.lucide-triangle-alert',
      ),
    ).toBeNull()
  })

  it('renders three "已設定" badges when all keys are set', async () => {
    renderPage()
    await screen.findByText('API keys')
    const setBadges = screen.getAllByText('已設定')
    expect(setBadges).toHaveLength(3)
  })
})

// ---------------------------------------------------------------------------
// Budget / model mix (ST-B2)
// ---------------------------------------------------------------------------

describe('SettingsPage budget block', () => {
  it('renders used / budget / remaining and model mix percentages', async () => {
    const { container } = renderPage()
    await screen.findByText('本月額度與模型分布')
    expect(screen.getByText('40.00')).toBeInTheDocument()
    expect(screen.getByText('60.00')).toBeInTheDocument()
    const opus = container.querySelector('[data-model="opus"]')
    expect(opus?.textContent).toMatch(/50%/)
    const haiku = container.querySelector('[data-model="haiku"]')
    expect(haiku?.textContent).toMatch(/20%/)
  })
})

// ---------------------------------------------------------------------------
// Connection test (ST-B1)
// ---------------------------------------------------------------------------

describe('SettingsPage connection test', () => {
  function urlAwareMock(testResult: unknown, status = 200) {
    return vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : (input as Request).url
      if (url.includes('/test-connection')) {
        return jsonResponse(testResult, status)
      }
      return jsonResponse({ ok: true, data: DEFAULT_PAYLOAD })
    })
  }

  it('shows success and latency on ok:true', async () => {
    fetchMock.mockReset()
    fetchMock = urlAwareMock({ ok: true, data: { ok: true, latency_ms: 42 } })
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)

    const { container } = renderPage()
    await screen.findByText('連線測試')
    const shioajiRow = container.querySelector('[data-provider="shioaji"]')!
    const btn = shioajiRow.querySelector('button')!
    fireEvent.click(btn)

    await waitFor(() =>
      expect(
        container.querySelector('[data-testid="result-shioaji"]')?.textContent,
      ).toMatch(/連線成功/),
    )
    expect(
      container.querySelector('[data-testid="result-shioaji"]')?.textContent,
    ).toMatch(/42 ms/)
  })

  it('shows failure error on ok:false without leaking keys', async () => {
    fetchMock.mockReset()
    fetchMock = urlAwareMock({
      ok: true,
      data: { ok: false, error: 'connection refused' },
    })
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)

    const { container } = renderPage()
    await screen.findByText('連線測試')
    const finmindRow = container.querySelector('[data-provider="finmind"]')!
    fireEvent.click(finmindRow.querySelector('button')!)

    await waitFor(() =>
      expect(
        container.querySelector('[data-testid="result-finmind"]')?.textContent,
      ).toMatch(/connection refused/),
    )
  })
})

// ---------------------------------------------------------------------------
// Error states
// ---------------------------------------------------------------------------

describe('SettingsPage error states', () => {
  it('clears auth token on 401 (logout-on-401 invariant)', async () => {
    fetchMock.mockReset()
    fetchMock = vi.fn(async () =>
      jsonResponse(
        { ok: false, error: { code: 'auth_invalid', message: 'no' } },
        401,
      ),
    )
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)

    renderPage()
    await waitFor(() => {
      expect(useAuthStore.getState().token).toBeNull()
    })
  })

  it('shows retry button when backend returns 5xx', async () => {
    fetchMock.mockReset()
    fetchMock = vi.fn(async () =>
      jsonResponse(
        { ok: false, error: { code: 'internal_error', message: 'db down' } },
        500,
      ),
    )
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)

    renderPage()
    await screen.findByText(/載入失敗/)
    expect(screen.getByRole('button', { name: '重試' })).toBeInTheDocument()
  })
})
