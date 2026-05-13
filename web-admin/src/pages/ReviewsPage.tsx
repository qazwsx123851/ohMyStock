/**
 * /reviews — read-only list of every LLM post-trade review on disk.
 *
 * Layout: header → 5-tab kind filter (segmented control) → 7-col DataTable.
 * Click row (or Tab + Enter) → /reviews/<review_id>.
 *
 * Tab state persists in URL search params (`?kind=monthly`) so back/forward
 * navigation restores the view. The "全部" tab omits the param entirely.
 *
 * No SSE — review output is static once the pipeline completes (or crashes).
 *
 * Spec: openspec/changes/admin-reviews-endpoints-and-pages/specs/web-admin-reviews-pages/spec.md
 */
import { useNavigate, useSearchParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  Inbox,
  PackageSearch,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import {
  ApiError,
  listReviews,
  type ReviewKind,
  type ReviewSummary,
  type ReviewsListResponse,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  DataTable,
  type DataTableColumn,
} from '@/components/data-table'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 50
const KIND_PARAM = 'kind'

type KindFilter = 'all' | ReviewKind

const TABS: { value: KindFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'monthly', label: 'monthly' },
  { value: 'quarterly', label: 'quarterly' },
  { value: 'forced', label: 'forced' },
  { value: 'manual', label: 'manual' },
]

const VALID_KINDS: ReviewKind[] = ['monthly', 'quarterly', 'forced', 'manual']

function parseKindParam(raw: string | null): KindFilter {
  if (!raw) return 'all'
  if (VALID_KINDS.includes(raw as ReviewKind)) return raw as ReviewKind
  return 'all'
}

