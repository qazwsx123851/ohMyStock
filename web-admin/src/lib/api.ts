/**
 * web-admin API client.
 *
 * - apiFetch: REST call with Bearer header injection + envelope parsing.
 * - openSSE:  fetch-based SSE stream (allows custom Authorization header,
 *             which native EventSource does not).
 *
 * Both honour the { ok, data, error } envelope from
 * openspec/specs/server-action-endpoints/spec.md and trigger logout()
 * on HTTP 401.
 */

import { useAuthStore, logout } from '@/stores'

// ---------------------------------------------------------------------------
// Domain types - what backend endpoints return, hand-written until codegen
// ---------------------------------------------------------------------------

export type StatsToday = {
  realized_pnl_twd: number
  open_positions: number
  pending_confirms: number
  llm_cost_usd: number
}

// Open position row from GET /api/admin/positions/open
export type OpenPosition = {
  symbol: string
  side: 'long' | 'short'
  qty: number
  entry_price: number
  mark_price: number
  unrealized_pnl_twd: number
  unrealized_pnl_pct: number
  stop_loss: number
  t1_target: number
  hold_days: number
  time_stop_date: string
  entry_reason: string
  entry_at: string
}

// Single row in GET /api/admin/journal/rows
export type JournalRow = {
  id: number | string
  kind: string
  symbol?: string | null
  decision_id?: string | null
  created_at: string
  payload: Record<string, unknown>
  status?: string
}

// Paginated envelope shape returned by paginated admin list endpoints
export type PaginatedRows<T> = {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export type LiveEvent = {
  event_type: string
  agent?: string
  timestamp: string
  payload?: Record<string, unknown> & { symbol?: string; price?: number }
}

export type Envelope<T> =
  | { ok: true; data: T }
  | { ok: false; error: { code: string; message: string } }

// ---------------------------------------------------------------------------
// ApiError
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  code: string
  httpStatus: number
  constructor(code: string, message: string, httpStatus: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.httpStatus = httpStatus
  }
}

// ---------------------------------------------------------------------------
// apiFetch
// ---------------------------------------------------------------------------

function authHeader(): Record<string, string> {
  const t = useAuthStore.getState().token
  return t ? { Authorization: `Bearer ${t}` } : {}
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...authHeader(),
    ...((init?.headers as Record<string, string>) ?? {}),
  }
  if (init?.body && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(path, { ...init, headers })

  if (res.status === 401) {
    logout()
    throw new ApiError('auth_invalid', 'unauthorised', 401)
  }

  let body: Envelope<T>
  try {
    body = (await res.json()) as Envelope<T>
  } catch (e) {
    throw new ApiError('non_json_response', `non-JSON response (${res.status}): ${(e as Error).message}`, res.status)
  }

  if ('ok' in body && body.ok) {
    return body.data
  }
  if ('ok' in body && !body.ok) {
    throw new ApiError(body.error.code, body.error.message, res.status)
  }
  throw new ApiError('envelope_invalid', 'response did not match { ok, ... } envelope', res.status)
}

// ---------------------------------------------------------------------------
// openSSE - fetch + ReadableStream parser supporting Authorization header
// ---------------------------------------------------------------------------

export type SseHandle = {
  close: () => void
}

export type SseHandlers = {
  onEvent: (event: LiveEvent) => void
  onUnauthorized: () => void
  onError?: (err: unknown) => void
}

export function openSSE(path: string, handlers: SseHandlers): SseHandle {
  const ctrl = new AbortController()
  const headers: Record<string, string> = { Accept: 'text/event-stream', ...authHeader() }
  let closed = false

  ;(async () => {
    let res: Response
    try {
      res = await fetch(path, { method: 'GET', headers, signal: ctrl.signal })
    } catch (err) {
      if (!closed) handlers.onError?.(err)
      return
    }
    if (res.status === 401) {
      handlers.onUnauthorized()
      return
    }
    if (!res.ok || !res.body) {
      handlers.onError?.(new Error(`SSE handshake failed: ${res.status}`))
      return
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE messages separated by blank line
        let sep = buffer.indexOf('\n\n')
        while (sep !== -1) {
          const raw = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          parseAndDispatch(raw, handlers.onEvent)
          sep = buffer.indexOf('\n\n')
        }
      }
    } catch (err) {
      if (!closed) handlers.onError?.(err)
    }
  })()

  return {
    close() {
      closed = true
      try { ctrl.abort() } catch { /* ignore */ }
    },
  }
}

function parseAndDispatch(raw: string, onEvent: (e: LiveEvent) => void): void {
  const lines = raw.split('\n')
  const dataLines: string[] = []
  for (const line of lines) {
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''))
    }
  }
  if (dataLines.length === 0) return
  const payload = dataLines.join('\n').trim()
  if (!payload || payload === '{}') return
  try {
    const parsed = JSON.parse(payload) as LiveEvent
    onEvent(parsed)
  } catch {
    // ignore malformed events
  }
}