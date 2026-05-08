import * as React from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { useMutation } from '@tanstack/react-query'
import {
  Activity,
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Hourglass,
  Search,
  TrendingDown,
  TrendingUp,
  X,
} from 'lucide-react'
import dayjs from 'dayjs'
import {
  ApiError,
  runScreener,
  type LiveEvent,
  type ScreenerHit,
  type ScreenerInput,
  type ScreenerRun,
} from '@/lib/api'
import { useAdminEvents } from '@/hooks/useAdminEvents'
import { useLiveFeedStore } from '@/stores'
import { DataTable, type DataTableColumn } from '@/components/data-table'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const UNIVERSES = ['tw50', 'tw100', 'mid100', 'custom'] as const
type Universe = (typeof UNIVERSES)[number]

type FilterFlags = {
  sepa: boolean
  rsMin80: boolean
  foreignBuyStreak: boolean
  triangle: boolean
}

type RunSummary = {
  runId: string
  hits: number
  elapsedMs: number | null
  asofIso: string
}

const LIVE_FEED_TYPES = new Set([
  'screener_started',
  'screener_completed',
  'pattern_detected',
])
const LIVE_FEED_RENDER = 5
const LIVE_FEED_BUFFER = 20
const FLASH_DURATION_MS = 500

const priceFmt = new Intl.NumberFormat('zh-TW', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const pctFmt = new Intl.NumberFormat('zh-TW', {
  style: 'percent',
  minimumFractionDigits: 1,
  maximumFractionDigits: 2,
})

function todayISO(): string {
  return dayjs().format('YYYY-MM-DD')
}

function patternDirection(
  pattern: string | undefined,
): 'up' | 'down' | 'neutral' {
  if (!pattern) return 'neutral'
  const p = pattern.toLowerCase()
  if (
    p.includes('breakout') ||
    p.includes('bullish') ||
    p.includes('reversal up') ||
    p.includes('rs=')
  ) {
    return 'up'
  }
  if (
    p.includes('failed') ||
    p.includes('bearish') ||
    p.includes('breakdown') ||
    p.includes('reversal down')
  ) {
    return 'down'
  }
  return 'neutral'
}

function buildScreenerInput(
  universe: Universe,
  customSymbols: string[],
  filters: FilterFlags,
  asof: string,
): ScreenerInput {
  const filterRows: Array<Record<string, unknown>> = []
  if (filters.sepa) filterRows.push({ sepa: true })
  if (filters.rsMin80) filterRows.push({ rs_min: 80 })
  if (filters.foreignBuyStreak) filterRows.push({ foreign_buy_streak: 3 })
  if (filters.triangle) filterRows.push({ triangle: true })
  return {
    universe,
    custom_symbols: customSymbols.length > 0 ? customSymbols : null,
    filters: filterRows.length > 0 ? filterRows : null,
    asof_date: asof || null,
  }
}

// ---------------------------------------------------------------------------
// Result columns + cells
// ---------------------------------------------------------------------------

type ResultRow = ScreenerHit & { _flashUntil?: number }

function ChangeCell({ value }: { value: number | null | undefined }) {
  if (value == null || value === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-muted-foreground">
        —
      </span>
    )
  }
  if (value > 0) {
    return (
      <span className="inline-flex items-center gap-1 text-up tabular">
        <ArrowUp className="size-3" aria-hidden />
        {pctFmt.format(value)}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-down tabular">
      <ArrowDown className="size-3" aria-hidden />
      {pctFmt.format(value)}
    </span>
  )
}

function PatternCell({ pattern }: { pattern: string | undefined }) {
  const dir = patternDirection(pattern)
  const text = pattern ?? '—'
  if (dir === 'up') {
    return (
      <span className="inline-flex items-center gap-1.5">
        <TrendingUp className="size-3.5 text-up" aria-hidden />
        <span>{text}</span>
      </span>
    )
  }
  if (dir === 'down') {
    return (
      <span className="inline-flex items-center gap-1.5">
        <TrendingDown className="size-3.5 text-down" aria-hidden />
        <span>{text}</span>
      </span>
    )
  }
  return <span>{text}</span>
}

function buildColumns(): DataTableColumn<ResultRow>[] {
  return [
    {
      id: 'symbol',
      header: 'Symbol',
      accessor: (r) => <span className="font-mono">{r.symbol}</span>,
    },
    {
      id: 'name',
      header: '名稱',
      accessor: (r) => (r.name as string | undefined) ?? '—',
    },
    {
      id: 'price',
      header: '現價',
      align: 'right',
      accessor: (r) =>
        r.price != null ? priceFmt.format(Number(r.price)) : '—',
    },
    {
      id: 'change_pct',
      header: '漲跌',
      align: 'right',
      accessor: (r) => (
        <ChangeCell value={(r.change_pct as number | null | undefined) ?? null} />
      ),
    },
    {
      id: 'pattern',
      header: 'Pattern',
      accessor: (r) => <PatternCell pattern={r.pattern as string | undefined} />,
    },
    {
      id: 'score',
      header: 'Score',
      align: 'right',
      sortable: true,
      accessor: (r) => {
        const s = (r.score as number | undefined) ?? 0
        return (
          <span
            className={cn('tabular', s >= 0.7 && 'font-medium')}
            data-testid="score-cell"
          >
            {s.toFixed(2)}
          </span>
        )
      },
    },
  ]
}

// ---------------------------------------------------------------------------
// Live feed row
// ---------------------------------------------------------------------------

function liveFeedIcon(eventType: string) {
  if (eventType === 'screener_started') {
    return <Hourglass className="size-3.5" aria-hidden />
  }
  if (eventType === 'screener_completed') {
    return <Search className="size-3.5" aria-hidden />
  }
  return <Activity className="size-3.5" aria-hidden />
}

function LiveFeedRow({ e }: { e: LiveEvent }) {
  const sym = (e.payload?.symbol as string | undefined) ?? '—'
  const note =
    (e.payload?.pattern as string | undefined) ??
    (e.payload?.note as string | undefined) ??
    e.event_type
  const time = dayjs(e.timestamp).format('HH:mm:ss')
  return (
    <li className="grid grid-cols-[auto_auto_minmax(0,1fr)_auto] items-center gap-3 border-b px-3 py-1.5 text-xs last:border-b-0">
      <span className="tabular text-[11px] text-muted-foreground">{time}</span>
      <span className="text-muted-foreground">
        {liveFeedIcon(e.event_type)}
      </span>
      <span className="truncate text-foreground">{note}</span>
      <span className="tabular text-muted-foreground">{sym}</span>
    </li>
  )
}

// ---------------------------------------------------------------------------
// MarketPage
// ---------------------------------------------------------------------------

export function MarketPage() {
  const navigate = useNavigate()
  useAdminEvents()

  const [universe, setUniverse] = useState<Universe>('tw50')
  const [customSymbols, setCustomSymbols] = useState<string[]>([])
  const [chipDraft, setChipDraft] = useState('')
  const [filters, setFilters] = useState<FilterFlags>({
    sepa: false,
    rsMin80: false,
    foreignBuyStreak: false,
    triangle: false,
  })
  const [asof, setAsof] = useState<string>(() => todayISO())
  const [rows, setRows] = useState<ResultRow[]>([])
  const [summary, setSummary] = useState<RunSummary | null>(null)
  const [, setNow] = useState(0) // tick to expire flash highlights

  const formRef = useRef<HTMLFormElement>(null)

  const screenerM = useMutation<ScreenerRun, ApiError, ScreenerInput>({
    mutationFn: (input) => runScreener(input),
    onSuccess: (data) => {
      const hits = (data.hits ?? data.candidates ?? []) as ResultRow[]
      setRows(hits)
      setSummary({
        runId: String(data.run_id ?? ''),
        hits: hits.length,
        elapsedMs: typeof data.elapsed_ms === 'number' ? data.elapsed_ms : null,
        asofIso: dayjs().format('HH:mm'),
      })
    },
  })

  const submit = useCallback(() => {
    const input = buildScreenerInput(universe, customSymbols, filters, asof)
    screenerM.mutate(input)
  }, [universe, customSymbols, filters, asof, screenerM])

  const onFormSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    submit()
  }

  // Cmd/Ctrl+Enter inside the form scope triggers a screener run.
  useEffect(() => {
    const form = formRef.current
    if (!form) return
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault()
        submit()
      }
    }
    form.addEventListener('keydown', handler)
    return () => form.removeEventListener('keydown', handler)
  }, [submit])

  // Chip input — Enter / "," → push chip; Backspace on empty → pop last.
  const onChipKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      const v = chipDraft.trim()
      if (v.length > 0 && !customSymbols.includes(v)) {
        e.preventDefault()
        setCustomSymbols((prev) => [...prev, v])
        setChipDraft('')
      } else if (v.length > 0) {
        e.preventDefault()
        setChipDraft('')
      }
    } else if (
      e.key === 'Backspace' &&
      chipDraft.length === 0 &&
      customSymbols.length > 0
    ) {
      e.preventDefault()
      setCustomSymbols((prev) => prev.slice(0, -1))
    }
  }
  const removeChip = (s: string) =>
    setCustomSymbols((prev) => prev.filter((x) => x !== s))

  // SSE → pattern_detected prepends a result row + flashes for 0.5s.
  useEffect(() => {
    let prevLen = useLiveFeedStore.getState().events.length
    const unsubscribe = useLiveFeedStore.subscribe((state) => {
      if (state.events.length === prevLen) return
      prevLen = state.events.length
      const latest = state.events[0]
      if (!latest) return
      if (latest.event_type !== 'pattern_detected') return
      const p = latest.payload ?? {}
      const sym = p.symbol as string | undefined
      if (!sym) return
      const hit: ResultRow = {
        symbol: sym,
        name: (p.name as string | undefined) ?? undefined,
        price: (p.price as number | undefined) ?? undefined,
        change_pct: (p.change_pct as number | null | undefined) ?? null,
        pattern: (p.pattern as string | undefined) ?? '',
        score: (p.score as number | undefined) ?? 0,
        _flashUntil: Date.now() + FLASH_DURATION_MS,
      }
      setRows((prev) => {
        const without = prev.filter((r) => r.symbol !== sym)
        return [hit, ...without]
      })
    })
    return () => unsubscribe()
  }, [])

  // Tick at 250 ms while any row has an active flash so the highlight expires.
  useEffect(() => {
    const hasFlash = rows.some(
      (r) => r._flashUntil != null && r._flashUntil > Date.now(),
    )
    if (!hasFlash) return
    const t = window.setInterval(() => setNow((x) => x + 1), 250)
    return () => window.clearInterval(t)
  }, [rows])

  const allEvents = useLiveFeedStore((s) => s.events)
  const filteredFeed = useMemo(
    () =>
      allEvents
        .filter((e) => LIVE_FEED_TYPES.has(e.event_type))
        .slice(0, LIVE_FEED_BUFFER),
    [allEvents],
  )

  const error = screenerM.error ? (screenerM.error as ApiError) : null
  const isLoading = screenerM.isPending
  const showEmpty = !isLoading && !error && summary != null && rows.length === 0
  const showResults = !isLoading && rows.length > 0

  const columns = useMemo(() => buildColumns(), [])

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">市場掃描</h1>
        <span className="text-[11px] text-muted-foreground">
          Cmd/Ctrl+Enter 跑 screener
        </span>
      </header>

      <form
        ref={formRef}
        onSubmit={onFormSubmit}
        className="rounded-lg border bg-card p-4 shadow-sm"
        aria-label="screener filter form"
      >
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[200px_1fr_auto]">
          <label className="flex flex-col gap-1 text-xs">
            <span className="font-medium text-muted-foreground">Universe</span>
            <select
              value={universe}
              onChange={(e) => setUniverse(e.target.value as Universe)}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="universe"
            >
              {UNIVERSES.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-xs">
            <span className="font-medium text-muted-foreground">
              Custom symbols
            </span>
            <div className="flex h-9 w-full flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-2">
              {customSymbols.map((s) => (
                <span
                  key={s}
                  data-chip
                  className="inline-flex items-center gap-1 rounded bg-secondary px-1.5 py-0.5 text-xs text-secondary-foreground"
                >
                  <span className="font-mono">{s}</span>
                  <button
                    type="button"
                    onClick={() => removeChip(s)}
                    aria-label={`移除 ${s}`}
                    className="cursor-pointer"
                  >
                    <X className="size-3" aria-hidden />
                  </button>
                </span>
              ))}
              <input
                value={chipDraft}
                onChange={(e) => setChipDraft(e.target.value)}
                onKeyDown={onChipKeyDown}
                placeholder={
                  customSymbols.length === 0 ? '輸入 symbol 後 Enter…' : ''
                }
                className="min-w-[80px] flex-1 bg-transparent text-sm outline-none"
                aria-label="custom symbols input"
              />
            </div>
          </label>

          <label className="flex flex-col gap-1 text-xs">
            <span className="font-medium text-muted-foreground">As-of</span>
            <input
              type="date"
              value={asof}
              onChange={(e) => setAsof(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="asof date"
            />
          </label>
        </div>

        <fieldset className="mt-3 flex flex-wrap items-center gap-4 text-sm">
          <legend className="sr-only">filters</legend>
          <CheckboxLabel
            label="SEPA"
            checked={filters.sepa}
            onChange={(v) => setFilters((s) => ({ ...s, sepa: v }))}
          />
          <CheckboxLabel
            label="RS≥80"
            checked={filters.rsMin80}
            onChange={(v) => setFilters((s) => ({ ...s, rsMin80: v }))}
          />
          <CheckboxLabel
            label="法人連續買超"
            checked={filters.foreignBuyStreak}
            onChange={(v) =>
              setFilters((s) => ({ ...s, foreignBuyStreak: v }))
            }
          />
          <CheckboxLabel
            label="三角收斂"
            checked={filters.triangle}
            onChange={(v) => setFilters((s) => ({ ...s, triangle: v }))}
          />
          <div className="ml-auto">
            <Button type="submit" disabled={isLoading}>
              <Search className="size-3.5" aria-hidden />
              跑 screener
            </Button>
          </div>
        </fieldset>
      </form>

      {error && (
        <Card
          role="alert"
          className="border-destructive/50 bg-destructive/5 p-3"
        >
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="size-4" aria-hidden />
              <span>screener.run 失敗 — {error.message}</span>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => submit()}
            >
              重試
            </Button>
          </div>
        </Card>
      )}

      <Card className="px-4 py-2 text-xs text-muted-foreground">
        {isLoading ? (
          <span className="inline-flex items-center gap-2">
            <Hourglass className="size-3.5 animate-pulse" aria-hidden />
            啟動中…
          </span>
        ) : summary ? (
          <span>
            r#{summary.runId || '—'} · {summary.asofIso} · 共 {summary.hits}{' '}
            命中
            {summary.elapsedMs != null
              ? ` · ${(summary.elapsedMs / 1000).toFixed(1)}s`
              : ''}
          </span>
        ) : (
          <span>尚未執行 screener — 設定 filter 後按「跑 screener」</span>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
        <section className="rounded-lg border bg-card shadow-sm">
          <header className="flex items-center justify-between border-b px-4 py-2.5">
            <h2 className="text-sm font-semibold">命中列表</h2>
            <span className="text-[11px] text-muted-foreground">
              {showResults ? `${rows.length} 筆` : ''}
            </span>
          </header>
          <div className="p-3">
            {isLoading ? (
              <DataTable<ResultRow>
                rows={[]}
                columns={columns}
                loading
                skeletonRows={5}
              />
            ) : showEmpty ? (
              <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
                <Search className="size-6" aria-hidden />
                <span>本次掃描無命中</span>
                <span className="text-[11px]">試試放寬 filter 條件</span>
              </div>
            ) : (
              <DataTable<ResultRow>
                rows={rows}
                columns={columns}
                onRowClick={(r) => navigate(`/market/${r.symbol}`)}
                rowKey={(r) => r.symbol}
                emptyMessage="尚未執行 screener"
              />
            )}
          </div>
        </section>

        <section className="flex h-full flex-col rounded-lg border bg-card shadow-sm">
          <header className="flex items-center justify-between border-b px-4 py-2.5">
            <h2 className="text-sm font-semibold">即時事件</h2>
            <span className="text-[11px] text-muted-foreground">
              {Math.min(filteredFeed.length, LIVE_FEED_RENDER)} /{' '}
              {LIVE_FEED_RENDER}
            </span>
          </header>
          {filteredFeed.length === 0 ? (
            <div className="flex flex-1 items-center justify-center p-6 text-sm text-muted-foreground">
              等待事件中…
            </div>
          ) : (
            <ul className="overflow-y-auto">
              {filteredFeed.slice(0, LIVE_FEED_RENDER).map((e, i) => (
                <LiveFeedRow key={`${e.timestamp}-${i}`} e={e} />
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}

function CheckboxLabel({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="size-4 rounded border-input"
        aria-label={label}
      />
      <span>{label}</span>
    </label>
  )
}
