import * as React from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Hourglass,
  Play,
  RotateCcw,
  TrendingDown,
  X,
} from 'lucide-react'
import dayjs from 'dayjs'
import {
  ApiError,
  listBacktestJobs,
  listStrategies,
  runBacktest,
  type BacktestJobSummary,
  type BacktestRunInput,
  type BacktestStrategy,
} from '@/lib/api'
import { DataTable, type DataTableColumn } from '@/components/data-table'
import { StatusBadge } from '@/components/status-badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const pctFmt = new Intl.NumberFormat('zh-TW', {
  style: 'percent',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const numFmt = new Intl.NumberFormat('zh-TW', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const DEFAULT_INITIAL_CAPITAL = 1_000_000
const SYMBOL_RE = /^\d{4,6}$/

function todayISO(): string {
  return dayjs().format('YYYY-MM-DD')
}

function aYearAgoISO(): string {
  return dayjs().subtract(365, 'day').format('YYYY-MM-DD')
}

// ---------------------------------------------------------------------------
// 紅漲綠跌 cells (annual / sharpe / maxdd)
// ---------------------------------------------------------------------------

function AnnualCell({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-muted-foreground">—</span>
  if (value > 0) {
    return (
      <span className="inline-flex items-center justify-end gap-1 text-up tabular">
        <ArrowUp className="size-3" aria-hidden />
        {pctFmt.format(value)}
      </span>
    )
  }
  if (value < 0) {
    return (
      <span className="inline-flex items-center justify-end gap-1 text-down tabular">
        <ArrowDown className="size-3" aria-hidden />
        {pctFmt.format(value)}
      </span>
    )
  }
  return <span className="tabular text-muted-foreground">{pctFmt.format(0)}</span>
}

function SharpeCell({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-muted-foreground">—</span>
  const dir = value > 1 ? 'up' : value < 0 ? 'down' : 'neutral'
  return (
    <span
      className={cn(
        'inline-flex items-center justify-end gap-1 tabular',
        dir === 'up' && 'text-up',
        dir === 'down' && 'text-down',
      )}
    >
      {dir === 'up' && <ArrowUp className="size-3" aria-hidden />}
      {dir === 'down' && <ArrowDown className="size-3" aria-hidden />}
      {numFmt.format(value)}
    </span>
  )
}

function MaxDDCell({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-muted-foreground">—</span>
  return (
    <span className="inline-flex items-center justify-end gap-1 text-down tabular">
      <TrendingDown className="size-3" aria-hidden />
      {pctFmt.format(value)}
    </span>
  )
}

// ---------------------------------------------------------------------------
// History columns
// ---------------------------------------------------------------------------

function StatusCell({ status }: { status: 'completed' | 'failed' }) {
  if (status === 'completed') {
    return <StatusBadge status="executed" label="完成" />
  }
  return <StatusBadge status="errored" label="失敗" />
}

function buildHistoryColumns(): DataTableColumn<BacktestJobSummary>[] {
  return [
    {
      id: 'id',
      header: 'JobId',
      accessor: (r) => (
        <span className="font-mono text-xs">{r.id.slice(0, 8)}…</span>
      ),
    },
    { id: 'strategy', header: '策略', accessor: (r) => r.strategy },
    {
      id: 'period',
      header: '期間',
      accessor: (r) => (
        <span className="tabular text-xs">
          {r.period_from} ~ {r.period_to}
        </span>
      ),
    },
    {
      id: 'annual',
      header: '年化',
      align: 'right',
      accessor: (r) => <AnnualCell value={r.annual_return_pct} />,
    },
    {
      id: 'sharpe',
      header: 'Sharpe',
      align: 'right',
      accessor: (r) => <SharpeCell value={r.sharpe} />,
    },
    {
      id: 'maxdd',
      header: 'MaxDD',
      align: 'right',
      accessor: (r) => <MaxDDCell value={r.max_drawdown_pct} />,
    },
    {
      id: 'status',
      header: '狀態',
      accessor: (r) => <StatusCell status={r.status} />,
    },
    {
      id: 'created_at',
      header: '建立時間',
      accessor: (r) => (
        <span className="tabular text-xs">
          {dayjs(r.created_at).format('MM-DD HH:mm')}
        </span>
      ),
    },
  ]
}

// ---------------------------------------------------------------------------
// BacktestPage
// ---------------------------------------------------------------------------

export function BacktestPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const formRef = useRef<HTMLFormElement>(null)
  const [strategy, setStrategy] = useState<string>('sma_cross')
  const [symbols, setSymbols] = useState<string[]>([])
  const [chipDraft, setChipDraft] = useState('')
  const [periodFrom, setPeriodFrom] = useState<string>(() => aYearAgoISO())
  const [periodTo, setPeriodTo] = useState<string>(() => todayISO())
  const [initialCapital, setInitialCapital] = useState<number>(
    DEFAULT_INITIAL_CAPITAL,
  )

  const strategiesQ = useQuery({
    queryKey: ['backtest', 'strategies'],
    queryFn: () => listStrategies(),
  })
  const jobsQ = useQuery({
    queryKey: ['backtest', 'jobs'],
    queryFn: () => listBacktestJobs(50),
  })

  const runM = useMutation<
    Awaited<ReturnType<typeof runBacktest>>,
    ApiError,
    BacktestRunInput
  >({
    mutationFn: (input) => runBacktest(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backtest', 'jobs'] })
    },
  })

  const submit = useCallback(() => {
    runM.mutate({
      strategy,
      symbols,
      period_from: periodFrom,
      period_to: periodTo,
      initial_capital: initialCapital,
    })
  }, [strategy, symbols, periodFrom, periodTo, initialCapital, runM])

  const onFormSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    submit()
  }

  // Cmd/Ctrl+Enter inside the form scope.
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

  // Chip input — Enter / "," → push; Backspace on empty → pop.
  const onChipKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      const v = chipDraft.trim()
      if (v.length > 0 && !symbols.includes(v) && SYMBOL_RE.test(v)) {
        e.preventDefault()
        setSymbols((prev) => [...prev, v])
        setChipDraft('')
      } else if (v.length > 0) {
        e.preventDefault()
        setChipDraft('')
      }
    } else if (
      e.key === 'Backspace' &&
      chipDraft.length === 0 &&
      symbols.length > 0
    ) {
      e.preventDefault()
      setSymbols((prev) => prev.slice(0, -1))
    }
  }
  const removeChip = (s: string) =>
    setSymbols((prev) => prev.filter((x) => x !== s))

  const onReset = () => {
    setSymbols([])
    setChipDraft('')
    setPeriodFrom(aYearAgoISO())
    setPeriodTo(todayISO())
  }

  const strategiesList: BacktestStrategy[] =
    strategiesQ.data?.strategies ?? [{ name: 'sma_cross', description: '' }]
  const jobs = jobsQ.data?.items ?? []
  const error = runM.error ? (runM.error as ApiError) : null
  const submitting = runM.isPending

  const columns = useMemo(() => buildHistoryColumns(), [])

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">回測</h1>
        <span className="text-[11px] text-muted-foreground">
          Cmd/Ctrl+Enter 跑回測
        </span>
      </header>

      <form
        ref={formRef}
        onSubmit={onFormSubmit}
        className="rounded-lg border bg-card p-4 shadow-sm"
        aria-label="backtest filter form"
      >
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[200px_1fr_auto_auto]">
          <label className="flex flex-col gap-1 text-xs">
            <span className="font-medium text-muted-foreground">策略</span>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="strategy"
            >
              {strategiesList.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-xs">
            <span className="font-medium text-muted-foreground">
              Custom symbols
            </span>
            <div className="flex h-9 w-full flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-2">
              {symbols.map((s) => (
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
                  symbols.length === 0 ? '輸入 symbol 後 Enter…' : ''
                }
                className="min-w-[80px] flex-1 bg-transparent text-sm outline-none"
                aria-label="custom symbols input"
              />
            </div>
          </label>

          <label className="flex flex-col gap-1 text-xs">
            <span className="font-medium text-muted-foreground">起日</span>
            <input
              type="date"
              value={periodFrom}
              onChange={(e) => setPeriodFrom(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="period from"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs">
            <span className="font-medium text-muted-foreground">迄日</span>
            <input
              type="date"
              value={periodTo}
              onChange={(e) => setPeriodTo(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="period to"
            />
          </label>
        </div>

        <div className="mt-3 flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1 text-xs">
            <span className="font-medium text-muted-foreground">初始資金</span>
            <input
              type="number"
              value={initialCapital}
              min={1}
              step={1}
              onChange={(e) =>
                setInitialCapital(
                  Number(e.target.value) || DEFAULT_INITIAL_CAPITAL,
                )
              }
              className="h-9 w-40 rounded-md border border-input bg-background px-2 text-sm tabular focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="initial capital"
            />
          </label>
          <div className="ml-auto flex gap-2">
            <Button type="reset" variant="outline" onClick={onReset}>
              <RotateCcw className="size-3.5" aria-hidden />
              清空
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? (
                <>
                  <Hourglass
                    className="size-3.5 animate-pulse"
                    aria-hidden
                  />
                  啟動中…
                </>
              ) : (
                <>
                  <Play className="size-3.5" aria-hidden />
                  跑回測
                </>
              )}
            </Button>
          </div>
        </div>
      </form>

      {error && (
        <Card
          role="alert"
          className="border-destructive/50 bg-destructive/5 p-3"
        >
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="size-4" aria-hidden />
              <span>backtest.run 失敗 — {error.message}</span>
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

      <section className="rounded-lg border bg-card shadow-sm">
        <header className="flex items-center justify-between border-b px-4 py-2.5">
          <h2 className="text-sm font-semibold">歷史回測</h2>
          <span className="text-[11px] text-muted-foreground">
            {jobs.length > 0 ? `${jobs.length} 筆` : ''}
          </span>
        </header>
        <div className="p-3">
          {jobsQ.isLoading ? (
            <DataTable<BacktestJobSummary>
              rows={[]}
              columns={columns}
              loading
              skeletonRows={3}
            />
          ) : jobs.length === 0 ? (
            <div className="flex flex-col items-center gap-1 py-8 text-center text-sm text-muted-foreground">
              <span>尚未跑過回測</span>
              <span className="text-[11px]">填上方表單後點「跑回測 →」</span>
            </div>
          ) : (
            <DataTable<BacktestJobSummary>
              rows={jobs}
              columns={columns}
              onRowClick={(r) => navigate(`/backtest/${r.id}`)}
              rowKey={(r) => r.id}
            />
          )}
        </div>
      </section>
    </div>
  )
}
