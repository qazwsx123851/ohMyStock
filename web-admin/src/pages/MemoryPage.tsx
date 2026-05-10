/**
 * /memory — read-only browse + search over the memory_rows store.
 *
 * Two views toggled by a segmented control:
 *   - 「瀏覽」: kind <select> + 1-tag chip-input + 5-col DataTable +
 *     inline expand showing full content + recency-sorted pagination.
 *   - 「搜尋」: single FTS5 input + Cmd/Ctrl+Enter / Enter / 「搜尋」 button +
 *     same DataTable in BM25 order.
 *
 * Loading / empty / error states delegate to DataTable's built-in slots
 * (Skeleton rows, Card with destructive border + AlertCircle, centred
 * empty message). Filter changes reset offset to 0 and collapse the
 * expanded row. Tab switch also collapses the expanded row.
 *
 * v0 deliberately ships NO insert/edit, NO date-range, NO tag autocomplete,
 * NO semantic search — see proposal "Out of scope" + design D13.
 *
 * Spec: openspec/changes/web-admin-memory-page-and-store/specs/web-admin-memory-page/spec.md
 */
import * as React from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, X } from 'lucide-react'
import {
  ApiError,
  listMemory,
  searchMemory,
  type MemoryKind,
  type MemoryRow,
  type MemoryRowsResponse,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  DataTable,
  type DataTableColumn,
} from '@/components/data-table'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 50

const KIND_LABELS: Record<MemoryKind, string> = {
  note: '筆記',
  lesson: '經驗',
  proposal: '提案',
  review_summary: '復盤',
}

type KindFilter = 'all' | MemoryKind

const KIND_OPTIONS: { value: KindFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'note', label: '筆記' },
  { value: 'lesson', label: '經驗' },
  { value: 'proposal', label: '提案' },
  { value: 'review_summary', label: '復盤' },
]

type Mode = 'browse' | 'search'

// ---------------------------------------------------------------------------
// Mode toggle (segmented control)
// ---------------------------------------------------------------------------

