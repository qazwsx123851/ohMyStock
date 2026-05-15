import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest'

import { streamChatMessage } from '@/lib/chat-stream'
import { useAuthStore } from '@/stores'


function eventStreamResponse(body: string): Response {
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}


function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}


let fetchMock: Mock


beforeEach(() => {
  useAuthStore.getState().setToken('test-token-aaaaaaaaaaaaaaaaaaaaaaaa')
})


afterEach(() => {
  vi.restoreAllMocks()
})


function noopCallbacks() {
  return {
    onDelta: vi.fn(),
    onToolCall: vi.fn(),
    onToolResult: vi.fn(),
    onDone: vi.fn(),
    onError: vi.fn(),
  }
}


describe('streamChatMessage', () => {
  it('dispatches the five SSE event kinds in order', async () => {
    const sse = [
      'event: delta\ndata: {"text":"Hello"}\n\n',
      'event: delta\ndata: {"text":" world"}\n\n',
      'event: tool_call\ndata: {"id":"t1","name":"query_journal","args":{"symbol":"2330"}}\n\n',
      'event: tool_result\ndata: {"tool_call_id":"t1","result":{"rows":[]}}\n\n',
      'event: done\ndata: {"message_id":"msg_abc","elapsed_ms":42,"cost_usd":0.001}\n\n',
    ].join('')

    fetchMock = vi.fn(async () => eventStreamResponse(sse))
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)

    const cb = noopCallbacks()
    const ctrl = new AbortController()
    await streamChatMessage('chat_12345678', 'hi', cb, ctrl.signal)

    expect(cb.onDelta).toHaveBeenCalledTimes(2)
    expect(cb.onDelta).toHaveBeenNthCalledWith(1, 'Hello')
    expect(cb.onDelta).toHaveBeenNthCalledWith(2, ' world')
    expect(cb.onToolCall).toHaveBeenCalledTimes(1)
    expect(cb.onToolCall).toHaveBeenCalledWith({
      id: 't1',
      name: 'query_journal',
      args: { symbol: '2330' },
    })
    expect(cb.onToolResult).toHaveBeenCalledTimes(1)
    expect(cb.onDone).toHaveBeenCalledTimes(1)
    expect(cb.onError).not.toHaveBeenCalled()
  })

  it('routes a pre-stream envelope error to onError', async () => {
    fetchMock = vi.fn(async () =>
      jsonResponse(
        { ok: false, error: { code: 'missing_api_key', message: 'no key' } },
        422,
      ),
    )
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)

    const cb = noopCallbacks()
    await streamChatMessage(
      'chat_12345678',
      'hi',
      cb,
      new AbortController().signal,
    )

    expect(cb.onError).toHaveBeenCalledWith({
      code: 'missing_api_key',
      message: 'no key',
    })
    expect(cb.onDelta).not.toHaveBeenCalled()
  })

  it('flags non-SSE content types as unexpected_content_type', async () => {
    fetchMock = vi.fn(
      async () =>
        new Response('<html></html>', {
          status: 200,
          headers: { 'Content-Type': 'text/html' },
        }),
    )
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)

    const cb = noopCallbacks()
    await streamChatMessage(
      'chat_12345678',
      'hi',
      cb,
      new AbortController().signal,
    )

    expect(cb.onError).toHaveBeenCalledTimes(1)
    expect(cb.onError.mock.calls[0]?.[0]?.code).toBe('unexpected_content_type')
    expect(cb.onDelta).not.toHaveBeenCalled()
  })

  it('does not call onError on AbortError', async () => {
    const abortErr = Object.assign(new Error('abort'), { name: 'AbortError' })
    fetchMock = vi.fn(async () => {
      throw abortErr
    })
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)

    const cb = noopCallbacks()
    await streamChatMessage(
      'chat_12345678',
      'hi',
      cb,
      new AbortController().signal,
    )

    expect(cb.onError).not.toHaveBeenCalled()
  })

  it('sends the Bearer token from the auth store', async () => {
    const sse = 'event: done\ndata: {"message_id":"msg_x","elapsed_ms":1}\n\n'
    fetchMock = vi.fn(async () => eventStreamResponse(sse))
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)

    const cb = noopCallbacks()
    await streamChatMessage(
      'chat_12345678',
      'hi',
      cb,
      new AbortController().signal,
    )

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    const headers = init.headers as Record<string, string>
    expect(headers.Authorization).toMatch(/^Bearer /)
  })
})
