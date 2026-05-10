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
import { MemoryRouter } from 'react-router'
import { MemoryPage } from '../MemoryPage'
import { useAuthStore } from '@/stores'
import type { MemoryRow } from '@/lib/api'

vi.mock('@/hooks/useAdminEvents', () => ({ useAdminEvents: () => {} }))

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function emptyRowsResponse() {
  return jsonResponse({
    ok: true,
    data: { items: [], total: 0, limit: 50, offset: 0, has_more: false },
  })
}

function rowsResponse(items: MemoryRow[], total?: number, has_more = false) {
  return jsonResponse({
    ok: true,
    data: {
      items,
      total: total ?? items.length,
      limit: 50,
      offset: 0,
      has_more,
    },
  })
}

const ROW_NOTE: MemoryRow = {
  id: 1,
  kind: 'note',
  content: 'first note body — read me',
  content_preview: 'first note body — read me',
  content_truncated: false,
  tags: ['vcp'],
  source: null,
  created_at: '2026-05-09T10:00:00+08:00',
}

const ROW_LESSON: MemoryRow = {
  id: 2,
  kind: 'lesson',
  content: 'lesson learned about breakouts',
  content_preview: 'lesson learned about breakouts',
  content_truncated: false,
  tags: [],
  source: 'phase5-review:dec_X',
  created_at: '2026-05-09T11:00:00+08:00',
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
      <MemoryRouter initialEntries={['/memory']}>
        <MemoryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function urlOf(call: Parameters<typeof fetch>): string {
  const input = call[0]
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.toString()
  return (input as Request).url
}

beforeEach(() => {
  useAuthStore.getState().setToken('test-token-aaaaaaaaaaaaaaaaaaaaaaaa')
  fetchMock = vi.fn(async () => emptyRowsResponse())
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Browse defaults + filter
// ---------------------------------------------------------------------------

describe('MemoryPage browse', () => {
  it('default view fires listMemory without kind/tag filters', async () => {
    fetchMock.mockResolvedValueOnce(rowsResponse([ROW_NOTE, ROW_LESSON]))
    renderPage()

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })
    const url = urlOf(fetchMock.mock.calls[0] as Parameters<typeof fetch>)
    expect(url).toContain('/api/admin/memory/rows')
    // limit/offset are page-managed defaults; kind/tag must not be passed.
    expect(url).not.toContain('kind=')
    expect(url).not.toContain('tag=')
  })

  it('selecting a kind triggers a refetch with kind param', async () => {
    fetchMock.mockResolvedValueOnce(rowsResponse([ROW_NOTE, ROW_LESSON]))
    fetchMock.mockResolvedValueOnce(rowsResponse([ROW_LESSON]))
    renderPage()

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    const kindSelect = screen.getByLabelText('按 kind 過濾') as HTMLSelectElement
    fireEvent.change(kindSelect, { target: { value: 'lesson' } })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const url = urlOf(fetchMock.mock.calls[1] as Parameters<typeof fetch>)
    expect(url).toContain('/api/admin/memory/rows?')
    expect(url).toContain('kind=lesson')
  })

  it('adding a tag chip triggers a refetch with tag param', async () => {
    fetchMock.mockResolvedValueOnce(rowsResponse([ROW_NOTE]))
    fetchMock.mockResolvedValueOnce(rowsResponse([ROW_NOTE]))
    renderPage()

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    const tagInput = screen.getByLabelText('按 tag 過濾') as HTMLInputElement
    fireEvent.change(tagInput, { target: { value: 'vcp' } })
    fireEvent.keyDown(tagInput, { key: 'Enter' })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const url = urlOf(fetchMock.mock.calls[1] as Parameters<typeof fetch>)
    expect(url).toContain('tag=vcp')
  })

  it('clicking a row expands and shows full content + char count', async () => {
    fetchMock.mockResolvedValueOnce(rowsResponse([ROW_NOTE]))
    renderPage()

    await waitFor(() => screen.getByText(/first note body/))
    const row = screen.getByText(/first note body/).closest('tr')
    expect(row).toBeTruthy()
    fireEvent.click(row!)

    await waitFor(() => {
      expect(screen.getByText(`${ROW_NOTE.content.length} 字元`)).toBeTruthy()
    })
  })

  it('renders default empty state when no rows and no filter', async () => {
    fetchMock.mockResolvedValueOnce(emptyRowsResponse())
    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText(/尚無 memory；待 Phase 5 復盤 \/ proposal 任務寫入/),
      ).toBeTruthy()
    })
  })

  it('renders filtered empty state with 清除 filter button', async () => {
    fetchMock.mockResolvedValueOnce(rowsResponse([ROW_NOTE]))
    fetchMock.mockResolvedValueOnce(emptyRowsResponse())
    fetchMock.mockResolvedValueOnce(rowsResponse([ROW_NOTE]))
    renderPage()

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    const kindSelect = screen.getByLabelText('按 kind 過濾') as HTMLSelectElement
    fireEvent.change(kindSelect, { target: { value: 'lesson' } })

    await waitFor(() =>
      expect(screen.getByText(/無符合條件的 memory/)).toBeTruthy(),
    )
    const clearBtn = screen.getByRole('button', { name: /清除 filter/ })
    fireEvent.click(clearBtn)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
  })

  it('renders error state with retry button', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { ok: false, error: { code: 'internal_error', message: 'boom' } },
        500,
      ),
    )
    fetchMock.mockResolvedValueOnce(rowsResponse([ROW_NOTE]))
    renderPage()

    await waitFor(() => screen.getByRole('alert'))
    const retry = screen.getByRole('button', { name: /重試/ })
    fireEvent.click(retry)

    await waitFor(() => screen.getByText(/first note body/))
  })
})

