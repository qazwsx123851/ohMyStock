import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import {
  AlertCircle,
  Download,
  ReceiptText,
  RefreshCcw,
  Rows3,
  Rows4,
} from 'lucide-react'
import dayjs from 'dayjs'
import { apiFetch, type JournalRow, type PaginatedRows } from '@/lib/api'
import { JOURNAL_KIND_ALL, type JournalKind } from '@/lib/journal-kinds'
import {
  DataTable,
  type DataTableColumn,
  type Density,
} from '@/components/data-table'
import { StatusBadge, type Status } from '@/components/status-badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const ALL_KINDS: JournalKind[] = [...JOURNAL_KIND_ALL]
const PAGE_SIZE = 50
const totalFmt = new Intl.NumberFormat('zh-TW')

type AppliedFilter = {
  kinds: JournalKind[]
  symbol: string
  decisionId: string
  dateFrom: string
  dateTo: string
  page: number
  density: Density
}

function readFilter(sp: URLSearchParams): AppliedFilter {
  const rawKinds = sp.getAll('kind').filter((k): k is JournalKind =>
    ALL_KINDS.includes(k as JournalKind),
  )
  const density: Density =
    sp.get('density') === 'comfortable' ? 'comfortable' : 'compact'
  return {
    kinds: rawKinds.length > 0 ? rawKinds : ALL_KINDS,
    symbol: sp.get('symbol') ?? '',
    decisionId: sp.get('decision_id') ?? '',
    dateFrom: sp.get('date_from') ?? '',
    dateTo: sp.get('date_to') ?? '',
    page: Math.max(1, parseInt(sp.get('page') ?? '1', 10) || 1),
    density,
  }
}

function buildPath(f: AppliedFilter): string {
  const qs = new URLSearchParams()
  for (const k of f.kinds) qs.append('kind', k)
  if (f.symbol) qs.set('symbol', f.symbol)
  if (f.decisionId) qs.set('decision_id', f.decisionId)
  if (f.dateFrom) qs.set('date_from', f.dateFrom)
  if (f.dateTo) qs.set('date_to', f.dateTo)
  qs.set('limit', String(PAGE_SIZE))
  qs.set('offset', String((f.page - 1) * PAGE_SIZE))
  return `/api/admin/journal/rows?${qs.toString()}`
}

function inferStatus(row: JournalRow): Status {
  if (row.status) {
    const s = row.status.toLowerCase()
    if (
      s === 'pending' ||
      s === 'approved' ||
      s === 'rejected' ||
      s === 'executed' ||
      s === 'expired' ||
      s === 'canceled' ||
      s === 'errored'
    ) {
      return s as Status
    }
  }
  switch (row.kind) {
    case 'entry':
    case 'fill':
    case 'exit':
    case 'confirm_received':
      return 'executed'
    case 'reject':
    case 'confirm_rejected':
      return 'rejected'
    case 'risk_off_triggered':
    case 'breaker_tripped':
      return 'errored'
    case 'awaiting_confirm':
    case 'decider_thinking':
      return 'pending'
    case 'decision_made':
      return 'approved'
    default:
      return 'pending'
  }
}

function summarisePayload(row: JournalRow): string {
  const p = row.payload ?? {}
  const side = p.side as string | undefined
  const qty = p.qty as number | undefined
  const price = (p.price ?? p.actual_entry_price) as number | undefined
  const reason = (p.reason ?? p.message) as string | undefined
  const conf = p.confidence as number | undefined

  if (qty != null && price != null) {
    return `${side === 'long' ? '多' : side === 'short' ? '空' : ''} ${qty}@${price}`.trim()
  }
  if (conf != null) return `conf=${conf.toFixed(2)}`
  if (reason) return reason
  const keys = Object.keys(p)
  return keys.length > 0 ? keys.slice(0, 2).join(', ') : '—'
}

const COLUMNS: DataTableColumn<JournalRow>[] = [
  {
    id: 'time',
    header: '時間',
    accessor: (r) => (
      <span className="tabular text-xs">
        {dayjs(r.created_at).format('MM-DD HH:mm:ss')}
      </span>
    ),
  },
  {
    id: 'kind',
    header: 'Kind',
    accessor: (r) => <span className="font-mono text-xs">{r.kind}</span>,
  },
  { id: 'symbol', header: 'Symbol', accessor: (r) => r.symbol ?? '—' },
  {
    id: 'decision_id',
    header: 'Decision id',
    accessor: (r) => (
      <span className="font-mono text-[11px] text-muted-foreground">
        {r.decision_id ?? '—'}
      </span>
    ),
  },
  {
    id: 'status',
    header: '狀態',
    accessor: (r) => <StatusBadge status={inferStatus(r)} />,
  },
  {
    id: 'summary',
    header: '摘要',
    accessor: (r) => (
      <span className="truncate text-xs text-muted-foreground">
        {summarisePayload(r)}
      </span>
    ),
  },
]

