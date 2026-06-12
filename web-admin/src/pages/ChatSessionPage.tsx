/**
 * /chat/:sessionId — streaming conversation view.
 *
 * Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/web-admin-chat-pages/spec.md
 *
 * Visual contract: docs/web-admin-page-designs.md §2.
 *
 * - Header: ← back / title / ⋮ menu (重命名 placeholder, 刪除 with confirm)
 * - Message stream: user (right) / assistant (left) / tool_call (inline)
 * - Streaming caret `▮` (decorative; aria-hidden); stream container has
 *   aria-live="polite" so screen readers announce incremental deltas.
 * - Bottom Textarea + 送出/停止 button. Cmd/Ctrl+Enter sends; Enter = newline.
 * - 404 → neutral NotFound view. 422 session_deleted → destructive Card + input hidden.
 */

import * as React from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  MessagesSquare,
  MoreVertical,
} from 'lucide-react'

import {
  ApiError,
  deleteChatSession,
  getChatSession,
  type ChatMessage as ApiChatMessage,
  type ChatSessionDetail,
} from '@/lib/api'
import { streamChatMessage } from '@/lib/chat-stream'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'


type StreamingMsg = {
  /** transient — replaced once server emits done {message_id} */
  tempId: string
  text: string
  toolCalls: Array<{ id: string; name: string; args: Record<string, unknown> }>
  toolResults: Record<string, Record<string, unknown>>
}


function MessageBubble({
  role,
  children,
}: {
  role: 'user' | 'assistant'
  children: React.ReactNode
}) {
  return (
    <div
      className={cn(
        'flex',
        role === 'user' ? 'justify-end' : 'justify-start',
      )}
    >
      <Card
        className={cn(
          'max-w-[80%] px-4 py-3 whitespace-pre-wrap',
          role === 'user' ? 'bg-muted' : 'bg-card',
        )}
      >
        {children}
      </Card>
    </div>
  )
}


