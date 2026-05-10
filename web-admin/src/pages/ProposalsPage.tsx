/**
 * /proposals — read-only list of every proposal across the 4 sub-locations.
 *
 * Layout: header → 6-tab status filter (segmented control) → 5-col DataTable.
 * Click row (or Tab + Enter) → /proposals/<slug>.
 *
 * Tab state persists in URL search params (`?status=approved`) so back/forward
 * navigation restores the view. The "全部" tab omits the param entirely.
 *
 * No SSE, no body preview — proposals don't change without an operator action.
 *
 * Spec: openspec/changes/admin-proposals-endpoints-and-pages/specs/web-admin-proposals-pages/spec.md
 */
import { useNavigate, useSearchParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, Inbox, PackageSearch } from 'lucide-react'
import {
  ApiError,
  listProposals,
  type Proposal,
  type ProposalStatus,
  type ProposalsListResponse,
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
const STATUS_PARAM = 'status'

type StatusFilter = 'all' | ProposalStatus

const TABS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'pending', label: 'pending' },
  { value: 'validating', label: 'validating' },
  { value: 'approved', label: 'approved' },
  { value: 'merged', label: 'merged' },
  { value: 'rejected', label: 'rejected' },
]

const VALID_STATUSES: ProposalStatus[] = [
  'pending',
  'validating',
  'approved',
  'merged',
  'rejected',
]

function parseStatusParam(raw: string | null): StatusFilter {
  if (!raw) return 'all'
  if (VALID_STATUSES.includes(raw as ProposalStatus)) {
    return raw as ProposalStatus
  }
  return 'all'
}

function StatusTabs({
  active,
  onChange,
}: {
  active: StatusFilter
  onChange: (next: StatusFilter) => void
}) {
  return (
    <div
      role="tablist"
      aria-label="按狀態過濾"
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

function TimeCell({ iso }: { iso: string }) {
  let display = iso
  try {
    display = new Date(iso).toLocaleString('zh-TW', { hour12: false })
  } catch {
    /* fall back */
  }
  return (
    <span className="whitespace-nowrap font-mono text-xs" title={iso}>
      {display}
    </span>
  )
}

const COLUMNS: DataTableColumn<Proposal>[] = [
  {
    id: 'created_at',
    header: '時間',
    accessor: (r) => <TimeCell iso={r.created_at} />,
  },
  {
    id: 'status',
    header: '狀態',
    accessor: (r) => <Badge variant="secondary">{r.status}</Badge>,
  },
  {
    id: 'topic',
    header: '主題',
    accessor: (r) => <span className="font-medium">{r.topic}</span>,
  },
  {
    id: 'target_section',
    header: 'Target section',
    accessor: (r) => (
      <span
        className="block max-w-[36ch] truncate text-sm text-muted-foreground"
        title={r.target_section}
      >
        {r.target_section || '—'}
      </span>
    ),
  },
  {
    id: 'priority',
    header: '優先級',
    accessor: (r) => <Badge variant="outline">{r.priority}</Badge>,
  },
]

function LoadingRows() {
  return (
    <Card className="overflow-hidden p-0" data-testid="proposals-loading">
      <div className="divide-y">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-4 py-3">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-4 w-40 flex-1" />
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-5 w-14" />
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
      <p className="text-sm text-muted-foreground">尚無提案</p>
    </Card>
  )
}

function EmptyForStatus({
  status,
  onResetAll,
}: {
  status: ProposalStatus
  onResetAll: () => void
}) {
  return (
    <Card className="flex flex-col items-center justify-center gap-3 p-12 text-center">
      <PackageSearch className="size-8 text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground">
        目前 <span className="font-mono">{status}</span> 沒有提案
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
    <Card
      role="alert"
      className="border-destructive/50 bg-destructive/5 p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="size-4" aria-hidden />
          <span>載入提案失敗 — {error.message}</span>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          重試
        </Button>
      </div>
    </Card>
  )
}

export function ProposalsPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const status: StatusFilter = parseStatusParam(searchParams.get(STATUS_PARAM))

  const setStatus = (next: StatusFilter) => {
    const params = new URLSearchParams(searchParams)
    if (next === 'all') {
      params.delete(STATUS_PARAM)
    } else {
      params.set(STATUS_PARAM, next)
    }
    setSearchParams(params, { replace: false })
  }

  const query = useQuery<ProposalsListResponse, ApiError>({
    queryKey: ['proposals', status],
    queryFn: () =>
      status === 'all'
        ? listProposals({ limit: PAGE_SIZE })
        : listProposals({ status, limit: PAGE_SIZE }),
    retry: false,
  })

  const items = query.data?.items ?? []
  const total = query.data?.total ?? 0

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Proposals</h1>
        <p className="text-sm text-muted-foreground">
          策略改動提案清單。狀態以 frontmatter 為準（不依賴所在資料夾）。
          {query.data && (
            <>
              {' '}
              共 {items.length}/{total} 筆。
            </>
          )}
        </p>
      </header>

      <StatusTabs active={status} onChange={setStatus} />

      {query.isLoading && <LoadingRows />}

      {query.error && (
        <ErrorPanel error={query.error} onRetry={() => query.refetch()} />
      )}

      {query.data && items.length === 0 && status === 'all' && <EmptyAll />}

      {query.data && items.length === 0 && status !== 'all' && (
        <EmptyForStatus
          status={status}
          onResetAll={() => setStatus('all')}
        />
      )}

      {query.data && items.length > 0 && (
        <DataTable<Proposal>
          rows={items}
          columns={COLUMNS}
          rowKey={(r) => r.slug}
          onRowClick={(r) => navigate(`/proposals/${r.slug}`)}
          skeletonRows={8}
        />
      )}
    </div>
  )
}
