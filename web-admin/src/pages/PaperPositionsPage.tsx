import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  ListOrdered,
  Minus,
  RefreshCcw,
} from 'lucide-react'
import dayjs from 'dayjs'
import { apiFetch, type OpenPosition } from '@/lib/api'
import { DataTable, type DataTableColumn } from '@/components/data-table'
import { directionOf, type KpiDirection } from '@/components/kpi-card'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const numFmt = new Intl.NumberFormat('zh-TW')
const signedTwdFmt = new Intl.NumberFormat('zh-TW', { signDisplay: 'exceptZero' })
const signedPctFmt = new Intl.NumberFormat('zh-TW', {
  signDisplay: 'exceptZero',
  minimumFractionDigits: 1,
  maximumFractionDigits: 2,
})
const priceFmt = new Intl.NumberFormat('zh-TW', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

function dirClass(d: KpiDirection): string {
  return d === 'up'
    ? 'text-up'
    : d === 'down'
      ? 'text-down'
      : 'text-muted-foreground'
}

function DirGlyph({ d, size = 'size-3.5' }: { d: KpiDirection; size?: string }) {
  if (d === 'up') return <ArrowUp className={size} aria-hidden />
  if (d === 'down') return <ArrowDown className={size} aria-hidden />
  return <Minus className={size} aria-hidden />
}

function SideCell({ side }: { side: 'long' | 'short' }) {
  const d: KpiDirection = side === 'long' ? 'up' : 'down'
  return (
    <span
      className={cn('inline-flex items-center gap-1 font-medium', dirClass(d))}
      data-direction={d}
    >
      <DirGlyph d={d} size="size-3.5" />
      <span>{side === 'long' ? '多' : '空'}</span>
    </span>
  )
}

function PnlCell({
  value,
  format,
}: {
  value: number
  format: Intl.NumberFormat
}) {
  const d = directionOf(value)
  return (
    <span
      className={cn(
        'inline-flex items-center justify-end gap-1 tabular',
        dirClass(d),
      )}
      data-direction={d}
    >
      <DirGlyph d={d} size="size-3.5" />
      <span>{format.format(value)}</span>
    </span>
  )
}

const COLUMNS: DataTableColumn<OpenPosition>[] = [
  { id: 'symbol', header: 'Symbol', accessor: (r) => r.symbol },
  { id: 'side', header: '方向', accessor: (r) => <SideCell side={r.side} /> },
  {
    id: 'qty',
    header: 'Qty',
    align: 'right',
    accessor: (r) => numFmt.format(r.qty),
  },
  {
    id: 'entry_price',
    header: 'Entry',
    align: 'right',
    accessor: (r) => priceFmt.format(r.entry_price),
  },
  {
    id: 'mark_price',
    header: '現價',
    align: 'right',
    accessor: (r) => priceFmt.format(r.mark_price),
  },
  {
    id: 'unrealized_pnl_twd',
    header: '未實現 P&L',
    align: 'right',
    sortable: true,
    accessor: (r) => (
      <PnlCell value={r.unrealized_pnl_twd} format={signedTwdFmt} />
    ),
  },
  {
    id: 'unrealized_pnl_pct',
    header: 'P&L%',
    align: 'right',
    accessor: (r) => (
      <PnlCell value={r.unrealized_pnl_pct} format={signedPctFmt} />
    ),
  },
  {
    id: 'stop_loss',
    header: '停損',
    align: 'right',
    accessor: (r) => priceFmt.format(r.stop_loss),
  },
  {
    id: 't1_target',
    header: 'T1',
    align: 'right',
    accessor: (r) => priceFmt.format(r.t1_target),
  },
  {
    id: 'hold_days',
    header: '持倉',
    align: 'right',
    accessor: (r) => `${numFmt.format(r.hold_days)}d`,
  },
]

function distancePct(from: number, to: number): number {
  if (!from) return 0
  return ((to - from) / from) * 100
}

function DetailPanel({ row }: { row: OpenPosition }) {
  const stopDistPct = distancePct(row.entry_price, row.stop_loss)
  const t1DistPct = distancePct(row.entry_price, row.t1_target)
  const stopDir = directionOf(stopDistPct)
  const t1Dir = directionOf(t1DistPct)

  return (
    <Card className="mt-3 p-4 text-sm" data-testid="positions-detail-panel">
      <div className="grid grid-cols-1 gap-x-6 gap-y-2 md:grid-cols-2">
        <div>
          <span className="text-muted-foreground">選定列：</span>
          <span className="ml-1 font-semibold">{row.symbol}</span>
        </div>
        <div>
          <span className="text-muted-foreground">進場時間：</span>
          <span className="ml-1 tabular">
            {dayjs(row.entry_at).format('YYYY-MM-DD HH:mm')}
          </span>
        </div>
        <div className="md:col-span-2">
          <span className="text-muted-foreground">進場理由：</span>
          <span className="ml-1">{row.entry_reason || '—'}</span>
        </div>
        <div>
          <span className="text-muted-foreground">停損距離：</span>
          <span
            className={cn(
              'ml-1 inline-flex items-center gap-1 tabular',
              dirClass(stopDir),
            )}
            data-direction={stopDir}
          >
            <DirGlyph d={stopDir} size="size-3" />
            {signedPctFmt.format(stopDistPct)}%
          </span>
        </div>
        <div>
          <span className="text-muted-foreground">T1 距離：</span>
          <span
            className={cn(
              'ml-1 inline-flex items-center gap-1 tabular',
              dirClass(t1Dir),
            )}
            data-direction={t1Dir}
          >
            <DirGlyph d={t1Dir} size="size-3" />
            {signedPctFmt.format(t1DistPct)}%
          </span>
        </div>
        <div className="md:col-span-2">
          <span className="text-muted-foreground">Time stop：</span>
          <span className="ml-1 tabular">{row.time_stop_date}</span>
        </div>
      </div>
    </Card>
  )
}

function EmptyState() {
  return (
    <Card className="p-8 text-center">
      <ListOrdered
        className="mx-auto size-8 text-muted-foreground"
        aria-hidden
      />
      <h3 className="mt-3 text-sm font-medium">目前無開倉</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        目前沒有任何持倉部位；新進場後會即時更新。
      </p>
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

function LoadingState() {
  return (
    <div className="space-y-3">
      <div className="rounded-md border bg-card p-4">
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-6 w-full" />
          ))}
        </div>
      </div>
      <Card className="p-4">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-2 h-4 w-3/4" />
        <Skeleton className="mt-2 h-4 w-1/2" />
      </Card>
    </div>
  )
}

export function PaperPositionsPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['admin', 'positions', 'open'],
    queryFn: () => apiFetch<OpenPosition[]>('/api/admin/positions/open'),
    refetchInterval: 30_000,
  })

  if (isLoading) return <LoadingState />
  if (error)
    return <ErrorState error={error as Error} onRetry={() => refetch()} />
  const rows = data ?? []
  if (rows.length === 0) return <EmptyState />

  const selected = rows.find((r) => r.symbol === selectedSymbol) ?? null

  return (
    <div className="space-y-3">
      <DataTable<OpenPosition>
        rows={rows}
        columns={COLUMNS}
        rowKey={(r) => r.symbol}
        onRowClick={(r) =>
          setSelectedSymbol((prev) => (prev === r.symbol ? null : r.symbol))
        }
      />
      {selected && <DetailPanel row={selected} />}
    </div>
  )
}
