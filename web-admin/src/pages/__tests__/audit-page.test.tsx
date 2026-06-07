import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { AuditPage } from '../AuditPage'
import { useAuthStore } from '@/stores'
import { JOURNAL_KIND_ALL } from '@/lib/journal-kinds'
import type { JournalRow, PaginatedRows } from '@/lib/api'

function row(
  overrides: Partial<JournalRow> & Pick<JournalRow, 'id' | 'kind'>,
): JournalRow {
  return {
    decision_id: 'd-129',
    symbol: '2454',
    created_at: '2026-05-08T14:03:08+08:00',
    payload: {},
    ...overrides,
  } as JournalRow
}

const ROWS_OK: JournalRow[] = [
  row({
    id: 101,
    kind: 'exit',
    payload: { side: 'long', qty: 100, price: 1180 },
  }),
  row({
    id: 102,
    kind: 'entry',
    payload: { side: 'long', qty: 100, price: 1180 },
  }),
  row({
    id: 103,
    kind: 'expire',
    payload: { confidence: 0.82 },
  }),
]

function envelope(
  items: JournalRow[],
  total = items.length,
): PaginatedRows<JournalRow> {
  return { items, total, limit: 50, offset: 0, has_more: items.length > 0 }
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderPage(initialEntries: string[] = ['/audit']) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <AuditPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useAuthStore.getState().setToken('test-token')
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AuditPage', () => {
  it('loading: ≥3 Skeleton elements while fetch is pending', () => {
    let resolveFetch!: (r: Response) => void
    const pending = new Promise<Response>((res) => {
      resolveFetch = res
    })
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => pending)

    const { container } = renderPage()
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThanOrEqual(3)
    resolveFetch(jsonResponse({ ok: true, data: envelope([]) }))
  })

  it('resolved: renders 共 N 列 (zh-TW formatted) with envelope total', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ ok: true, data: envelope(ROWS_OK, 8432) }),
    )

    renderPage()
    await screen.findByText('共 8,432 列')
  })

  it('empty: renders 此 filter 無紀錄 + 清空 filter button', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ ok: true, data: envelope([]) }),
    )

    renderPage()
    await screen.findByText('此 filter 無紀錄')
    expect(
      screen.getByRole('button', { name: /清空 filter/ }),
    ).toBeInTheDocument()
  })

  it('error: renders --destructive panel with retry button', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(
        { ok: false, error: { code: 'db_unavailable', message: 'sqlite locked' } },
        500,
      ),
    )

    renderPage()
    await waitFor(() =>
      expect(screen.getByText('載入失敗')).toBeInTheDocument(),
    )
    expect(screen.getByText('sqlite locked')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重試/ })).toBeInTheDocument()
  })

  it('filter: typing decision_id and pressing 套用 fires fetch with decision_id=d-129', async () => {
    const user = userEvent.setup()
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ ok: true, data: envelope(ROWS_OK) }))

    renderPage()
    await screen.findByText('共 3 列')

    fetchSpy.mockClear()

    const decisionInput = document.querySelector(
      'input[placeholder="d-129"]',
    ) as HTMLInputElement
    expect(decisionInput).not.toBeNull()
    await user.type(decisionInput, 'd-129')
    await user.click(screen.getByRole('button', { name: '套用' }))

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    const lastCall = fetchSpy.mock.calls[fetchSpy.mock.calls.length - 1]
    const url = String(lastCall[0])
    expect(url).toContain('decision_id=d-129')
  })

  it('density toggle: click flips compact → comfortable label', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ ok: true, data: envelope(ROWS_OK) }),
    )

    renderPage()
    await screen.findByText('共 3 列')

    expect(screen.getByText('compact')).toBeInTheDocument()
    await user.click(screen.getByLabelText('切換密度'))
    expect(screen.getByText('comfortable')).toBeInTheDocument()
  })

  it('renders 5 kind checkboxes whose names equal JOURNAL_KIND_ALL', () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      () => new Promise(() => undefined),
    )
    const { container } = renderPage()
    const checkboxes = container.querySelectorAll('input[type="checkbox"]')
    expect(checkboxes).toHaveLength(JOURNAL_KIND_ALL.length)
    const names = Array.from(checkboxes).map((c) => c.getAttribute('name'))
    expect(names).toEqual([...JOURNAL_KIND_ALL])
  })
})
