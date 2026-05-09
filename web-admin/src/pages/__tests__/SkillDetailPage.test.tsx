import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
  type Mock,
} from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router'
import { SkillDetailPage } from '../SkillDetailPage'
import { useAuthStore } from '@/stores'
import type { SkillDetail } from '@/lib/api'

vi.mock('@/hooks/useAdminEvents', () => ({ useAdminEvents: () => {} }))

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const DETAIL: SkillDetail = {
  name: 'market-data',
  description: '取得 daily bars 與 quote',
  category: 'data',
  body: '# Purpose\nFetch OHLCV from FinMind / Shioaji.\n\n# I/O\n- input: symbol\n- output: BarRow[]',
  cited_specs: ['market-data-cache', 'external-connectors'],
}

let fetchMock: Mock

function makeQc() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
}

function renderPage(name = 'market-data') {
  return render(
    <QueryClientProvider client={makeQc()}>
      <MemoryRouter initialEntries={[`/skills/${name}`]}>
        <Routes>
          <Route path="/skills" element={<div data-testid="skills-route" />} />
          <Route path="/skills/:name" element={<SkillDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useAuthStore.getState().setToken('test-token-aaaaaaaaaaaaaaaaaaaaaaaa')
  fetchMock = vi.fn(async () => jsonResponse({ ok: true, data: DETAIL }))
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('SkillDetailPage success', () => {
  it('renders header, description, cited specs chips, and body', async () => {
    renderPage()
    await screen.findByRole('heading', { name: 'market-data' })
    expect(screen.getByText('取得 daily bars 與 quote')).toBeInTheDocument()
    expect(screen.getByText('market-data-cache')).toBeInTheDocument()
    expect(screen.getByText('external-connectors')).toBeInTheDocument()
    expect(screen.getByText(/Fetch OHLCV/)).toBeInTheDocument()
    expect(document.querySelector('[data-category="data"]')).not.toBeNull()
  })

  it('renders editor / save UI is absent (read-only invariant)', async () => {
    renderPage()
    await screen.findByRole('heading', { name: 'market-data' })
    expect(screen.queryByText('儲存')).toBeNull()
    expect(screen.queryByText('編輯')).toBeNull()
    expect(document.querySelector('textarea')).toBeNull()
    expect(document.querySelector('form')).toBeNull()
  })
})

describe('SkillDetailPage empty cited_specs', () => {
  it('renders the （無 cited_specs） fallback', async () => {
    fetchMock.mockReset()
    fetchMock = vi.fn(async () =>
      jsonResponse({ ok: true, data: { ...DETAIL, cited_specs: [] } }),
    )
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)

    renderPage()
    await screen.findByText('（無 cited_specs）')
    expect(screen.queryByText('market-data-cache')).not.toBeInTheDocument()
  })
})

describe('SkillDetailPage 404', () => {
  it('renders the 找不到 skill empty state with a back-link button', async () => {
    fetchMock.mockReset()
    fetchMock = vi.fn(async () =>
      jsonResponse(
        {
          ok: false,
          error: { code: 'not_found', message: 'skill not found: nope' },
        },
        404,
      ),
    )
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)

    renderPage('nope')
    await screen.findByText(/找不到 skill:/)
    expect(screen.getByText('nope')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: '返回 Skills' }),
    ).toBeInTheDocument()
    expect(screen.queryByText(/^Body$/)).toBeNull()
    expect(screen.queryByText(/Cited specs/)).toBeNull()
  })
})

describe('SkillDetailPage 500', () => {
  it('renders destructive alert with retry', async () => {
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
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重試' })).toBeInTheDocument()
  })
})
