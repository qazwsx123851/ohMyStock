import { useQuery } from '@tanstack/react-query'
import { Activity, AlertCircle, AlertTriangle, Briefcase, DollarSign, Hourglass } from 'lucide-react'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-tw'
import { apiFetch, type LiveEvent, type StatsSummary, type StatsToday } from '@/lib/api'
import { useAdminEvents } from '@/hooks/useAdminEvents'
import { useLiveFeedStore } from '@/stores'
import { KpiCard, directionOf } from '@/components/kpi-card'
import { cn } from '@/lib/utils'

dayjs.extend(relativeTime)
dayjs.locale('zh-tw')

// ---------------------------------------------------------------------------
// Shared summary query — all dashboard widgets read GET /api/admin/stats/today
// ---------------------------------------------------------------------------

function useSummary() {
  return useQuery({
    queryKey: ['stats', 'today'],
    queryFn: () => apiFetch<StatsSummary>('/api/admin/stats/today'),
    refetchInterval: 30_000,
  })
}

// ---------------------------------------------------------------------------
// KpiRow - fetches /api/admin/stats/today
// ---------------------------------------------------------------------------

const numFmt = new Intl.NumberFormat('zh-TW')
const signedTwdFmt = new Intl.NumberFormat('zh-TW', { signDisplay: 'exceptZero' })
const pctFmt = new Intl.NumberFormat('zh-TW', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const usdFmt = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

function KpiRow() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['stats', 'today'],
    queryFn: () => apiFetch<StatsToday>('/api/admin/stats/today'),
    refetchInterval: 30_000,
  })

  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
        <AlertCircle className="size-4" aria-hidden />
        <span>載入今日 KPI 失敗：{(error as Error).message}</span>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <KpiCard
        label="今日已實現損益"
        value={data ? signedTwdFmt.format(data.realized_pnl_twd) : ''}
        unit="TWD"
        direction={directionOf(data?.realized_pnl_twd)}
        loading={isLoading}
      />
      <KpiCard
        label="持倉檔數"
        value={data ? numFmt.format(data.open_positions) : ''}
        loading={isLoading}
      />
      <KpiCard
        label="待確認"
        value={data ? numFmt.format(data.pending_confirms) : ''}
        loading={isLoading}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// RiskGateLight — green/yellow/red market Risk-Off light + triggers (DB-B1)
// ---------------------------------------------------------------------------

const RISK_TRIGGER_LABELS: Record<string, string> = {
  taiex_below_ma60: '加權指數跌破 60MA',
  spy_5d_drop: '美股 SPY 5 日跌幅 >3%',
  vix_high: 'VIX 警戒（>25 或單日 +30%）',
  twd_depreciation: '台幣單日貶值 >0.5%',
  taifex_foreign_short_streak: '外資台指期淨空連 3 日新高',
}

const RISK_STATUS_META: Record<
  string,
  { dot: string; label: string; tone: string }
> = {
  green: { dot: 'bg-emerald-500', label: 'Risk-On（綠）', tone: 'border-border' },
  yellow: { dot: 'bg-amber-500', label: '注意（黃）', tone: 'border-amber-500/50' },
  red: { dot: 'bg-red-600', label: 'Risk-Off（紅）', tone: 'border-red-600/60 bg-red-600/5' },
}