function ToolBlock({
  name,
  args,
  result,
}: {
  name: string
  args: Record<string, unknown>
  result?: Record<string, unknown>
}) {
  const [open, setOpen] = React.useState(false)
  return (
    <div className="mt-2 rounded border bg-background/50 text-xs">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full flex items-center gap-1 px-2 py-1 cursor-pointer hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
      >
        {open ? (
          <ChevronDown className="size-3" aria-hidden="true" />
        ) : (
          <ChevronRight className="size-3" aria-hidden="true" />
        )}
        <span className="font-mono">⚙ {name}</span>
      </button>
      {open && (
        <div className="space-y-2 px-2 py-2 border-t">
          <div>
            <div className="text-muted-foreground mb-1">args</div>
            <pre className="overflow-auto rounded bg-muted p-2 text-[10px]">
              {JSON.stringify(args, null, 2)}
            </pre>
          </div>
          {result !== undefined && (
            <div>
              <div className="text-muted-foreground mb-1">result</div>
              <pre className="overflow-auto rounded bg-muted p-2 text-[10px] max-h-48">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}


function PersistedMessage({ msg }: { msg: ApiChatMessage }) {
  let toolCalls: Array<{
    id: string
    name: string
    args: Record<string, unknown>
  }> = []
  if (msg.tool_calls_json) {
    try {
      const parsed = JSON.parse(msg.tool_calls_json) as unknown
      if (Array.isArray(parsed)) {
        toolCalls = parsed as typeof toolCalls
      }
    } catch {
      // ignore malformed legacy rows
    }
  }
  if (msg.role === 'tool_result') {
    // Tool results are summarised inside the assistant bubble; skip stand-alone.
    return null
  }
  return (
    <MessageBubble role={msg.role === 'user' ? 'user' : 'assistant'}>
      <div>{msg.content || <span className="opacity-50">（空）</span>}</div>
      {toolCalls.map((tc) => (
        <ToolBlock key={tc.id} name={tc.name} args={tc.args} />
      ))}
    </MessageBubble>
  )
}


export function ChatSessionPage() {
  const { sessionId = '' } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [input, setInput] = React.useState('')
  const [streaming, setStreaming] =
    React.useState<StreamingMsg | null>(null)
  const [streamError, setStreamError] = React.useState<{
    code: string
    message: string
  } | null>(null)
  const [menuOpen, setMenuOpen] = React.useState(false)
  const [confirmDelete, setConfirmDelete] = React.useState(false)
  const abortRef = React.useRef<AbortController | null>(null)
  const scrollRef = React.useRef<HTMLDivElement | null>(null)

  const query = useQuery<ChatSessionDetail, ApiError>({
    queryKey: ['chat-session', sessionId],
    queryFn: () => getChatSession(sessionId),
    enabled: !!sessionId,
  })

  React.useEffect(() => {
    // Auto-scroll to bottom on data change or stream growth.
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [query.data, streaming])

  React.useEffect(() => {
    // Clean up an in-flight stream when the page unmounts.
    return () => abortRef.current?.abort()
  }, [])

  const isStreaming = streaming !== null

  function startStream() {
    if (isStreaming) return
    const content = input.trim()
    if (!content) return
    setInput('')
    setStreamError(null)

    const tempId = `temp_${Date.now().toString(16)}`
    const transient: StreamingMsg = {
      tempId,
      text: '',
      toolCalls: [],
      toolResults: {},
    }
    setStreaming(transient)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    streamChatMessage(
      sessionId,
      content,
      {
        onDelta: (delta) => {
          setStreaming((prev) =>
            prev ? { ...prev, text: prev.text + delta } : prev,
          )
        },
        onToolCall: (call) => {
          setStreaming((prev) =>
            prev
              ? {
                  ...prev,
                  toolCalls: [...prev.toolCalls, call],
                }
              : prev,
          )
        },
        onToolResult: (tr) => {
          setStreaming((prev) =>
            prev
              ? {
                  ...prev,
                  toolResults: {
                    ...prev.toolResults,
                    [tr.tool_call_id]: tr.result,
                  },
                }
              : prev,
          )
        },
        onDone: () => {
          setStreaming(null)
          queryClient.invalidateQueries({
            queryKey: ['chat-session', sessionId],
          })
          queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
        },
        onError: (err) => {
          setStreamError(err)
          setStreaming(null)
          // Restore the draft so the error card's「已保留你輸入的內容」holds
          // (input was cleared optimistically before the stream started).
          setInput(content)
          queryClient.invalidateQueries({
            queryKey: ['chat-session', sessionId],
          })
        },
      },
      ctrl.signal,
    )
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      startStream()
    }
  }

  function handleStop() {
    abortRef.current?.abort()
    abortRef.current = null
    setStreaming(null)
    queryClient.invalidateQueries({
      queryKey: ['chat-session', sessionId],
    })
  }

  async function handleDelete() {
    try {
      await deleteChatSession(sessionId)
      navigate('/chat')
    } catch {
      // soft fail — keep the page; user can retry
      setMenuOpen(false)
    }
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (query.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <div className="space-y-3">
          <Skeleton className="h-12 w-40" />
          <Skeleton className="h-24 w-[60%]" />
          <Skeleton className="h-12 w-40 ml-auto" />
        </div>
      </div>
    )
  }

  const apiErr = query.error as ApiError | undefined
  if (apiErr?.code === 'not_found') {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <MessagesSquare
          className="size-12 text-muted-foreground"
          aria-hidden="true"
        />
        <h1 className="text-lg font-medium">找不到對話</h1>
        <Link to="/chat" className="text-sm text-primary underline">
          ← 回到對話列表
        </Link>
      </div>
    )
  }
  if (apiErr?.code === 'session_deleted') {
    return (
      <div className="space-y-4">
        <Link
          to="/chat"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          回到對話列表
        </Link>
        <Card
          className="border-destructive p-4"
          role="alert"
          aria-live="polite"
        >
          <div className="flex items-start gap-2">
            <AlertCircle
              className="size-4 mt-0.5 text-destructive"
              aria-hidden="true"
            />
            <div>
              <div className="font-medium">此對話已刪除</div>
              <div className="text-sm text-muted-foreground">
                訊息保留以供搜尋與復盤，但無法繼續對話。
              </div>
            </div>
          </div>
        </Card>
      </div>
    )
  }
  if (query.error) {
    return (
      <Card
        className="border-destructive p-4"
        role="alert"
        aria-live="polite"
      >
        <div className="flex items-start gap-2">
          <AlertCircle
            className="size-4 mt-0.5 text-destructive"
            aria-hidden="true"
          />
          <div className="flex-1">
            <div className="font-medium">載入歷史訊息失敗</div>
            <div className="text-sm text-muted-foreground">
              {(query.error as ApiError | undefined)?.code ?? 'unknown'}
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => query.refetch()}
          >
            重試
          </Button>
        </div>
      </Card>
    )
  }

  const data = query.data!
  const messages = data.messages

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b pb-3">
        <div className="flex items-center gap-2 min-w-0">
          <Link to="/chat" aria-label="返回對話列表">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="size-4" aria-hidden="true" />
            </Button>
          </Link>
          <h1 className="text-lg font-medium truncate">
            {data.session.title}
          </h1>
        </div>
        <div className="relative">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label="對話選單"
            aria-expanded={menuOpen}
          >
            <MoreVertical className="size-4" aria-hidden="true" />
          </Button>
          {menuOpen && (
            <Card className="absolute right-0 mt-1 w-40 p-1 z-50">
              <button
                type="button"
                className="w-full text-left px-3 py-2 text-sm rounded hover:bg-muted cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => {
                  setMenuOpen(false)
                  alert('v0 尚未支援重新命名，請刪除重建')
                }}
              >
                重新命名
              </button>
              <button
                type="button"
                className="w-full text-left px-3 py-2 text-sm rounded hover:bg-muted text-destructive cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => {
                  setMenuOpen(false)
                  setConfirmDelete(true)
                }}
              >
                刪除對話
              </button>
            </Card>
          )}
        </div>
      </div>

      {confirmDelete && (
        <Card
          className="my-3 border-destructive p-3"
          role="alertdialog"
          aria-live="polite"
        >
          <div className="flex items-center justify-between gap-3 text-sm">
            <span>確定刪除此對話？訊息會保留以供搜尋。</span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setConfirmDelete(false)}
              >
                取消
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={handleDelete}
              >
                確定刪除
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Message stream */}
      <div
        ref={scrollRef}
        aria-live="polite"
        aria-atomic="false"
        className="flex-1 space-y-3 overflow-y-auto py-4"
      >
        {messages.length === 0 && !streaming && (
          <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
            <MessagesSquare className="size-8" aria-hidden="true" />
            <span>這是新對話 — 在下方輸入你的問題</span>
          </div>
        )}
        {messages.map((msg) => (
          <PersistedMessage key={msg.id} msg={msg} />
        ))}
        {streaming && (
          <MessageBubble role="assistant">
            <div>
              {streaming.text}
              <span
                aria-hidden="true"
                className="ml-1 inline-block w-2 align-baseline animate-pulse motion-reduce:animate-none"
              >
                ▮
              </span>
            </div>
            {streaming.toolCalls.map((tc) => (
              <ToolBlock
                key={tc.id}
                name={tc.name}
                args={tc.args}
                result={streaming.toolResults[tc.id]}
              />
            ))}
          </MessageBubble>
        )}
      </div>

      {/* Input area */}
      {streamError && (
        <Card
          className="mb-3 border-warning p-3 text-sm"
          role="alert"
          aria-live="polite"
        >
          <div className="flex items-start gap-2">
            <AlertTriangle
              className="size-4 mt-0.5 text-warning"
              aria-hidden="true"
            />
            <span>
              網路或服務異常（{streamError.code}）。已保留你輸入的內容，請重試。
            </span>
          </div>
        </Card>
      )}
      <div className="space-y-2 border-t pt-3">
        <textarea
          rows={3}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          disabled={isStreaming}
          placeholder="輸入訊息… Cmd/Ctrl+Enter 送出，Enter 換行"
          className="w-full resize-y rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          aria-label="訊息輸入"
        />
        <div className="flex justify-end">
          {isStreaming ? (
            <Button
              variant="destructive"
              onClick={handleStop}
              aria-label="abort streaming"
            >
              停止
            </Button>
          ) : (
            <Button
              onClick={startStream}
              disabled={!input.trim()}
              aria-label="送出訊息 (Cmd/Ctrl+Enter)"
            >
              送出 (⌘↩)
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
