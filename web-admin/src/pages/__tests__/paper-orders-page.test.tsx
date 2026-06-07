import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { PaperOrdersPage } from '../PaperOrdersPage'
import { useAuthStore } from '@/stores'
import type { JournalRow, PaginatedRows } from '@/lib/api'

function row(
  overrides: Partial<JournalRow> & Pick<JournalRow, 'id' | 'kind'>,
): JournalRow {
  return {
    decision_id: null,
    symbol: '2330',
    created_at: '2026-05-08T13:00:00+08:00',
    payload: {},
    ...overrides,
  } as JournalRow
}

const ROWS_OK: JournalRow[] = [
  row({
    id: 11,
    kind: 'exit',
    symbol: '2454',
    created_at: '2026-05-08T14:03:12+08:00',
    payload: { side: 'long', qty: 100, price: 1180 },
  }),
  row({
    id: 12,
    kind: 'entry',
    symbol: '2454',
    created_at: '2026-05-08T14:03:08+08:00',
    payload: { side: 'long', qty: 100, price: 1180 },
  }),
  row({
    id: 13,
    kind: 'reject',
    symbol: '6505',
    created_at: '2026-05-08T13:58:01+08:00',
    payload: { side: 'short', qty: 500, price: 33.6 },
  }),
]

function envelope(
  items: JournalRow[],
  total = items.length,
): PaginatedRows<JournalRow> {
  return { items, total, limit: 50, offset: 0, has_more: false }
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderPage(initialEntries: string[] = ['/paper/orders']) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <PaperOrdersPage />
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

describe('PaperOrdersPage', () => {
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

  it('resolved: renders rows and applies side dual-encoding (long=text-up+ArrowUp, short=text-down+ArrowDown)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ ok: true, data: envelope(ROWS_OK) }),
    )

    const { container } = renderPage()
    await screen.findByText('已拒絕')

    const upCells = container.querySelectorAll('[data-direction="up"]')
    const downCells = container.querySelectorAll('[data-direction="down"]')
    expect(upCells.length).toBeGreaterThanOrEqual(2)
    expect(downCells.length).toBeGreaterThanOrEqual(1)

    const upWithUpClass = Array.from(upCells).some((el) =>
      el.className.includes('text-up'),
    )
    const upWithSvg = Array.from(upCells).some((el) => el.querySelector('svg'))
    expect(upWithUpClass).toBe(true)
    expect(upWithSvg).toBe(true)

    const downWithDownClass = Array.from(downCells).some((el) =>
      el.className.includes('text-down'),
    )
    const downWithSvg = Array.from(downCells).some((el) =>
      el.querySelector('svg'),
    )
    expect(downWithDownClass).toBe(true)
    expect(downWithSvg).toBe(true)
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

  it('filter: unchecking reject and pressing 套用 fires fetch with kind=entry & kind=exit only', async () => {
    const user = userEvent.setup()
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ ok: true, data: envelope(ROWS_OK) }))

    renderPage()
    await screen.findByText('已拒絕')

    fetchSpy.mockClear()

    const rejectCheckbox = document.querySelector(
      'input[type="checkbox"][name="reject"]',
    ) as HTMLInputElement
    expect(rejectCheckbox).not.toBeNull()

    await user.click(rejectCheckbox)
    await user.click(screen.getByRole('button', { name: '套用' }))

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    const lastCall = fetchSpy.mock.calls[fetchSpy.mock.calls.length - 1]
    const url = String(lastCall[0])
    expect(url).toContain('kind=entry')
    expect(url).toContain('kind=exit')
    expect(url).not.toContain('kind=reject')
  })

  it('filter bar renders 3 checkboxes whose names match JOURNAL_KIND_ENTRY_LIKE order', () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      () => new Promise(() => undefined),
    )
    const { container } = renderPage()
    const checkboxes = container.querySelectorAll('input[type="checkbox"]')
    expect(checkboxes).toHaveLength(3)
    const names = Array.from(checkboxes).map((c) => c.getAttribute('name'))
    expect(names).toEqual(['entry', 'exit', 'reject'])
  })
})