function ModeToggle({
  mode,
  onChange,
}: {
  mode: Mode
  onChange: (m: Mode) => void
}) {
  const tabs: { value: Mode; label: string }[] = [
    { value: 'browse', label: '瀏覽' },
    { value: 'search', label: '搜尋' },
  ]
  return (
    <div
      role="tablist"
      aria-label="檢視模式"
      className="inline-flex rounded-md border border-input bg-muted/40 p-1"
    >
      {tabs.map((t) => {
        const active = mode === t.value
        return (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={active}
            aria-controls={`memory-${t.value}-panel`}
            onClick={() => onChange(t.value)}
            className={cn(
              'cursor-pointer rounded px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              active
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
          </button>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tag chip-input (single tag for v0)
// ---------------------------------------------------------------------------

function TagChipInput({
  tag,
  onChange,
  disabled,
}: {
  tag: string | null
  onChange: (next: string | null) => void
  disabled?: boolean
}) {
  const [draft, setDraft] = React.useState('')

  if (tag) {
    return (
      <div className="inline-flex items-center gap-1 rounded-md border border-input bg-muted/40 px-2 py-1 text-sm">
        <code className="font-mono text-xs">{tag}</code>
        <button
          type="button"
          aria-label={`移除 tag ${tag}`}
          onClick={() => onChange(null)}
          disabled={disabled}
          className="cursor-pointer rounded text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
        >
          <X className="size-3" aria-hidden />
        </button>
      </div>
    )
  }

  return (
    <input
      type="text"
      placeholder="輸入 tag 後按 Enter"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          const trimmed = draft.trim()
          if (trimmed) {
            onChange(trimmed)
            setDraft('')
          }
        }
      }}
      disabled={disabled}
      aria-label="按 tag 過濾"
      className="block w-48 rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
    />
  )
}

// ---------------------------------------------------------------------------
// Shared row pieces
// ---------------------------------------------------------------------------

function KindBadge({ kind }: { kind: MemoryKind }) {
  return <Badge variant="secondary">{KIND_LABELS[kind]}</Badge>
}

function TagsCell({ tags }: { tags: string[] }) {
  if (!tags.length) return <span className="text-muted-foreground">—</span>
  return (
    <div className="flex flex-wrap gap-1">
      {tags.map((t) => (
        <code
          key={t}
          className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs"
        >
          {t}
        </code>
      ))}
    </div>
  )
}

function PreviewCell({ row }: { row: MemoryRow }) {
  const text = row.content_truncated
    ? `${row.content_preview}…`
    : row.content_preview
  return (
    <span className="block max-w-[42ch] truncate text-sm" title={text}>
      {text}
    </span>
  )
}

function SourceCell({ source }: { source: string | null }) {
  if (!source) return <span className="text-muted-foreground">—</span>
  return <span className="font-mono text-xs">{source}</span>
}

function TimeCell({ createdAt }: { createdAt: string }) {
  // Display in local time but keep ISO string in title for precision.
  let display = createdAt
  try {
    display = new Date(createdAt).toLocaleString('zh-TW', { hour12: false })
  } catch {
    /* fall back to raw ISO */
  }
  return (
    <span className="whitespace-nowrap font-mono text-xs" title={createdAt}>
      {display}
    </span>
  )
}

const COLUMNS: DataTableColumn<MemoryRow>[] = [
  {
    id: 'time',
    header: '時間',
    accessor: (r) => <TimeCell createdAt={r.created_at} />,
  },
  {
    id: 'kind',
    header: 'Kind',
    accessor: (r) => <KindBadge kind={r.kind} />,
  },
  {
    id: 'tags',
    header: 'Tags',
    accessor: (r) => <TagsCell tags={r.tags} />,
  },
  {
    id: 'preview',
    header: '內容預覽',
    accessor: (r) => <PreviewCell row={r} />,
  },
  {
    id: 'source',
    header: '來源',
    accessor: (r) => <SourceCell source={r.source} />,
  },
]

function ExpandedContent({ row }: { row: MemoryRow }) {
  return (
    <div className="space-y-2 p-2">
      <p className="text-xs text-muted-foreground">
        {row.content.length} 字元
      </p>
      <Card className="p-3">
        <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap font-mono text-sm">
          {row.content}
        </pre>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Error / inline error
// ---------------------------------------------------------------------------

function ErrorCard({
  error,
  onRetry,
}: {
  error: ApiError
  onRetry: () => void
}) {
  return (
    <Card
      role="alert"
      className="border-destructive/50 bg-destructive/5 p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="size-4" aria-hidden />
          <span>載入失敗 — {error.message}</span>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          重試
        </Button>
      </div>
    </Card>
  )
}

function InlineQuerySyntaxError() {
  return (
    <Card
      role="alert"
      className="border-destructive/50 bg-destructive/5 p-4"
    >
      <div className="flex items-center gap-2 text-sm text-destructive">
        <AlertCircle className="size-4" aria-hidden />
        <span>查詢語法錯誤</span>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Browse view
// ---------------------------------------------------------------------------

function BrowseView() {
  const [kind, setKind] = React.useState<KindFilter>('all')
  const [tag, setTag] = React.useState<string | null>(null)
  const [offset, setOffset] = React.useState(0)

  // Reset offset whenever filter changes.
  const setKindAndReset = (next: KindFilter) => {
    setKind(next)
    setOffset(0)
  }
  const setTagAndReset = (next: string | null) => {
    setTag(next)
    setOffset(0)
  }

  const q = useQuery<MemoryRowsResponse, ApiError>({
    queryKey: ['memory', 'rows', kind, tag, offset],
    queryFn: () =>
      listMemory({
        kind: kind === 'all' ? undefined : kind,
        tag: tag ?? undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    retry: false,
  })

  const isFiltered = kind !== 'all' || tag !== null
  const items = q.data?.items ?? []
  const total = q.data?.total ?? 0
  const page = Math.floor(offset / PAGE_SIZE) + 1

  const onPageChange = (next: number) => {
    setOffset(Math.max(0, (next - 1) * PAGE_SIZE))
  }

  const handleClearFilter = () => {
    setKind('all')
    setTag(null)
    setOffset(0)
  }

  return (
    <section
      id="memory-browse-panel"
      role="tabpanel"
      aria-labelledby="memory-browse-tab"
      className="space-y-3"
    >
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Kind</span>
          <select
            value={kind}
            onChange={(e) => setKindAndReset(e.target.value as KindFilter)}
            disabled={q.isLoading}
            aria-label="按 kind 過濾"
            className="block rounded-md border border-input bg-background px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
          >
            {KIND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Tag</span>
          <TagChipInput
            tag={tag}
            onChange={setTagAndReset}
            disabled={q.isLoading}
          />
        </label>
      </div>

      {q.error ? (
        <ErrorCard error={q.error} onRetry={() => q.refetch()} />
      ) : items.length === 0 && !q.isLoading ? (
        isFiltered ? (
          <Card className="p-8 text-center text-sm text-muted-foreground">
            <p>無符合條件的 memory</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={handleClearFilter}
            >
              清除 filter
            </Button>
          </Card>
        ) : (
          <Card className="p-8 text-center text-sm text-muted-foreground">
            尚無 memory；待 Phase 5 復盤 / proposal 任務寫入
          </Card>
        )
      ) : (
        <DataTable<MemoryRow>
          rows={items}
          columns={COLUMNS}
          loading={q.isLoading}
          rowKey={(r) => r.id}
          onRowClick={() => {
            /* expansion handled by DataTable internal state */
          }}
          expandedRowRender={(row) => <ExpandedContent row={row} />}
          pageSize={PAGE_SIZE}
          total={total}
          page={page}
          onPageChange={onPageChange}
          skeletonRows={6}
        />
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Search view
// ---------------------------------------------------------------------------

function SearchView() {
  const [draft, setDraft] = React.useState('')
  const [submittedQ, setSubmittedQ] = React.useState('')
  const [offset, setOffset] = React.useState(0)

  const trimmedDraft = draft.trim()

  const q = useQuery<MemoryRowsResponse, ApiError>({
    queryKey: ['memory', 'search', submittedQ, offset],
    queryFn: () =>
      searchMemory({ q: submittedQ, limit: PAGE_SIZE, offset }),
    enabled: submittedQ.trim().length > 0,
    retry: false,
  })

  const submit = () => {
    if (!trimmedDraft) return
    setOffset(0)
    setSubmittedQ(trimmedDraft)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    // Cmd+Enter, Ctrl+Enter, or plain Enter all submit.
    if (e.key === 'Enter') {
      e.preventDefault()
      submit()
    }
  }

  const items = q.data?.items ?? []
  const total = q.data?.total ?? 0
  const page = Math.floor(offset / PAGE_SIZE) + 1
  const onPageChange = (next: number) => {
    setOffset(Math.max(0, (next - 1) * PAGE_SIZE))
  }

  const isInvalidQuery = q.error?.code === 'invalid_query'

  return (
    <section
      id="memory-search-panel"
      role="tabpanel"
      aria-labelledby="memory-search-tab"
      className="space-y-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="FTS5 查詢，例：VCP AND breakout"
          aria-label="FTS5 查詢"
          disabled={q.isLoading}
          className="block w-80 max-w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
        />
        <Button
          type="button"
          size="sm"
          onClick={submit}
          disabled={q.isLoading || trimmedDraft.length === 0}
        >
          搜尋
        </Button>
        <span className="text-xs text-muted-foreground">
          按 Enter 或 ⌘/Ctrl+Enter 送出
        </span>
      </div>

      {isInvalidQuery ? (
        <InlineQuerySyntaxError />
      ) : q.error ? (
        <ErrorCard error={q.error} onRetry={() => q.refetch()} />
      ) : submittedQ.trim().length === 0 ? (
        <Card className="p-8 text-center text-sm text-muted-foreground">
          請輸入查詢關鍵字
        </Card>
      ) : items.length === 0 && !q.isLoading ? (
        <Card className="p-8 text-center text-sm text-muted-foreground">
          找不到符合「{submittedQ}」的 memory
        </Card>
      ) : (
        <DataTable<MemoryRow>
          rows={items}
          columns={COLUMNS}
          loading={q.isLoading}
          rowKey={(r) => r.id}
          onRowClick={() => {
            /* expansion handled by DataTable internal state */
          }}
          expandedRowRender={(row) => <ExpandedContent row={row} />}
          pageSize={PAGE_SIZE}
          total={total}
          page={page}
          onPageChange={onPageChange}
          skeletonRows={6}
        />
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// MemoryPage
// ---------------------------------------------------------------------------

export function MemoryPage() {
  const [mode, setMode] = React.useState<Mode>('browse')

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">長期記憶</h1>
        <p className="text-sm text-muted-foreground">
          僅供瀏覽。內容由 Phase 5 復盤與 proposal 任務寫入；本頁不提供新增 / 編輯 / 刪除。
        </p>
      </header>

      {/* Re-mounting on mode change forces DataTable internal state
          (e.g. expandedKey) to reset, satisfying the spec's
          "switching tab collapses the expanded row" scenario. */}
      <ModeToggle mode={mode} onChange={setMode} />
      {mode === 'browse' ? (
        <BrowseView key="browse" />
      ) : (
        <SearchView key="search" />
      )}
    </div>
  )
}
