import { useQuery } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Activity, AlertCircle, Briefcase, DollarSign, Hourglass, Minus } from 'lucide-react'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-tw'
import { apiFetch, type LiveEvent, type StatsToday } from '@/lib/api'
import { useAdminEvents } from '@/hooks/useAdminEvents'
import { useLiveFeedStore } from '@/stores'
import { cn } from '@/lib/utils'

dayjs.extend(relativeTime)
dayjs.locale('zh-tw')

// ---------------------------------------------------------------------------
// KpiCard - value + trend glyph + tabular number; pairs color with arrow.
// ---------------------------------------------------------------------------

type Trend = 'up' | 'down' | 'neutral'

function KpiCard({
  label, value, unit, trend = 'neutral', loading = false,
}: {
  label: string
  value: React.ReactNode
  unit?: string
  trend?: Trend
  loading?: boolean
}) {
  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      {loading ? (
        <div className="mt-2 h-8 w-32 animate-pulse rounded bg-muted" aria-busy="true" aria-label="載入中" />
      ) : (
        <div className={cn(
          'mt-2 flex items-baseline gap-1.5 tabular text-2xl font-semibold',
          trend === 'up'   && 'text-up',
          trend === 'down' && 'text-down',
        )}>
          <span aria-hidden className="inline-flex">
            {trend === 'up' && <ArrowUp className="size-4 self-center" />}
            {trend === 'down' && <ArrowDown className="size-4 self-center" />}
            {trend === 'neutral' && <Minus className="size-4 self-center text-muted-foreground" />}
          </span>
          <span>{value}</span>
          {unit && <span className="text-sm font-normal text-muted-foreground">{unit}</span>}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// KpiRow - fetches /api/admin/stats/today
// ---------------------------------------------------------------------------

function trendOf(n: number): Trend {
  if (n > 0) return 'up'
  if (n < 0) return 'down'
  return 'neutral'
}

const numFmt = new Intl.NumberFormat('zh-TW')
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
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard
        label="今日已實現損益"
        value={data ? numFmt.format(data.realized_pnl_twd) : ''}
        unit="TWD"
        trend={data ? trendOf(data.realized_pnl_twd) : 'neutral'}
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
      <KpiCard
        label="今日 LLM 成本"
        value={data ? usdFmt.format(data.llm_cost_usd) : ''}
        unit="USD"
        loading={isLoading}
      />
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
        <KpiRow />
      </div>
      <div className="lg:row-span-2 lg:h-[calc(100vh-10rem)]">
        <LiveFeed />
      </div>
    </div>
  )
}