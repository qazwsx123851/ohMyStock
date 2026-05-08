import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Download,
  Minus,
  ReceiptText,
  RefreshCcw,
} from 'lucide-react'
import dayjs from 'dayjs'
import { apiFetch, type JournalRow, type PaginatedRows } from '@/lib/api'
import { JOURNAL_KIND_ENTRY_LIKE } from '@/lib/journal-kinds'
import { DataTable, type DataTableColumn } from '@/components/data-table'
import { StatusBadge, type Status } from '@/components/status-badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

type EntryLikeKind = (typeof JOURNAL_KIND_ENTRY_LIKE)[number]
const ALL_ENTRY_KINDS: EntryLikeKind[] = [...JOURNAL_KIND_ENTRY_LIKE]
const PAGE_SIZE = 50

type AppliedFilter = {
  kinds: EntryLikeKind[]
  symbol: string
  dateFrom: string
  dateTo: string
  page: number
}

function readFilter(sp: URLSearchParams): AppliedFilter {
  const rawKinds = sp.getAll('kind').filter((k): k is EntryLikeKind =>
    ALL_ENTRY_KINDS.includes(k as EntryLikeKind),
  )
  return {
    kinds: rawKinds.length > 0 ? rawKinds : ALL_ENTRY_KINDS,
    symbol: sp.get('symbol') ?? '',
    dateFrom: sp.get('date_from') ?? '',
    dateTo: sp.get('date_to') ?? '',
    page: Math.max(1, parseInt(sp.get('page') ?? '1', 10) || 1),
  }
}

function buildPath(f: AppliedFilter): string {
  const qs = new URLSearchParams()
  for (const k of f.kinds) qs.append('kind', k)
  if (f.symbol) qs.set('symbol', f.symbol)
  if (f.dateFrom) qs.set('date_from', f.dateFrom)
  if (f.dateTo) qs.set('date_to', f.dateTo)
  qs.set('limit', String(PAGE_SIZE))
  qs.set('offset', String((f.page - 1) * PAGE_SIZE))
  return `/api/admin/journal/rows?${qs.toString()}`
}

function applyToSearchParams(f: Omit<AppliedFilter, 'page'>): URLSearchParams {
  const sp = new URLSearchParams()
  for (const k of f.kinds) sp.append('kind', k)
  if (f.symbol) sp.set('symbol', f.symbol)
  if (f.dateFrom) sp.set('date_from', f.dateFrom)
  if (f.dateTo) sp.set('date_to', f.dateTo)
  return sp
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
      return 'executed'
    case 'reject':
      return 'rejected'
    default:
      return 'pending'
  }
}

function DirCell({ side }: { side?: string }) {
  if (side === 'long') {
    return (
      <span
        className="inline-flex items-center gap-1 text-up"
        data-direction="up"
      >
        <ArrowUp className="size-3.5" aria-hidden />
        <span>多</span>
      </span>
    )
  }
  if (side === 'short') {
    return (
      <span
        className="inline-flex items-center gap-1 text-down"
        data-direction="down"
      >
        <ArrowDown className="size-3.5" aria-hidden />
        <span>空</span>
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-muted-foreground">
      <Minus className="size-3.5" aria-hidden />
      <span>—</span>
    </span>
  )
}

const priceFmt = new Intl.NumberFormat('zh-TW', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const qtyFmt = new Intl.NumberFormat('zh-TW')

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
    id: 'side',
    header: '方向',
    accessor: (r) => <DirCell side={r.payload?.side as string | undefined} />,
  },
  {
    id: 'qty',
    header: 'Qty',
    align: 'right',
    accessor: (r) => {
      const q = r.payload?.qty as number | undefined
      return q != null ? qtyFmt.format(q) : '—'
    },
  },
  {
    id: 'price',
    header: 'Price',
    align: 'right',
    accessor: (r) => {
      const p = (r.payload?.price ?? r.payload?.actual_entry_price) as
        | number
        | undefined
      return p != null ? priceFmt.format(p) : '—'
    },
  },
  {
    id: 'status',
    header: '狀態',
    accessor: (r) => <StatusBadge status={inferStatus(r)} />,
  },
]

const CSV_HEADERS = ['時間', 'Kind', 'Symbol', '方向', 'Qty', 'Price', '狀態']