function RiskGateLight() {
  const { data, isLoading } = useSummary()
  const rg = data?.risk_gate
  const status = rg?.status ?? 'green'
  const meta = RISK_STATUS_META[status] ?? RISK_STATUS_META.green
  return (
    <div
      className={cn('rounded-lg border bg-card p-4 shadow-sm', meta.tone)}
      data-risk-status={status}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider text-muted-foreground">
          市場風險閘
        </span>
        <span className="flex items-center gap-2 text-sm font-medium">
          <span
            className={cn('inline-block size-2.5 rounded-full', meta.dot)}
            aria-hidden
          />
          {isLoading && !rg ? '載入中…' : meta.label}
        </span>
      </div>
      {rg && rg.triggers.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm text-red-700 dark:text-red-400">
          {rg.triggers.map((t) => (
            <li key={t} className="flex items-center gap-1.5">
              <AlertTriangle className="size-3.5 shrink-0" aria-hidden />
              {RISK_TRIGGER_LABELS[t] ?? t}
            </li>
          ))}
        </ul>
      )}
      {status === 'yellow' && (
        <p className="mt-2 text-xs text-muted-foreground">
          部分訊號暫無資料；評分目前僅採 TAIEX。
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// MonthlyBreakerBanner — red banner when month PnL hit the breaker threshold
// ---------------------------------------------------------------------------

function MonthlyBreakerBanner() {
  const { data } = useSummary()
  if (!data?.monthly_breaker?.tripped) return null
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>
        <p className="font-semibold">
          月度熔斷已觸發（本月 {pctFmt.format(data.monthly_breaker.month_pnl_pct)}%）
        </p>
        <p className="mt-0.5 text-destructive/90">
          禁止新進場至月底，並請執行月度復盤。
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CostBar — month-to-date LLM cost vs budget; turns orange at ≥80%
// ---------------------------------------------------------------------------

function CostBar() {
  const { data, isLoading } = useSummary()
  const cost = data?.cost
  const pct = cost ? Math.max(0, cost.pct) : 0
  const clamped = Math.min(100, pct)
  const warn = pct >= 80
  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm">
      <div className="flex items-baseline justify-between">
        <span className="text-xs uppercase tracking-wider text-muted-foreground">
          本月 LLM 成本
        </span>
        <span className="tabular text-sm text-muted-foreground">
          {cost
            ? `${usdFmt.format(cost.used_usd)} / ${usdFmt.format(cost.budget_usd)} USD`
            : isLoading
              ? '載入中…'
              : '—'}
        </span>
      </div>
      <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          role="progressbar"
          aria-valuenow={Math.round(pct)}
          aria-valuemin={0}
          aria-valuemax={100}
          data-warn={warn ? 'true' : 'false'}
          className={cn(
            'h-full rounded-full transition-all',
            warn ? 'bg-orange-500' : 'bg-primary',
          )}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// LiveFeed - subscribes to SSE and shows the last 20 events
// ---------------------------------------------------------------------------

function eventIcon(eventType: string) {
  if (eventType.startsWith('confirm_gate'))    return <Hourglass className="size-3.5" aria-hidden />
  if (eventType.startsWith('order'))           return <Briefcase className="size-3.5" aria-hidden />
  if (eventType.startsWith('auto_execute'))    return <DollarSign className="size-3.5" aria-hidden />
  return <Activity className="size-3.5" aria-hidden />
}

function LiveFeedRow({ e }: { e: LiveEvent }) {
  const sym = (e.payload?.symbol as string | undefined) ?? '—'
  const rel = dayjs(e.timestamp).fromNow()
  return (
    <li className="grid grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-3 border-b px-3 py-1.5 text-xs last:border-b-0">
      <span className="text-muted-foreground">{eventIcon(e.event_type)}</span>
      <span className="truncate font-medium text-foreground">{e.event_type}</span>
      <span className="tabular text-muted-foreground">{sym}</span>
      <span className="tabular text-[11px] text-muted-foreground">{rel}</span>
    </li>
  )
}

function LiveFeed() {
  useAdminEvents()
  const events = useLiveFeedStore((s) => s.events).slice(0, 20)
  return (
    <section className="flex h-full flex-col rounded-lg border bg-card shadow-sm">
      <header className="flex items-center justify-between border-b px-4 py-2.5">
        <h2 className="text-sm font-semibold">即時事件</h2>
        <span className="text-[11px] text-muted-foreground">{events.length} / 20</span>
      </header>
      {events.length === 0 ? (
        <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted-foreground">
          等待事件中…
        </div>
      ) : (
        <ul className="overflow-y-auto">
          {events.map((e, i) => <LiveFeedRow key={`${e.timestamp}-${i}`} e={e} />)}
        </ul>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Page composition
// ---------------------------------------------------------------------------

export function DashboardPage() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr] lg:items-start">
      <div className="space-y-4">
        <RiskGateLight />
        <MonthlyBreakerBanner />
        <KpiRow />
        <CostBar />
      </div>
      <div className="lg:row-span-2 lg:h-[calc(100vh-10rem)]">
        <LiveFeed />
      </div>
    </div>
  )
}