function KindTabs({
  active,
  onChange,
}: {
  active: KindFilter
  onChange: (next: KindFilter) => void
}) {
  return (
    <div
      role="tablist"
      aria-label="按 kind 過濾"
      className="inline-flex flex-wrap rounded-md border border-input bg-muted/40 p-1"
    >
      {TABS.map((t) => {
        const selected = active === t.value
        return (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(t.value)}
            className={cn(
              'cursor-pointer rounded px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              selected
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

function CompletedAtCell({ iso }: { iso: string }) {
  const dateOnly = iso.slice(0, 10)
  return (
    <span className="whitespace-nowrap font-mono text-xs" title={iso}>
      {dateOnly}
    </span>
  )
}

function WinRateCell({ value }: { value: number }) {
  const up = value >= 0.5
  const Icon = up ? TrendingUp : TrendingDown
  return (
    <span
      className={cn(
        'inline-flex items-center justify-end gap-1 tabular',
        up ? 'text-up' : 'text-down',
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      <span>{(value * 100).toFixed(1)}%</span>
    </span>
  )
}

function PfCell({ value }: { value: number }) {
  const up = value >= 1
  const Icon = up ? TrendingUp : TrendingDown
  return (
    <span
      className={cn(
        'inline-flex items-center justify-end gap-1 tabular',
        up ? 'text-up' : 'text-down',
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      <span>{value.toFixed(2)}</span>
    </span>
  )
}

const COLUMNS: DataTableColumn<ReviewSummary>[] = [
  {
    id: 'completed_at',
    header: '完成時間',
    accessor: (r) => <CompletedAtCell iso={r.completed_at} />,
  },
  {
    id: 'review_id',
    header: 'Review ID',
    accessor: (r) => (
      <span
        className="block max-w-[36ch] truncate font-medium"
        title={r.review_id}
      >
        {r.review_id}
      </span>
    ),
  },
  {
    id: 'kind',
    header: 'Kind',
    accessor: (r) => <Badge variant="secondary">{r.kind}</Badge>,
  },
  {
    id: 'period',
    header: 'Period',
    accessor: (r) => (
      <span className="whitespace-nowrap font-mono text-xs text-muted-foreground">
        {r.period.from.slice(5)} → {r.period.to.slice(5)}
      </span>
    ),
  },
  {
    id: 'trade_count',
    header: '筆數',
    align: 'right',
    accessor: (r) => <span className="tabular">{r.trade_count}</span>,
  },
  {
    id: 'win_rate',
    header: 'Win Rate',
    align: 'right',
    accessor: (r) => <WinRateCell value={r.win_rate} />,
  },
  {
    id: 'pf',
    header: 'PF',
    align: 'right',
    accessor: (r) => <PfCell value={r.pf} />,
  },
]

function LoadingRows() {
  return (
    <Card className="overflow-hidden p-0" data-testid="reviews-loading">
      <div className="divide-y">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-4 py-3">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-40 flex-1" />
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-10" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-14" />
          </div>
        ))}
      </div>
    </Card>
  )
}

function EmptyAll() {
  return (
    <Card className="flex flex-col items-center justify-center gap-2 p-12 text-center">
      <Inbox className="size-8 text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground">
        尚無 review;執行{' '}
        <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
          uv run ohmystock review --from ... --to ...
        </code>{' '}
        產出第一份。
      </p>
    </Card>
  )
}

function EmptyForKind({
  kind,
  onResetAll,
}: {
  kind: ReviewKind
  onResetAll: () => void
}) {
  return (
    <Card className="flex flex-col items-center justify-center gap-3 p-12 text-center">
      <PackageSearch className="size-8 text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground">
        目前 <span className="font-mono">{kind}</span> 沒有 review
      </p>
      <Button variant="outline" size="sm" onClick={onResetAll}>
        回到全部
      </Button>
    </Card>
  )
}

function ErrorPanel({
  error,
  onRetry,
}: {
  error: ApiError
  onRetry: () => void
}) {
  return (
    <Card role="alert" className="border-destructive/50 bg-destructive/5 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="size-4" aria-hidden />
          <span>載入 review 失敗 — {error.message}</span>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          重試
        </Button>
      </div>
    </Card>
  )
}

export function ReviewsPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const kind: KindFilter = parseKindParam(searchParams.get(KIND_PARAM))

  const setKind = (next: KindFilter) => {
    const params = new URLSearchParams(searchParams)
    if (next === 'all') {
      params.delete(KIND_PARAM)
    } else {
      params.set(KIND_PARAM, next)
    }
    setSearchParams(params, { replace: false })
  }

  const query = useQuery<ReviewsListResponse, ApiError>({
    queryKey: ['reviews', kind],
    queryFn: () =>
      kind === 'all'
        ? listReviews({ limit: PAGE_SIZE })
        : listReviews({ kind, limit: PAGE_SIZE }),
    retry: false,
  })

  const items = query.data?.items ?? []
  const total = query.data?.total ?? 0

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Reviews</h1>
        <p className="text-sm text-muted-foreground">
          LLM 復盤 swarm 的歷史輸出。每份 review 來自{' '}
          <code className="font-mono text-xs">reviews/&lt;review_id&gt;/</code>。
          {query.data && (
            <>
              {' '}
              共 {items.length}/{total} 筆。
            </>
          )}
        </p>
      </header>

      <KindTabs active={kind} onChange={setKind} />

      {query.isLoading && <LoadingRows />}

      {query.error && (
        <ErrorPanel error={query.error} onRetry={() => query.refetch()} />
      )}

      {query.data && items.length === 0 && kind === 'all' && <EmptyAll />}

      {query.data && items.length === 0 && kind !== 'all' && (
        <EmptyForKind kind={kind} onResetAll={() => setKind('all')} />
      )}

      {query.data && items.length > 0 && (
        <DataTable<ReviewSummary>
          rows={items}
          columns={COLUMNS}
          rowKey={(r) => r.review_id}
          onRowClick={(r) => navigate(`/reviews/${r.review_id}`)}
          skeletonRows={8}
        />
      )}
    </div>
  )
}