function rowsToJsonl(rows: JournalRow[]): string {
  return rows.map((r) => JSON.stringify(r)).join('\n')
}

function downloadBlob(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function FilterBar({
  applied,
  onApply,
  onClear,
  onExport,
  onToggleDensity,
  exportCount,
}: {
  applied: AppliedFilter
  onApply: (next: Omit<AppliedFilter, 'page' | 'density'>) => void
  onClear: () => void
  onExport: () => void
  onToggleDensity: () => void
  exportCount: number
}) {
  const [pendingKinds, setPendingKinds] = useState<JournalKind[]>(applied.kinds)
  const [pendingSymbol, setPendingSymbol] = useState(applied.symbol)
  const [pendingDecisionId, setPendingDecisionId] = useState(applied.decisionId)
  const [pendingFrom, setPendingFrom] = useState(applied.dateFrom)
  const [pendingTo, setPendingTo] = useState(applied.dateTo)

  useEffect(() => {
    setPendingKinds(applied.kinds)
    setPendingSymbol(applied.symbol)
    setPendingDecisionId(applied.decisionId)
    setPendingFrom(applied.dateFrom)
    setPendingTo(applied.dateTo)
  }, [
    applied.kinds,
    applied.symbol,
    applied.decisionId,
    applied.dateFrom,
    applied.dateTo,
  ])

  const toggleKind = (k: JournalKind) => {
    setPendingKinds((prev) =>
      prev.includes(k) ? prev.filter((x) => x !== k) : [...prev, k],
    )
  }

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-end gap-3 text-xs">
        <div className="space-y-1">
          <div className="font-medium text-muted-foreground">Kind</div>
          <div className="flex max-w-3xl flex-wrap items-center gap-x-3 gap-y-1">
            {ALL_KINDS.map((k) => (
              <label key={k} className="inline-flex items-center gap-1.5">
                <input
                  type="checkbox"
                  name={k}
                  checked={pendingKinds.includes(k)}
                  onChange={() => toggleKind(k)}
                  className="size-3.5"
                />
                <span className="font-mono text-[11px]">{k}</span>
              </label>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-3 text-xs">
        <label className="space-y-1">
          <div className="font-medium text-muted-foreground">Symbol</div>
          <input
            type="text"
            value={pendingSymbol}
            onChange={(e) => setPendingSymbol(e.target.value)}
            placeholder="2330"
            className="h-8 w-28 rounded-md border bg-background px-2 text-xs"
          />
        </label>
        <label className="space-y-1">
          <div className="font-medium text-muted-foreground">Decision id</div>
          <input
            type="text"
            value={pendingDecisionId}
            onChange={(e) => setPendingDecisionId(e.target.value)}
            placeholder="d-129"
            className="h-8 w-32 rounded-md border bg-background px-2 text-xs"
          />
        </label>
        <label className="space-y-1">
          <div className="font-medium text-muted-foreground">日期 from</div>
          <input
            type="date"
            value={pendingFrom}
            onChange={(e) => setPendingFrom(e.target.value)}
            className="h-8 rounded-md border bg-background px-2 text-xs"
          />
        </label>
        <label className="space-y-1">
          <div className="font-medium text-muted-foreground">日期 to</div>
          <input
            type="date"
            value={pendingTo}
            onChange={(e) => setPendingTo(e.target.value)}
            className="h-8 rounded-md border bg-background px-2 text-xs"
          />
        </label>
        <div className="ml-auto flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            onClick={() =>
              onApply({
                kinds: pendingKinds,
                symbol: pendingSymbol.trim(),
                decisionId: pendingDecisionId.trim(),
                dateFrom: pendingFrom,
                dateTo: pendingTo,
              })
            }
          >
            套用
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onClear}>
            清空
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={exportCount === 0}
            onClick={onExport}
            title="僅匯出當前頁；需要全部請查 sqlite journal_entries"
          >
            <Download className="size-3" aria-hidden />
            匯出本頁 {exportCount} 列 JSONL
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onToggleDensity}
            aria-label="切換密度"
          >
            {applied.density === 'compact' ? (
              <>
                <Rows3 className="size-3" aria-hidden />
                compact
              </>
            ) : (
              <>
                <Rows4 className="size-3" aria-hidden />
                comfortable
              </>
            )}
          </Button>
        </div>
      </div>
    </Card>
  )
}

