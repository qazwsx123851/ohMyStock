/**
 * Chat SSE stream parser.
 *
 * The chat send endpoint (`POST /api/admin/chat/sessions/:id/messages`)
 * answers with `Content-Type: text/event-stream` and yields named SSE
 * frames of the form:
 *
 *     event: <kind>\ndata: <json>\n\n
 *
 * We can't use the native `EventSource` API because it does not support
 * custom `Authorization` headers, so this module wraps `fetch` +
 * `ReadableStream` + `TextDecoder` and dispatches each parsed frame to
 * the appropriate callback.
 *
 * Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/
 *       specs/web-admin-chat-pages/spec.md
 */

import { useAuthStore } from '@/stores'

export type ChatStreamCallbacks = {
  onDelta: (text: string) => void
  onToolCall: (call: {
    id: string
    name: string
    args: Record<string, unknown>
  }) => void
  onToolResult: (result: {
    tool_call_id: string
    result: Record<string, unknown>
  }) => void
  onDone: (meta: {
    message_id: string
    elapsed_ms: number
    cost_usd?: number
    input_tokens?: number
    output_tokens?: number
  }) => void
  onError: (err: { code: string; message: string }) => void
}

type SseFrame = { event: string; data: string }

function parseFrame(raw: string): SseFrame | null {
  const lines = raw.split('\n')
  let event = ''
  const dataLines: string[] = []
  for (const line of lines) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''))
    }
  }
  if (!event || dataLines.length === 0) return null
  return { event, data: dataLines.join('\n') }
}

function dispatch(
  frame: SseFrame,
  callbacks: ChatStreamCallbacks,
): void {
  let parsed: Record<string, unknown>
  try {
    parsed = JSON.parse(frame.data) as Record<string, unknown>
  } catch {
    return // malformed payload — swallow
  }
  switch (frame.event) {
    case 'delta':
      callbacks.onDelta(String(parsed.text ?? ''))
      return
    case 'tool_call':
      callbacks.onToolCall({
        id: String(parsed.id ?? ''),
        name: String(parsed.name ?? ''),
        args: (parsed.args as Record<string, unknown>) ?? {},
      })
      return
    case 'tool_result':
      callbacks.onToolResult({
        tool_call_id: String(parsed.tool_call_id ?? ''),
        result: (parsed.result as Record<string, unknown>) ?? {},
      })
      return
    case 'done':
      callbacks.onDone({
        message_id: String(parsed.message_id ?? ''),
        elapsed_ms: Number(parsed.elapsed_ms ?? 0),
        cost_usd:
          parsed.cost_usd !== undefined ? Number(parsed.cost_usd) : undefined,
        input_tokens:
          parsed.input_tokens !== undefined
            ? Number(parsed.input_tokens)
            : undefined,
        output_tokens:
          parsed.output_tokens !== undefined
            ? Number(parsed.output_tokens)
            : undefined,
      })
      return
    case 'error':
      callbacks.onError({
        code: String(parsed.code ?? 'stream_failed'),
        message: String(parsed.message ?? ''),
      })
      return
  }
}

export async function streamChatMessage(
  sessionId: string,
  content: string,
  callbacks: ChatStreamCallbacks,
  signal: AbortSignal,
): Promise<void> {
  const token = useAuthStore.getState().token
  let response: Response
  try {
    response = await fetch(
      `/api/admin/chat/sessions/${encodeURIComponent(sessionId)}/messages`,
      {
        method: 'POST',
        signal,
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ content }),
      },
    )
  } catch (err) {
    if ((err as Error).name === 'AbortError') return
    callbacks.onError({
      code: 'stream_failed',
      message: (err as Error).message,
    })
    return
  }

  // Non-stream envelope path: server hit a pre-stream validation error.
  if (response.status !== 200) {
    try {
      const body = (await response.json()) as {
        ok: boolean
        error?: { code?: string; message?: string }
      }
      const err = body.error ?? { code: 'request_failed', message: '' }
      callbacks.onError({
        code: err.code ?? 'request_failed',
        message: err.message ?? `HTTP ${response.status}`,
      })
    } catch {
      callbacks.onError({
        code: 'request_failed',
        message: `HTTP ${response.status}`,
      })
    }
    return
  }

  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('text/event-stream')) {
    callbacks.onError({
      code: 'unexpected_content_type',
      message: `expected text/event-stream, got ${contentType || 'unknown'}`,
    })
    return
  }

  if (!response.body) {
    callbacks.onError({
      code: 'stream_failed',
      message: 'response has no body',
    })
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // Frames are separated by a blank line (\n\n).
      let separatorIdx = buffer.indexOf('\n\n')
      while (separatorIdx !== -1) {
        const rawFrame = buffer.slice(0, separatorIdx)
        buffer = buffer.slice(separatorIdx + 2)
        const frame = parseFrame(rawFrame)
        if (frame) dispatch(frame, callbacks)
        separatorIdx = buffer.indexOf('\n\n')
      }
    }
  } catch (err) {
    if ((err as Error).name === 'AbortError') return
    callbacks.onError({
      code: 'stream_failed',
      message: (err as Error).message,
    })
  }
}
