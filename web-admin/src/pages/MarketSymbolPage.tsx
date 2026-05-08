import * as React from 'react'
import { useEffect } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import {
  ApiError,
  getMarketSymbol,
  type InstitutionalRow,
  type MarketSymbolDetail,
  type RecentPattern,
} from '@/lib/api'
import { useAdminEvents } from '@/hooks/useAdminEvents'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { DataTable, type DataTableColumn } from '@/components/data-table'
import { cn } from '@/lib/utils'

const numFmt = new Intl.NumberFormat('zh-TW')
const priceFmt = new Intl.NumberFormat('zh-TW', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
})
const pctFmt = new Intl.NumberFormat('zh-TW', {
  style: 'percent',
  minimumFractionDigits: 1,
  maximumFractionDigits: 2,
})

function dirOf(value: number | null | undefined): 'up' | 'down' | 'neutral' {
  if (value == null || value === 0) return 'neutral'
  return value > 0 ? 'up' : 'down'
}

function patternDirection(p: string | undefined): 'up' | 'down' | 'neutral' {
  if (!p) return 'neutral'
  const s = p.toLowerCase()
  if (
    s.includes('breakout') ||
    s.includes('bullish') ||
    s.includes('reversal up') ||
    s.includes('rs=')
  ) {
    return 'up'
  }
  if (
    s.includes('failed') ||
    s.includes('bearish') ||
    s.includes('breakdown') ||
    s.includes('reversal down')
  ) {
    return 'down'
  }
  return 'neutral'
}

