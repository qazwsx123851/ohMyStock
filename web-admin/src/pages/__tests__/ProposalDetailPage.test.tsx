/**
 * /proposals/:slug page tests.
 *
 * Covers: header + body render, changelog list with all 3 kinds,
 * action row variants per status, 404 / 422 / 500 error paths.
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
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router'
import { ProposalDetailPage } from '../ProposalDetailPage'
import { useAuthStore } from '@/stores'
import type { ProposalDetail } from '@/lib/api'

vi.mock('@/hooks/useAdminEvents', () => ({ useAdminEvents: () => {} }))

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function makeDetail(overrides: Partial<ProposalDetail> = {}): ProposalDetail {
  return {
    slug: '2026-04-30-x',
    proposal_id: '2026-04-30-x',
    status: 'pending',
    topic: 'x-topic',
    target_section: 'cheatsheet §6.6',
    created_by: 'mark',
    created_at: '2026-04-30T10:00:00+08:00',
    review_id: null,
    priority: 'medium',
    body: {
      description: 'desc body',
      motivation: 'mot body metrics.json#',
      diff_draft: 'diff body',
      expected_impact: 'impact body',
      risk_assessment: 'risk body',
      validation_plan: 'plan body',
      expected_improvement: 'improve body',
    },
    changelog: [
      { kind: 'created', timestamp: '2026-04-30T10:00:00+08:00', actor: 'mark' },
    ],
    extra_frontmatter: {},
    ...overrides,
  }
}

let fetchMock: Mock

function makeQc() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
}

function renderAt(slug: string) {
  return render(
    <QueryClientProvider client={makeQc()}>
      <MemoryRouter initialEntries={[`/proposals/${slug}`]}>
        <Routes>
          <Route path="/proposals/:slug" element={<ProposalDetailPage />} />
          <Route
            path="/proposals"
            element={<div data-testid="list-route" />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useAuthStore.getState().setToken('test-token-aaaaaaaaaaaaaaaaaaaaaaaa')
  fetchMock = vi.fn(async () =>
    jsonResponse({ ok: true, data: makeDetail() }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ProposalDetailPage header + body', () => {
  it('renders topic h1, status badge, priority badge, and 7 body sections', async () => {
    renderAt('2026-04-30-x')
    await screen.findByRole('heading', { level: 1, name: 'x-topic' })
    expect(screen.getByText('pending')).toBeInTheDocument()
    expect(screen.getByText('medium')).toBeInTheDocument()
    expect(screen.getByText('## 1. 改動描述')).toBeInTheDocument()
    expect(screen.getByText('## 7. 預期改善幅度')).toBeInTheDocument()
    expect(screen.getByText('desc body')).toBeInTheDocument()
    expect(screen.getByText(/mot body metrics\.json#/)).toBeInTheDocument()
  })

  it('omits the Extra metadata Card when extra_frontmatter is empty', async () => {
    renderAt('2026-04-30-x')
    await screen.findByText('## 1. 改動描述')
    expect(screen.queryByText('Extra metadata')).toBeNull()
  })

  it('renders Extra metadata Card for merged file', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        ok: true,
        data: makeDetail({
          status: 'merged',
          extra_frontmatter: {
            merged_to_version: 'v3.1',
            merged_at: '2026-05-12T10:00:00+08:00',
          },
        }),
      }),
    )
    renderAt('2026-05-03-merged-x')
    await screen.findByText('Extra metadata')
    expect(screen.getByText('merged_to_version')).toBeInTheDocument()
    expect(screen.getByText('v3.1')).toBeInTheDocument()
    expect(screen.getByText('merged_at')).toBeInTheDocument()
  })
})

describe('ProposalDetailPage changelog', () => {
  it('renders created, transition, and raw entries', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        ok: true,
        data: makeDetail({
          changelog: [
            {
              kind: 'created',
              timestamp: '2026-04-30T10:00:00+08:00',
              actor: 'mark',
            },
            {
              kind: 'transition',
              timestamp: '2026-05-01T11:00:00+08:00',
              from_status: 'pending',
              to_status: 'validating',
              actor: 'mark',
              reason: null,
            },
            {
              kind: 'raw',
              text: '- arbitrary free-form note',
            },
          ],
        }),
      }),
    )
    renderAt('2026-04-30-x')
    await screen.findByText('created by')
    expect(screen.getAllByText('pending')[0]).toBeInTheDocument()
    expect(screen.getByText('validating')).toBeInTheDocument()
    expect(
      screen.getByText('- arbitrary free-form note'),
    ).toBeInTheDocument()
  })
})

describe('ProposalDetailPage action row', () => {
  it('pending → renders [Mark Validating] only', async () => {
    renderAt('2026-04-30-x')
    await screen.findByRole('button', { name: 'Mark Validating' })
    expect(screen.queryByRole('button', { name: 'Approve…' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Reject…' })).toBeNull()
  })

  it('validating → renders [Approve…] and [Reject…]', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        ok: true,
        data: makeDetail({ status: 'validating' }),
      }),
    )
    renderAt('2026-05-01-validating-x')
    await screen.findByRole('button', { name: 'Approve…' })
    expect(screen.getByRole('button', { name: 'Reject…' })).toBeInTheDocument()
  })

  it('approved → renders [Mark Merged…] and [Reject…]', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        ok: true,
        data: makeDetail({ status: 'approved' }),
      }),
    )
    renderAt('2026-05-02-approved-x')
    await screen.findByRole('button', { name: 'Mark Merged…' })
    expect(screen.getByRole('button', { name: 'Reject…' })).toBeInTheDocument()
  })

  it('merged → renders 終局狀態 with no transition buttons', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ ok: true, data: makeDetail({ status: 'merged' }) }),
    )
    renderAt('2026-05-03-merged-x')
    await screen.findByText('終局狀態')
    expect(screen.queryByRole('button', { name: 'Mark Validating' })).toBeNull()
  })

  it('rejected → renders 終局狀態', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ ok: true, data: makeDetail({ status: 'rejected' }) }),
    )
    renderAt('2026-05-04-rejected-x')
    await screen.findByText('終局狀態')
  })
})

describe('ProposalDetailPage error paths', () => {
  it('404 not_found shows back-link to Proposals, no body cards', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { ok: false, error: { code: 'not_found', message: 'gone' } },
        404,
      ),
    )
    renderAt('does-not-exist')
    await screen.findByText(/找不到提案/)
    expect(
      screen.getByRole('link', { name: '返回 Proposals' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('## 1. 改動描述')).toBeNull()
  })

  it('422 malformed_proposal shows destructive Card with NO retry', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          ok: false,
          error: {
            code: 'malformed_proposal',
            message: 'missing section: ## 5.',
          },
        },
        422,
      ),
    )
    renderAt('broken-x')
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText(/格式錯誤/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重試' })).toBeNull()
  })

  it('500 internal_error shows destructive Card with retry button', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { ok: false, error: { code: 'internal_error', message: 'boom' } },
        500,
      ),
    )
    renderAt('2026-04-30-x')
    const alert = await screen.findByRole('alert')
    const retry = within(alert).getByRole('button', { name: '重試' })
    fireEvent.click(retry)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })
})