function csvEscape(value: unknown): string {
  if (value == null) return ''
  const s = String(value)
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

function rowsToCsv(rows: JournalRow[]): string {
  const header = CSV_HEADERS.join(',')
  const lines = rows.map((r) => {
    const side = (r.payload?.side as string | undefined) ?? ''
    const qty = r.payload?.qty as number | undefined
    const price = (r.payload?.price ?? r.payload?.actual_entry_price) as
      | number
      | undefined
    return [
      dayjs(r.created_at).format('YYYY-MM-DD HH:mm:ss'),
      r.kind,
      r.symbol ?? '',
      side === 'long' ? '多' : side === 'short' ? '空' : '',
      qty ?? '',
      price ?? '',
      inferStatus(r),
    ]
      .map(csvEscape)
      .join(',')
  })
  return [header, ...lines].join('\n')
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
  exportCount,
}: {
  applied: AppliedFilter
  onApply: (next: Omit<AppliedFilter, 'page'>) => void
  onClear: () => void
  onExport: () => void
  exportCount: number
}) {
  const [pendingKinds, setPendingKinds] = useState<EntryLikeKind[]>(
    applied.kinds,
  )
  const [pendingSymbol, setPendingSymbol] = useState(applied.symbol)
  const [pendingFrom, setPendingFrom] = useState(applied.dateFrom)
  const [pendingTo, setPendingTo] = useState(applied.dateTo)

  useEffect(() => {
    setPendingKinds(applied.kinds)
    setPendingSymbol(applied.symbol)
    setPendingFrom(applied.dateFrom)
    setPendingTo(applied.dateTo)
  }, [applied.kinds, applied.symbol, applied.dateFrom, applied.dateTo])

  const toggleKind = (k: EntryLikeKind) => {
    setPendingKinds((prev) =>
      prev.includes(k) ? prev.filter((x) => x !== k) : [...prev, k],
    )
  }

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-end gap-3 text-xs">
        <div className="space-y-1">
          <div className="font-medium text-muted-foreground">Kind</div>
          <div className="flex flex-wrap items-center gap-3">
            {ALL_ENTRY_KINDS.map((k) => (
              <label key={k} className="inline-flex items-center gap-1.5">
                <input
                  type="checkbox"
                  name={k}
                  checked={pendingKinds.includes(k)}
                  onChange={() => toggleKind(k)}
                  className="size-3.5"
                />
                <span className="font-mono">{k}</span>
              </label>
            ))}
          </div>
        </div>
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
            匯出本頁 {exportCount} 列 CSV
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
        試試調整 kind / symbol / 日期，或清空 filter 看全部。
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
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-6 w-full" />
        ))}
      </div>
    </Card>
  )
}

function expandedPayload(row: JournalRow) {
  return (
    <pre
      data-testid="orders-row-expanded"
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

export function PaperOrdersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const applied = useMemo(() => readFilter(searchParams), [searchParams])

  const path = buildPath(applied)
  const { data, isLoading, error, refetch, isPlaceholderData } = useQuery({
    queryKey: ['admin', 'journal', 'rows', path],
    queryFn: () => apiFetch<PaginatedRows<JournalRow>>(path),
    refetchInterval: 60_000,
    placeholderData: keepPreviousData,
  })

  const onApply = (next: Omit<AppliedFilter, 'page'>) => {
    const sp = applyToSearchParams(next)
    sp.set('page', '1')
    setSearchParams(sp)
  }
  const onClear = () => {
    setSearchParams(new URLSearchParams())
  }
  const setPage = (page: number) => {
    const sp = new URLSearchParams(searchParams)
    sp.set('page', String(page))
    setSearchParams(sp)
  }

  const items = data?.items ?? []
  const total = data?.total ?? 0

  const onExport = () => {
    if (items.length === 0) return
    const stamp = dayjs().format('YYYYMMDD-HHmmss')
    downloadBlob(
      `paper-orders-${stamp}.csv`,
      rowsToCsv(items),
      'text/csv;charset=utf-8',
    )
  }

  return (
    <div className="space-y-3">
      <FilterBar
        applied={applied}
        onApply={onApply}
        onClear={onClear}
        onExport={onExport}
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
            pageSize={PAGE_SIZE}
            total={total}
            page={applied.page}
            onPageChange={setPage}
            onRowClick={() => {}}
            expandedRowRender={(row) => expandedPayload(row)}
          />
        </div>
      )}
    </div>
  )
}