function outcomeDirection(o: string): 'up' | 'down' | 'neutral' {
  if (o.startsWith('+')) return 'up'
  if (o.startsWith('-')) return 'down'
  return 'neutral'
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

function HeaderQuote({ data }: { data: MarketSymbolDetail }) {
  const q = data.quote
  const direction = dirOf(q.change)
  const pct = q.change_pct
  const arrow =
    direction === 'up' ? (
      <ArrowUp className="size-4" aria-hidden />
    ) : direction === 'down' ? (
      <ArrowDown className="size-4" aria-hidden />
    ) : null

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-3">
        <Link
          to="/market"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-3" aria-hidden /> /market
        </Link>
        <h1 className="text-xl font-semibold tracking-tight">
          <span className="font-mono">{data.symbol}</span>
        </h1>
      </div>
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="tabular text-3xl font-semibold">
          {priceFmt.format(q.price)}
        </span>
        {direction === 'neutral' ? (
          <span
            className="inline-flex items-center gap-1 text-sm text-muted-foreground"
            data-direction="neutral"
          >
            —
          </span>
        ) : (
          <span
            className={cn(
              'inline-flex items-center gap-1 tabular text-sm',
              direction === 'up' ? 'text-up' : 'text-down',
            )}
            data-direction={direction}
          >
            {arrow}
            {q.change != null && (
              <span>
                {q.change > 0 ? '+' : ''}
                {q.change.toFixed(2)}
              </span>
            )}
            {pct != null && <span>({pctFmt.format(pct)})</span>}
          </span>
        )}
        <span className="text-xs text-muted-foreground">
          以 {q.asof} 收盤計
        </span>
      </div>
      <div className="text-xs text-muted-foreground">
        量 {numFmt.format(q.volume)}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// KPI cards
// ---------------------------------------------------------------------------

function ChipKpiCard({
  label,
  value,
  hint,
}: {
  label: string
  value: React.ReactNode
  hint?: React.ReactNode
}) {
  return (
    <Card className="rounded-lg p-4">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="mt-2 flex items-baseline gap-1.5 tabular text-2xl font-semibold">
        {value}
      </div>
      {hint && (
        <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
      )}
    </Card>
  )
}

function KpiRow({ data }: { data: MarketSymbolDetail }) {
  const rs = data.rs
  const sepa = data.sepa
  const totalLast5 = data.institutional.reduce((s, r) => s + r.total, 0)
  const totalDir = dirOf(totalLast5)
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <ChipKpiCard
        label="RS Rank"
        value={rs == null ? <span>—</span> : <span>{rs.value}</span>}
        hint={rs == null ? '無資料' : `as of ${rs.asof}`}
      />
      <ChipKpiCard
        label="SEPA"
        value={sepa == null ? <span>—</span> : <span>Stage {sepa.stage}</span>}
        hint={
          sepa == null
            ? '資料不足'
            : sepa.since
              ? `since ${sepa.since}`
              : null
        }
      />
      <ChipKpiCard
        label="連續買超"
        value={
          data.institutional.length === 0 ? (
            <span>—</span>
          ) : (
            <span
              className={cn(
                totalDir === 'up' && 'text-up',
                totalDir === 'down' && 'text-down',
              )}
            >
              {totalLast5 > 0 && '+'}
              {numFmt.format(totalLast5)}
            </span>
          )
        }
        hint={
          data.institutional.length === 0
            ? '近 5 日無資料'
            : `近 ${data.institutional.length} 日合計（張）`
        }
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Institutional table
// ---------------------------------------------------------------------------

function NumCell({ value }: { value: number }) {
  if (value === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-muted-foreground">
        —
      </span>
    )
  }
  if (value > 0) {
    return (
      <span className="inline-flex items-center justify-end gap-1 text-up tabular">
        <ArrowUp className="size-3" aria-hidden />
        +{numFmt.format(value)}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center justify-end gap-1 text-down tabular">
      <ArrowDown className="size-3" aria-hidden />
      {numFmt.format(value)}
    </span>
  )
}

const INST_COLUMNS: DataTableColumn<InstitutionalRow>[] = [
  {
    id: 'date',
    header: '日期',
    accessor: (r) => <span className="tabular">{r.date}</span>,
  },
  {
    id: 'foreign',
    header: '外資',
    align: 'right',
    accessor: (r) => <NumCell value={r.foreign} />,
  },
  {
    id: 'trust',
    header: '投信',
    align: 'right',
    accessor: (r) => <NumCell value={r.trust} />,
  },
  {
    id: 'dealer',
    header: '自營商',
    align: 'right',
    accessor: (r) => <NumCell value={r.dealer} />,
  },
  {
    id: 'total',
    header: '合計',
    align: 'right',
    accessor: (r) => <NumCell value={r.total} />,
  },
]

// ---------------------------------------------------------------------------
// Patterns table
// ---------------------------------------------------------------------------

function OutcomeCell({ outcome }: { outcome: string }) {
  const dir = outcomeDirection(outcome)
  if (dir === 'neutral') {
    return (
      <span className="inline-flex items-center gap-1 text-muted-foreground">
        {outcome}
      </span>
    )
  }
  if (dir === 'up') {
    return (
      <span className="inline-flex items-center gap-1 text-up tabular">
        <ArrowUp className="size-3" aria-hidden />
        {outcome}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-down tabular">
      <ArrowDown className="size-3" aria-hidden />
      {outcome}
    </span>
  )
}

function PatternNameCell({ pattern }: { pattern: string }) {
  const dir = patternDirection(pattern)
  if (dir === 'up') {
    return (
      <span className="inline-flex items-center gap-1.5">
        <TrendingUp className="size-3.5 text-up" aria-hidden />
        <span>{pattern}</span>
      </span>
    )
  }
  if (dir === 'down') {
    return (
      <span className="inline-flex items-center gap-1.5">
        <TrendingDown className="size-3.5 text-down" aria-hidden />
        <span>{pattern}</span>
      </span>
    )
  }
  return <span>{pattern}</span>
}

const PATTERN_COLUMNS: DataTableColumn<RecentPattern>[] = [
  {
    id: 'ts',
    header: '日期',
    accessor: (r) => <span className="tabular">{r.ts.slice(0, 10)}</span>,
  },
  {
    id: 'pattern',
    header: 'Pattern',
    accessor: (r) => <PatternNameCell pattern={r.pattern} />,
  },
  {
    id: 'score',
    header: 'Score',
    align: 'right',
    accessor: (r) => (
      <span className={cn('tabular', r.score >= 0.7 && 'font-medium')}>
        {r.score.toFixed(2)}
      </span>
    ),
  },
  {
    id: 'outcome',
    header: '結局',
    accessor: (r) => <OutcomeCell outcome={r.outcome} />,
  },
]

// ---------------------------------------------------------------------------
// MarketSymbolPage
// ---------------------------------------------------------------------------

export function MarketSymbolPage() {
  const { symbol = '' } = useParams()
  const navigate = useNavigate()
  useAdminEvents()

  const q = useQuery<MarketSymbolDetail, ApiError>({
    queryKey: ['market', 'symbol', symbol],
    queryFn: () => getMarketSymbol(symbol),
    enabled: symbol.length > 0,
    retry: false,
  })

  // refetch when symbol changes
  useEffect(() => {
    if (symbol.length === 0) return
    q.refetch().catch(() => {
      /* error surfaces via q.error */
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol])

  if (q.isLoading) {
    return (
      <div className="space-y-4">
        <header className="space-y-2">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-6 w-60" />
        </header>
        <Card className="h-48 p-4">
          <Skeleton className="h-full w-full" />
        </Card>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="rounded-lg p-4">
              <Skeleton className="h-3 w-12" />
              <Skeleton className="mt-2 h-7 w-16" />
            </Card>
          ))}
        </div>
        <Card className="p-4">
          <Skeleton className="h-32 w-full" />
        </Card>
        <Card className="p-4">
          <Skeleton className="h-32 w-full" />
        </Card>
      </div>
    )
  }

  if (q.error) {
    const err = q.error as ApiError
    if (err.code === 'market_symbol_not_found' || err.httpStatus === 404) {
      return (
        <div className="space-y-3">
          <Card className="p-6 text-center text-sm">
            <div className="text-base font-medium">該 symbol 無資料</div>
            <p className="mt-1 text-muted-foreground">
              請確認代號 {symbol} 是否正確。
            </p>
            <div className="mt-4">
              <Button asChild variant="outline">
                <Link to="/market">
                  <ArrowLeft className="size-3" aria-hidden /> 返回 /market
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
              <span>
                載入 {symbol} 失敗 — {err.message}
              </span>
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

  const onPatternClick = (r: RecentPattern) => {
    const date = r.ts.slice(0, 10)
    navigate(`/audit?symbol=${encodeURIComponent(symbol)}&date_from=${date}`)
  }

  return (
    <div className="space-y-4">
      <HeaderQuote data={data} />

      <Card className="p-4">
        <div className="flex h-48 items-center justify-center rounded-md border border-dashed border-input bg-muted/30 text-sm text-muted-foreground">
          K 線圖（圖庫待定）
        </div>
        <div className="mt-2 text-[11px] text-muted-foreground">
          近 {data.bars_daily.length} 日 OHLCV 已載入；圖表元件待後續挑選
        </div>
      </Card>

      <KpiRow data={data} />

      <section className="rounded-lg border bg-card shadow-sm">
        <header className="flex items-center justify-between border-b px-4 py-2.5">
          <h2 className="text-sm font-semibold">
            三大法人（近 {data.institutional.length || 5} 日）
          </h2>
        </header>
        <div className="p-3">
          {data.institutional.length === 0 ? (
            <div className="py-6 text-center text-sm text-muted-foreground">
              近 5 日無法人資料
            </div>
          ) : (
            <DataTable<InstitutionalRow>
              rows={data.institutional}
              columns={INST_COLUMNS}
              density="compact"
              rowKey={(r) => r.date}
            />
          )}
        </div>
      </section>

      <section className="rounded-lg border bg-card shadow-sm">
        <header className="flex items-center justify-between border-b px-4 py-2.5">
          <h2 className="text-sm font-semibold">近期偵測 Pattern</h2>
          <span className="text-[11px] text-muted-foreground">
            近 30 日，最多 20 筆
          </span>
        </header>
        <div className="p-3">
          {data.recent_patterns.length === 0 ? (
            <div className="py-6 text-center text-sm text-muted-foreground">
              近 30 日無 pattern 偵測紀錄
            </div>
          ) : (
            <DataTable<RecentPattern>
              rows={data.recent_patterns}
              columns={PATTERN_COLUMNS}
              onRowClick={onPatternClick}
              rowKey={(r) => r.ts}
            />
          )}
        </div>
      </section>
    </div>
  )
}