// ---------------------------------------------------------------------------
// Search view
// ---------------------------------------------------------------------------

describe('MemoryPage search', () => {
  it('switching to 搜尋 renders the prompt and never fires searchMemory on empty input', async () => {
    fetchMock.mockResolvedValueOnce(emptyRowsResponse())
    renderPage()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    const searchTab = screen.getByRole('tab', { name: '搜尋' })
    fireEvent.click(searchTab)

    expect(screen.getByText('請輸入查詢關鍵字')).toBeTruthy()

    // Wait a tick for any potential async settle, then assert no extra fetch.
    await new Promise((r) => setTimeout(r, 30))
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('Ctrl+Enter on the input fires searchMemory', async () => {
    fetchMock.mockResolvedValueOnce(emptyRowsResponse())
    fetchMock.mockResolvedValueOnce(rowsResponse([ROW_NOTE]))
    renderPage()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('tab', { name: '搜尋' }))
    const input = screen.getByLabelText('FTS5 查詢') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'breakout' } })
    fireEvent.keyDown(input, { key: 'Enter', ctrlKey: true })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const url = urlOf(fetchMock.mock.calls[1] as Parameters<typeof fetch>)
    expect(url).toContain('/api/admin/memory/search?')
    expect(url).toContain('q=breakout')
  })

  it('renders friendly inline 查詢語法錯誤 on invalid_query envelope', async () => {
    fetchMock.mockResolvedValueOnce(emptyRowsResponse())
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          ok: false,
          error: {
            code: 'invalid_query',
            message: 'FTS5 query syntax error',
          },
        },
        400,
      ),
    )
    renderPage()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('tab', { name: '搜尋' }))
    const input = screen.getByLabelText('FTS5 查詢') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'foo OR' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => screen.getByText('查詢語法錯誤'))
    // 重試 button must NOT appear for invalid_query (it's a user-input issue,
    // not a transient server failure).
    expect(screen.queryByRole('button', { name: /重試/ })).toBeNull()
  })

  it('switching tabs collapses the previously expanded row', async () => {
    fetchMock.mockResolvedValueOnce(rowsResponse([ROW_NOTE]))
    renderPage()
    await waitFor(() => screen.getByText(/first note body/))

    const row = screen.getByText(/first note body/).closest('tr')!
    fireEvent.click(row)
    await waitFor(() =>
      expect(screen.queryByText(`${ROW_NOTE.content.length} 字元`)).toBeTruthy(),
    )

    // Switch to search tab and back; the expanded row should be gone.
    fireEvent.click(screen.getByRole('tab', { name: '搜尋' }))
    fireEvent.click(screen.getByRole('tab', { name: '瀏覽' }))

    await waitFor(() =>
      expect(screen.queryByText(`${ROW_NOTE.content.length} 字元`)).toBeNull(),
    )
  })
})
