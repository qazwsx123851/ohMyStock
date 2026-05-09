import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
  type Mock,
} from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router'
import { SkillsPage } from '../SkillsPage'
import { useAuthStore } from '@/stores'
import type { Skill } from '@/lib/api'

vi.mock('@/hooks/useAdminEvents', () => ({ useAdminEvents: () => {} }))

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const ITEMS: Skill[] = [
  {
    name: 'alpha',
    description: 'data ingestion alpha',
    category: 'data',
    body_preview: '# alpha',
    body_truncated: false,
    cited_specs: ['spec-one'],
  },
  {
    name: 'beta-indicator',
    description: 'rs-percentile beta',
    category: 'indicator',
    body_preview: '# beta',
    body_truncated: false,
    cited_specs: [],
  },
  {
    name: 'gamma-tool',
    description: 'utility tool gamma',
    category: 'tool',
    body_preview: '# gamma',
    body_truncated: false,
    cited_specs: [],
  },
]

let fetchMock: Mock

function makeQc() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeQc()}>
      <MemoryRouter initialEntries={['/skills']}>
        <Routes>
          <Route path="/skills" element={<SkillsPage />} />
          <Route
            path="/skills/:name"
            element={<div data-testid="detail-route" />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useAuthStore.getState().setToken('test-token-aaaaaaaaaaaaaaaaaaaaaaaa')
  fetchMock = vi.fn(async () =>
    jsonResponse({ ok: true, data: { items: ITEMS } }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

describe('SkillsPage loading', () => {
  it('renders 12 Skeleton cards before data resolves', () => {
    fetchMock.mockImplementationOnce(
      () =>
        new Promise(() => {
          /* never resolves */
        }) as unknown as Promise<Response>,
    )
    renderPage()
    const grid = screen.getByTestId('skills-loading')
    expect(grid.children.length).toBe(12)
  })
})

// ---------------------------------------------------------------------------
// Default render
// ---------------------------------------------------------------------------

describe('SkillsPage default render', () => {
  it('renders one card per item with name, description, and category badge', async () => {
    renderPage()
    await screen.findByText('alpha')
    expect(screen.getByText('beta-indicator')).toBeInTheDocument()
    expect(screen.getByText('gamma-tool')).toBeInTheDocument()
    expect(screen.getByText('data ingestion alpha')).toBeInTheDocument()

    const badges = document.querySelectorAll('[data-category]')
    expect(badges.length).toBe(3)
    const cats = Array.from(badges).map((b) => b.getAttribute('data-category'))
    expect(cats).toEqual(expect.arrayContaining(['data', 'indicator', 'tool']))
  })

  it('renders the 共/筆 counter once data is loaded', async () => {
    renderPage()
    await screen.findByText('alpha')
    expect(screen.getByText(/共\s+3\/3\s+筆/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Filtering
// ---------------------------------------------------------------------------

describe('SkillsPage filter', () => {
  it('filters by name substring without firing a new fetch', async () => {
    renderPage()
    await screen.findByText('alpha')
    expect(fetchMock).toHaveBeenCalledTimes(1)

    const input = screen.getByLabelText('搜尋 skills') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'beta' } })

    await waitFor(() =>
      expect(screen.queryByText('alpha')).not.toBeInTheDocument(),
    )
    expect(screen.getByText('beta-indicator')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('filters by category select', async () => {
    renderPage()
    await screen.findByText('alpha')
    const select = screen.getByLabelText('類別過濾') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'tool' } })
    await waitFor(() =>
      expect(screen.queryByText('alpha')).not.toBeInTheDocument(),
    )
    expect(screen.getByText('gamma-tool')).toBeInTheDocument()
    expect(screen.queryByText('beta-indicator')).not.toBeInTheDocument()
  })

  it('shows empty-after-filter state with a clear button', async () => {
    renderPage()
    await screen.findByText('alpha')
    const input = screen.getByLabelText('搜尋 skills') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'zzzz' } })

    await screen.findByText('無符合條件的 skill')
    const clearBtn = screen.getByRole('button', { name: '清除 filter' })
    fireEvent.click(clearBtn)
    await screen.findByText('alpha')
    expect(screen.queryByText('無符合條件的 skill')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Empty registry
// ---------------------------------------------------------------------------

describe('SkillsPage empty registry', () => {
  it('renders the 尚未註冊任何 skill empty state', async () => {
    fetchMock.mockReset()
    fetchMock = vi.fn(async () =>
      jsonResponse({ ok: true, data: { items: [] } }),
    )
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)

    renderPage()
    await screen.findByText('尚未註冊任何 skill')
    expect(
      screen.queryByRole('button', { name: '清除 filter' }),
    ).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

describe('SkillsPage navigation', () => {
  it('navigates to /skills/<name> on card click', async () => {
    renderPage()
    const card = await screen.findByLabelText(/^alpha：/)
    fireEvent.click(card)
    await screen.findByTestId('detail-route')
  })

  it('navigates on Enter when card has focus', async () => {
    renderPage()
    const card = await screen.findByLabelText(/^beta-indicator：/)
    card.focus()
    fireEvent.keyDown(card, { key: 'Enter' })
    await screen.findByTestId('detail-route')
  })
})

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

describe('SkillsPage error', () => {
  it('renders destructive Card with retry on 500', async () => {
    fetchMock.mockReset()
    fetchMock = vi.fn(async () =>
      jsonResponse(
        { ok: false, error: { code: 'internal_error', message: 'db down' } },
        500,
      ),
    )
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)

    renderPage()
    await screen.findByText(/載入 skills 失敗/)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重試' })).toBeInTheDocument()
  })
})
