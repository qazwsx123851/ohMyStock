/**
 * /sessions — FTS5 search across all chat sessions.
 *
 * Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/web-admin-chat-pages/spec.md
 *
 * Visual contract: docs/web-admin-page-designs.md §15.
 *
 * - Big search input + two date pickers + 搜尋 button. Enter on input triggers.
 * - Results grouped by session_id. Each group is a Card with N highlighted snippets.
 * - Highlight uses `bg-warning/30` yellow (search convention; NOT a warning).
 * - Deleted sessions show "(已刪除)" badge + disabled 「開啟 →」 button.
 * - URL query string `?q=&from=&to=` persists across reloads.
 */

import * as React from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, ExternalLink, History, Search } from 'lucide-react'

import {
  ApiError,
  searchChat,
  type ChatSearchResult,
  type ChatSnippetHit,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'


/**
 * Render snippet HTML safely — the server already wrapped matches in
 * <mark>…</mark>, so we substitute them for styled spans and render the
 * rest as plain text. This avoids dangerouslySetInnerHTML.
 */
function HighlightedSnippet({ snippet }: { snippet: string }) {
  const parts: React.ReactNode[] = []
  const re = /<mark>(.*?)<\/mark>/g
  let last = 0
  let m: RegExpExecArray | null
  let key = 0
  while ((m = re.exec(snippet)) !== null) {
    if (m.index > last) {
      parts.push(snippet.slice(last, m.index))
    }
    parts.push(
      <mark
        key={key++}
        className="bg-warning/30 px-0.5 rounded text-foreground"
      >
        {m[1]}
      </mark>,
    )
    last = m.index + m[0].length
  }
  if (last < snippet.length) parts.push(snippet.slice(last))
  return <>{parts}</>
}


export function SessionsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  const urlQ = searchParams.get('q') ?? ''
  const urlFrom = searchParams.get('from') ?? ''
  const urlTo = searchParams.get('to') ?? ''

  const [q, setQ] = React.useState(urlQ)
  const [dateFrom, setDateFrom] = React.useState(urlFrom)
  const [dateTo, setDateTo] = React.useState(urlTo)

  const query = useQuery<ChatSearchResult, ApiError>({
    queryKey: ['chat-search', urlQ, urlFrom, urlTo],
    queryFn: () =>
      searchChat({
        q: urlQ,
        dateFrom: urlFrom || undefined,
        dateTo: urlTo || undefined,
        limit: 50,
      }),
    enabled: !!urlQ.trim(),
  })

  function commitSearch() {
    const next = new URLSearchParams()
    if (q.trim()) next.set('q', q.trim())
    if (dateFrom) next.set('from', dateFrom)
    if (dateTo) next.set('to', dateTo)
    setSearchParams(next, { replace: false })
  }

  function onSearchKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      commitSearch()
    }
  }

  const apiErr = query.error as ApiError | undefined

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">對話歷史搜尋</h1>

      <Card className="p-4 space-y-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground"
              aria-hidden="true"
            />
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={onSearchKey}
              placeholder="搜尋對話內容…"
              aria-label="搜尋"
              className="w-full pl-9 pr-3 py-2 rounded-md border bg-background text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <Button onClick={commitSearch} disabled={!q.trim()}>
            搜尋 (↩)
          </Button>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <label className="text-muted-foreground" htmlFor="date-from">
            日期：
          </label>
          <input
            id="date-from"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="rounded-md border bg-background px-2 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <span aria-hidden="true">~</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            aria-label="到"
            className="rounded-md border bg-background px-2 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </div>
      </Card>

      {/* Results */}
      {!urlQ.trim() && (
        <Card className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
          <Search className="size-8" aria-hidden="true" />
          <span>輸入關鍵字後按下搜尋或 Enter</span>
        </Card>
      )}

      {urlQ.trim() && query.isLoading && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      )}

      {urlQ.trim() && apiErr && (
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
              <div className="font-medium">
                {apiErr.code === 'invalid_query'
                  ? '查詢語法錯誤'
                  : apiErr.code === 'invalid_input'
                  ? '輸入不合法'
                  : '搜尋失敗'}
              </div>
              <div className="text-sm text-muted-foreground">
                {apiErr.message || apiErr.code}
              </div>
            </div>
            {apiErr.code !== 'invalid_query' &&
              apiErr.code !== 'invalid_input' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => query.refetch()}
                >
                  重試
                </Button>
              )}
          </div>
        </Card>
      )}

      {urlQ.trim() &&
        query.data &&
        query.data.total_hits === 0 && (
          <Card className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
            <History className="size-8" aria-hidden="true" />
            <span>無命中 — 試試其他關鍵字</span>
          </Card>
        )}

      {urlQ.trim() && query.data && query.data.total_hits > 0 && (
        <>
          <div className="text-sm text-muted-foreground">
            {query.data.groups.length} 個對話、{query.data.total_hits} 段命中
          </div>
          {query.data.groups.map((group) => {
            const isDeleted = group.session_status === 'deleted'
            return (
              <Card key={group.session_id} className="p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">
                      {group.session_title}
                    </span>
                    {isDeleted && (
                      <span className="text-xs text-muted-foreground">
                        (已刪除)
                      </span>
                    )}
                  </div>
                  {isDeleted ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled
                      aria-disabled="true"
                      title="此對話已刪除"
                    >
                      開啟 →
                    </Button>
                  ) : (
                    <Link to={`/chat/${group.session_id}`}>
                      <Button variant="ghost" size="sm">
                        開啟 →
                        <ExternalLink
                          className="size-3 ml-1"
                          aria-hidden="true"
                        />
                      </Button>
                    </Link>
                  )}
                </div>
                <ul className="space-y-1 text-sm">
                  {group.hits.map((hit) => (
                    <SnippetRow
                      key={hit.message_id}
                      hit={hit}
                      disabled={isDeleted}
                      onOpen={(messageId) =>
                        navigate(
                          `/chat/${group.session_id}?msgId=${messageId}`,
                        )
                      }
                    />
                  ))}
                </ul>
              </Card>
            )
          })}
        </>
      )}
    </div>
  )
}


function SnippetRow({
  hit,
  disabled,
  onOpen,
}: {
  hit: ChatSnippetHit
  disabled: boolean
  onOpen: (messageId: string) => void
}) {
  return (
    <li>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onOpen(hit.message_id)}
        className="w-full text-left rounded px-2 py-1 hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <div className="text-xs text-muted-foreground">
          {hit.created_at.slice(0, 16).replace('T', ' ')}
        </div>
        <div className="line-clamp-2">
          <HighlightedSnippet snippet={hit.snippet} />
        </div>
      </button>
    </li>
  )
}
