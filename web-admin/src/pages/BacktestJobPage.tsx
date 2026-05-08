import { Link, useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowDown,
  ArrowLeft,
  ArrowUp,
} from 'lucide-react'
import dayjs from 'dayjs'
import {
  ApiError,
  getBacktestJob,
  type BacktestJobDetail,
  type BacktestTrade,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { KpiCard, type KpiDirection } from '@/components/kpi-card'
import { DataTable, type DataTableColumn } from '@/components/data-table'

const numFmt = new Intl.NumberFormat('zh-TW')
const pctFmt = new Intl.NumberFormat('zh-TW', {
  style: 'percent',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const sharpeFmt = new Intl.NumberFormat('zh-TW', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const pnlFmt = new Intl.NumberFormat('zh-TW', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})

function annualDirection(v: number | null | undefined): KpiDirection {
  if (v == null || v === 0) return 'neutral'
  return v > 0 ? 'up' : 'down'
}

function sharpeDirection(v: number | null | undefined): KpiDirection {
  if (v == null) return 'neutral'
  if (v > 1) return 'up'
  if (v < 0) return 'down'
  return 'neutral'
}

function PnlCell({ value }: { value: number }) {
  if (value === 0) {
    return <span className="text-muted-foreground tabular">0</span>
  }
  if (value > 0) {
    return (
      <span className="inline-flex items-center justify-end gap-1 text-up tabular">
        <ArrowUp className="size-3" aria-hidden />
        +{pnlFmt.format(value)}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center justify-end gap-1 text-down tabular">
      <ArrowDown className="size-3" aria-hidden />
      {pnlFmt.format(value)}
    </span>
  )
}

const TRADE_COLUMNS: DataTableColumn<BacktestTrade>[] = [
  {
    id: 'entry_date',
    header: '進場日',
    accessor: (r) => <span className="tabular text-xs">{r.entry_date}</span>,
  },
  {
    id: 'exit_date',
    header: '出場日',
    accessor: (r) => <span className="tabular text-xs">{r.exit_date}</span>,
  },
  {
    id: 'symbol',
    header: 'Symbol',
    accessor: (r) => <span className="font-mono">{r.symbol}</span>,
  },
  { id: 'side', header: '方向', accessor: (r) => r.side },
  {
    id: 'pnl_twd',
    header: 'P&L',
    align: 'right',
    accessor: (r) => <PnlCell value={r.pnl_twd} />,
  },
  {
    id: 'hold_days',
    header: '持倉',
    align: 'right',
    accessor: (r) => (
      <span className="tabular">{numFmt.format(r.hold_days)} 日</span>
    ),
  },
  {
    id: 'pattern',
    header: 'Pattern',
    accessor: (r) => r.pattern ?? '—',
  },
]

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

function Header({ data }: { data: BacktestJobDetail }) {
  const idShort = `${data.id.slice(0, 8)}…`
  return (
    <div className="flex flex-col gap-1">
      <Link
        to="/backtest"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3" aria-hidden /> /backtest
      </Link>
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-xl font-semibold tracking-tight">
          回測結果 <span className="font-mono text-base">{idShort}</span>
        </h1>
        <span className="text-sm text-muted-foreground tabular">
          {data.strategy} · {data.period_from} ~ {data.period_to}
        </span>
      </div>
      <div className="text-[11px] text-muted-foreground">
        建立 {dayjs(data.created_at).format('YYYY-MM-DD HH:mm')} · 耗時{' '}
        {data.elapsed_ms}ms
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// KPI row
// ---------------------------------------------------------------------------

function KpiRow({ data }: { data: BacktestJobDetail }) {
  const m = data.metrics
  const failed = data.status === 'failed' || m == null

  if (failed) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="年化" value="—" direction="neutral" glyph={null} />
        <KpiCard label="Sharpe" value="—" direction="neutral" glyph={null} />
        <KpiCard label="MaxDD" value="—" direction="neutral" glyph={null} />
        <KpiCard label="勝率" value="—" direction="neutral" glyph={null} />
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard
        label="年化"
        value={
          m.annual_return_pct == null
            ? '—'
            : `${m.annual_return_pct >= 0 ? '+' : ''}${pctFmt.format(m.annual_return_pct)}`
        }
        direction={annualDirection(m.annual_return_pct)}
      />
      <KpiCard
        label="Sharpe"
        value={m.sharpe == null ? '—' : sharpeFmt.format(m.sharpe)}
        direction={sharpeDirection(m.sharpe)}
        glyph={sharpeDirection(m.sharpe) === 'neutral' ? null : 'auto'}
      />
      <KpiCard
        label="MaxDD"
        value={
          m.max_drawdown_pct == null
            ? '—'
            : pctFmt.format(m.max_drawdown_pct)
        }
        direction={m.max_drawdown_pct == null ? 'neutral' : 'down'}
      />
      <KpiCard
        label="勝率"
        value={
          m.win_rate_pct == null ? '—' : pctFmt.format(m.win_rate_pct)
        }
        direction="neutral"
        glyph={null}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// BacktestJobPage
// ---------------------------------------------------------------------------

export function BacktestJobPage() {
  const { jobId = '' } = useParams()

  const q = useQuery<BacktestJobDetail, ApiError>({
    queryKey: ['backtest', 'job', jobId],
    queryFn: () => getBacktestJob(jobId),
    enabled: jobId.length > 0,
    retry: false,
  })

  if (q.isLoading) {
    return (
      <div className="space-y-4">
        <header className="space-y-2">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-7 w-72" />
          <Skeleton className="h-4 w-48" />
        </header>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="rounded-lg p-4">
              <Skeleton className="h-3 w-12" />
              <Skeleton className="mt-2 h-7 w-24" />
            </Card>
          ))}
        </div>
        <Card className="p-4">
          <Skeleton className="h-40 w-full" />
        </Card>
        <Card className="p-4">
          <Skeleton className="h-40 w-full" />
        </Card>
        <Card className="p-4">
          <Skeleton className="h-32 w-full" />
        </Card>
      </div>
    )
  }

  if (q.error) {
    const err = q.error
    if (err.code === 'not_found' || err.httpStatus === 404) {
      return (
        <div className="space-y-3">
          <Card className="p-6 text-center text-sm">
            <div className="text-base font-medium">該 job 不存在</div>
            <p className="mt-1 text-muted-foreground">
              jobId {jobId} 找不到對應的回測。
            </p>
            <div className="mt-4">
              <Button asChild variant="outline">
                <Link to="/backtest">
                  <ArrowLeft className="size-3" aria-hidden /> 返回 /backtest
                </Link>
              </Button>
            </div>
          </Card>
        </div>
      )
    }
    return (
      <div className="space-y-3">
        <Card
          role="alert"
          className="border-destructive/50 bg-destructive/5 p-4"
        >
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="size-4" aria-hidden />
              <span>載入回測結果失敗 — {err.message}</span>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => q.refetch()}
            >
              重試
            </Button>
          </div>
        </Card>
      </div>
    )
  }

  if (!q.data) return null
  const data = q.data
  const failed = data.status === 'failed'

  return (
    <div className="space-y-4">
      <Header data={data} />

      {failed && data.error && (
        <Card
          role="alert"
          className="border-destructive/50 bg-destructive/5 p-3"
        >
          <div className="flex items-center gap-2 text-sm text-destructive">
            <AlertCircle className="size-4" aria-hidden />
            <span>
              此 job 失敗 — {data.error.code}: {data.error.message}
            </span>
          </div>
        </Card>
      )}

      <KpiRow data={data} />

      <Card className="p-4">
        <div className="flex h-48 items-center justify-center rounded-md border border-dashed border-input bg-muted/30 text-sm text-muted-foreground">
          {failed ? '無資料 — job 失敗' : '資金曲線（圖庫待定）'}
        </div>
        <div className="mt-2 text-[11px] text-muted-foreground">
          {failed
            ? '失敗的 job 不繪製曲線'
            : `${data.equity_curve.length} 個 equity 點已載入；圖表元件待挑選`}
        </div>
      </Card>

      <Card className="p-4">
        <div className="flex h-48 items-center justify-center rounded-md border border-dashed border-input bg-muted/30 text-sm text-muted-foreground">
          {failed ? '無資料 — job 失敗' : '回撤曲線（圖庫待定）'}
        </div>
        <div className="mt-2 text-[11px] text-muted-foreground">
          {failed
            ? '失敗的 job 不繪製曲線'
            : `${data.drawdown.length} 個 drawdown 點已計算`}
        </div>
      </Card>

      <section className="rounded-lg border bg-card shadow-sm">
        <header className="flex items-center justify-between border-b px-4 py-2.5">
          <h2 className="text-sm font-semibold">交易明細</h2>
          <span className="text-[11px] text-muted-foreground">
            {data.trades.length} 筆
          </span>
        </header>
        <div className="p-3">
          {data.trades.length === 0 ? (
            <div className="py-6 text-center text-sm text-muted-foreground">
              本 job 區間無交易訊號
            </div>
          ) : (
            <DataTable<BacktestTrade>
              rows={data.trades}
              columns={TRADE_COLUMNS}
              rowKey={(r, i) => `${r.entry_date}-${r.symbol}-${i}`}
            />
          )}
        </div>
      </section>
    </div>
  )
}