function EmptyState({ onClear }: { onClear: () => void }) {
  return (
    <Card className="p-8 text-center">
      <ReceiptText
        className="mx-auto size-8 text-muted-foreground"
        aria-hidden
      />
      <h3 className="mt-3 text-sm font-medium">此 filter 無紀錄</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        試試調整 kind / symbol / decision_id / 日期。
      </p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-4"
        onClick={onClear}
      >
        清空 filter
      </Button>
    </Card>
  )
}

function ErrorState({
  error,
  onRetry,
}: {
  error: Error
  onRetry: () => void
}) {
  return (
    <Card className="border-destructive/50 p-6">
      <div className="flex items-start gap-3">
        <AlertCircle className="size-5 shrink-0 text-destructive" aria-hidden />
        <div className="flex-1 text-sm">
          <p className="font-medium">載入失敗</p>
          <p className="mt-1 text-muted-foreground">{error.message}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={onRetry}
          >
            <RefreshCcw className="size-3" aria-hidden />
            重試
          </Button>
        </div>
      </div>
    </Card>
  )
}

function LoadingTable() {
  return (
    <Card className="p-4">
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-5 w-full" />
        ))}
      </div>
    </Card>
  )
}

function expandedPayload(row: JournalRow) {
  return (
    <pre
      data-testid="audit-row-expanded"
      className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-card p-2 text-[11px] leading-tight"
    >
      {JSON.stringify(
        {
          id: row.id,
          decision_id: row.decision_id,
          kind: row.kind,
          symbol: row.symbol,
          created_at: row.created_at,
          status: row.status,
          payload: row.payload,
        },
        null,
        2,
      )}
    </pre>
  )
}

export function AuditPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const applied = useMemo(() => readFilter(searchParams), [searchParams])

  const path = buildPath(applied)
  const { data, isLoading, error, refetch, isPlaceholderData } = useQuery({
    queryKey: ['admin', 'journal', 'rows', 'audit', path],
    queryFn: () => apiFetch<PaginatedRows<JournalRow>>(path),
    refetchInterval: 60_000,
    placeholderData: keepPreviousData,
  })

  const onApply = (next: Omit<AppliedFilter, 'page' | 'density'>) => {
    const sp = new URLSearchParams()
    for (const k of next.kinds) sp.append('kind', k)
    if (next.symbol) sp.set('symbol', next.symbol)
    if (next.decisionId) sp.set('decision_id', next.decisionId)
    if (next.dateFrom) sp.set('date_from', next.dateFrom)
    if (next.dateTo) sp.set('date_to', next.dateTo)
    if (applied.density === 'comfortable') sp.set('density', 'comfortable')
    sp.set('page', '1')
    setSearchParams(sp)
  }
  const onClear = () => setSearchParams(new URLSearchParams())
  const setPage = (page: number) => {
    const sp = new URLSearchParams(searchParams)
    sp.set('page', String(page))
    setSearchParams(sp)
  }
  const onToggleDensity = () => {
    const sp = new URLSearchParams(searchParams)
    if (applied.density === 'compact') sp.set('density', 'comfortable')
    else sp.delete('density')
    setSearchParams(sp)
  }

  const items = data?.items ?? []
  const total = data?.total ?? 0

  const onExport = () => {
    if (items.length === 0) return
    const stamp = dayjs().format('YYYYMMDD-HHmmss')
    downloadBlob(
      `audit-${stamp}.jsonl`,
      rowsToJsonl(items),
      'application/x-ndjson;charset=utf-8',
    )
  }

  return (
    <div className="space-y-3">
      <FilterBar
        applied={applied}
        onApply={onApply}
        onClear={onClear}
        onExport={onExport}
        onToggleDensity={onToggleDensity}
        exportCount={items.length}
      />
      {error ? (
        <ErrorState error={error as Error} onRetry={() => refetch()} />
      ) : isLoading ? (
        <LoadingTable />
      ) : items.length === 0 ? (
        <EmptyState onClear={onClear} />
      ) : (
        <div className={cn('relative', isPlaceholderData && 'opacity-70')}>
          <DataTable<JournalRow>
            rows={items}
            columns={COLUMNS}
            rowKey={(r) => String(r.id)}
            density={applied.density}
            pageSize={PAGE_SIZE}
            total={total}
            page={applied.page}
            onPageChange={setPage}
            onRowClick={() => {}}
            expandedRowRender={(row) => expandedPayload(row)}
          />
          <div className="px-1 text-right text-xs text-muted-foreground">
            共 {totalFmt.format(total)} 列
          </div>
        </div>
      )}
    </div>
  )
}
