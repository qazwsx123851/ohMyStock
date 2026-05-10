/**
 * /proposals page tests.
 *
 * Covers: row render, status tab updates URL + triggers refetch, row click
 * navigates, loading skeletons, empty-after-filter shows reset button,
 * empty-overall shows "尚無提案", error shows retry.
 */
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
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router'
import { ProposalsPage } from '../ProposalsPage'
import { useAuthStore } from '@/stores'
import type { Proposal } from '@/lib/api'

vi.mock('@/hooks/useAdminEvents', () => ({ useAdminEvents: () => {} }))

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function makeProposal(overrides: Partial<Proposal> = {}): Proposal {
  return {
    slug: '2026-04-30-x',
    proposal_id: '2026-04-30-x',
    status: 'pending',
    topic: 'x',
    target_section: 'cheatsheet §6.6',
    created_by: 'mark',
    created_at: '2026-04-30T10:00:00+08:00',
    review_id: null,
    priority: 'medium',
    ...overrides,
  }
}

const ITEMS: Proposal[] = [
  makeProposal({
    slug: '2026-05-04-rejected-x',
    proposal_id: '2026-05-04-rejected-x',
    topic: 'rejected-x',
    status: 'rejected',
    created_at: '2026-05-04T10:00:00+08:00',
    priority: 'low',
  }),
  makeProposal({
    slug: '2026-05-03-merged-x',
    proposal_id: '2026-05-03-merged-x',
    topic: 'merged-x',
    status: 'merged',
    created_at: '2026-05-03T10:00:00+08:00',
    priority: 'high',
  }),
  makeProposal({
    slug: '2026-04-30-pending-x',
    proposal_id: '2026-04-30-pending-x',
    topic: 'pending-x',
    status: 'pending',
    created_at: '2026-04-30T10:00:00+08:00',
    priority: 'medium',
  }),
]

let fetchMock: Mock

function makeQc() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
}

function renderPage(initialPath = '/proposals') {
  return render(
    <QueryClientProvider client={makeQc()}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/proposals" element={<ProposalsPage />} />
          <Route
            path="/proposals/:slug"
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
    jsonResponse({
      ok: true,
      data: {
        items: ITEMS,
        total: ITEMS.length,
        limit: 50,
        offset: 0,
        has_more: false,
      },
    }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ProposalsPage loading', () => {
  it('renders skeleton placeholder before data resolves', () => {
    fetchMock.mockImplementationOnce(
      () =>
        new Promise(() => {
          /* never resolves */
        }) as unknown as Promise<Response>,
    )
    renderPage()
    expect(screen.getByTestId('proposals-loading')).toBeInTheDocument()
  })
})

describe('ProposalsPage rows', () => {
  it('renders one row per item with topic + status badges', async () => {
    renderPage()
    await screen.findByText('rejected-x')
    expect(screen.getByText('merged-x')).toBeInTheDocument()
    expect(screen.getByText('pending-x')).toBeInTheDocument()
    // 'rejected' / 'merged' / 'pending' appear both as topic substrings and
    // as status badge text; one match per status is enough.
    expect(screen.getAllByText('rejected').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('merged').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('pending').length).toBeGreaterThanOrEqual(1)
  })

  it('row click navigates to /proposals/<slug>', async () => {
    renderPage()
    const cell = await screen.findByText('rejected-x')
    fireEvent.click(cell)
    await waitFor(() =>
      expect(screen.getByTestId('detail-route')).toBeInTheDocument(),
    )
  })
})

describe('ProposalsPage tabs', () => {
  it('clicking a status tab triggers a refetch with ?status=', async () => {
    renderPage()
    await screen.findByText('rejected-x')
    expect(fetchMock).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('tab', { name: 'approved' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const secondCall = fetchMock.mock.calls[1] as Parameters<typeof fetch>
    const url =
      typeof secondCall[0] === 'string'
        ? secondCall[0]
        : (secondCall[0] as Request).url
    expect(url).toContain('status=approved')
  })

  it('全部 tab omits the status query param', async () => {
    renderPage('/proposals?status=pending')
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const firstCall = fetchMock.mock.calls[0] as Parameters<typeof fetch>
    const url1 =
      typeof firstCall[0] === 'string'
        ? firstCall[0]
        : (firstCall[0] as Request).url
    expect(url1).toContain('status=pending')

    fireEvent.click(screen.getByRole('tab', { name: '全部' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const secondCall = fetchMock.mock.calls[1] as Parameters<typeof fetch>
    const url2 =
      typeof secondCall[0] === 'string'
        ? secondCall[0]
        : (secondCall[0] as Request).url
    expect(url2).not.toContain('status=')
  })
})

describe('ProposalsPage empty/error states', () => {
  it('empty-after-filter shows 回到全部 reset button', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        ok: true,
        data: {
          items: [],
          total: 0,
          limit: 50,
          offset: 0,
          has_more: false,
        },
      }),
    )
    renderPage('/proposals?status=rejected')
    const button = await screen.findByRole('button', { name: '回到全部' })
    expect(button).toBeInTheDocument()
    fireEvent.click(button)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })

  it('empty overall shows "尚無提案" without reset button', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        ok: true,
        data: {
          items: [],
          total: 0,
          limit: 50,
          offset: 0,
          has_more: false,
        },
      }),
    )
    renderPage('/proposals')
    await screen.findByText('尚無提案')
    expect(screen.queryByRole('button', { name: '回到全部' })).toBeNull()
  })

  it('error shows destructive Card with retry button', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { ok: false, error: { code: 'internal_error', message: 'boom' } },
        500,
      ),
    )
    renderPage()
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText(/載入提案失敗/)).toBeInTheDocument()
    const retry = within(alert).getByRole('button', { name: '重試' })
    fireEvent.click(retry)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })
})
