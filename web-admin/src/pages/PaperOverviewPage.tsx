import * as React from 'react'
import { useEffect, useMemo, useRef } from 'react'
import { Link } from 'react-router'
import {
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query'
import {
  Activity,
  AlertCircle,
  Briefcase,
  Check,
  DollarSign,
  Hourglass,
  Inbox,
  ListOrdered,
  Trash2,
  X,
} from 'lucide-react'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-tw'
import { apiFetch, type LiveEvent } from '@/lib/api'
import { useAdminEvents } from '@/hooks/useAdminEvents'
import { useLiveFeedStore } from '@/stores'
import { KpiCard } from '@/components/kpi-card'
import { DataTable, type DataTableColumn } from '@/components/data-table'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

dayjs.extend(relativeTime)
dayjs.locale('zh-tw')

// Local types — backend response shapes (legacy `StatsToday` / `OpenPosition`
// in lib/api.ts have stale field names tracked by a separate change).

type PaperStatsToday = {
  asof_date: string
  decisions_made: number
  entries_pending: number
  entries_filled: number
  rejects: number
  expires: number
  auto_execute_audits: number
}

type PendingItem = {
  decision_id: string
  symbol: string
  created_at: string
  age_seconds: number
  ttl_seconds: number
  current_price: number
  final_sizing_pct: number
}

type PendingResponse = {
  items: PendingItem[]
  timeout_minutes: number
}

type PaperPositionItem = {
  decision_id: string
  symbol: string
  sector: string
  entry_price: number
  qty_lots: number
  entry_ts: string
  hold_days: number
  stop_loss: number | null
  t1_target: number | null
  time_stop_date: string | null
}

type PositionsOpenResponse = {
  items: PaperPositionItem[]
  asof_iso: string
  count: number
}

const PAPER_EVENT_TYPES = new Set([
  'awaiting_confirm',
  'order_sent',
  'decision_made',
  'journal_written',
  'risk_off_triggered',
])

const numFmt = new Intl.NumberFormat('zh-TW')
const priceFmt = new Intl.NumberFormat('zh-TW', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const pctFmt = new Intl.NumberFormat('zh-TW', {
  style: 'percent',
  minimumFractionDigits: 1,
  maximumFractionDigits: 2,
})

function KpiCellError({ label, message }: { label: string; message: string }) {
  return (
    <Card className="rounded-lg p-4">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="mt-2 flex items-center gap-1.5 text-sm text-destructive">
        <AlertCircle className="size-4" aria-hidden />
        <span className="truncate">{message}</span>
      </div>
    </Card>
  )
}

function PendingCard({
  item,
  onConfirm,
  onReject,
  pending,
}: {
  item: PendingItem
  onConfirm: (decision_id: string) => void
  onReject: (decision_id: string) => void
  pending: boolean
}) {
  const ttl = Math.max(item.ttl_seconds, 1)
  const remaining = Math.max(0, ttl - item.age_seconds)
  const remainingPct = Math.min(100, Math.max(0, (remaining / ttl) * 100))

  return (
    <Card
      tabIndex={0}
      data-pending-card
      data-decision-id={item.decision_id}
      className="space-y-2 p-3 outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-sm font-semibold">{item.symbol}</span>
          <span className="text-xs text-muted-foreground">
            @ {priceFmt.format(item.current_price)}
          </span>
        </div>
        <span className="text-xs tabular text-muted-foreground">
          {pctFmt.format(item.final_sizing_pct)}
        </span>
      </div>
      <div
        className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label="待確認剩餘時間"
        aria-valuenow={Math.round(remaining)}
        aria-valuemin={0}
        aria-valuemax={Math.round(ttl)}
      >
        <div
          className={cn(
            'h-full transition-[width]',
            remainingPct > 33 ? 'bg-primary' : 'bg-warning',
          )}
          style={{ width: `${remainingPct}%` }}
        />
      </div>
      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span>剩餘 {Math.round(remaining)}s / {Math.round(ttl)}s</span>
        <span className="tabular">{dayjs(item.created_at).fromNow()}</span>
      </div>
      <div className="flex gap-2 pt-1">
        <Button
          type="button"
          size="sm"
          disabled={pending}
          onClick={() => onConfirm(item.decision_id)}
          aria-label={`確認 ${item.symbol}`}
        >
          <Check className="size-3" aria-hidden />
          ✓ 確認
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={pending}
          onClick={() => onReject(item.decision_id)}
          aria-label={`拒絕 ${item.symbol}`}
        >
          <X className="size-3" aria-hidden />
          ✗ 拒絕
        </Button>
      </div>
    </Card>
  )
}

function eventIcon(eventType: string) {
  if (eventType === 'awaiting_confirm') return <Hourglass className="size-3.5" aria-hidden />
  if (eventType === 'order_sent') return <Briefcase className="size-3.5" aria-hidden />
  if (eventType === 'decision_made') return <DollarSign className="size-3.5" aria-hidden />
  if (eventType === 'risk_off_triggered') return <AlertCircle className="size-3.5" aria-hidden />
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

const POSITIONS_COLUMNS: DataTableColumn<PaperPositionItem>[] = [
  { id: 'symbol', header: 'Symbol', accessor: (r) => r.symbol },
  { id: 'side', header: '方向', accessor: () => '多' },
  {
    id: 'qty',
    header: 'Qty',
    align: 'right',
    accessor: (r) => numFmt.format(r.qty_lots),
  },
  {
    id: 'entry_price',
    header: 'Entry',
    align: 'right',
    accessor: (r) => priceFmt.format(r.entry_price),
  },
  {
    id: 'stop_loss',
    header: '停損',
    align: 'right',
    accessor: (r) => (r.stop_loss == null ? '—' : priceFmt.format(r.stop_loss)),
  },
  {
    id: 'days_left',
    header: '剩餘日',
    align: 'right',
    accessor: (r) => {
      if (!r.time_stop_date) return '—'
      const today = dayjs().startOf('day')
      const stop = dayjs(r.time_stop_date).startOf('day')
      const days = stop.diff(today, 'day')
      return numFmt.format(days)
    },
  },
]

export function PaperOverviewPage() {
  const queryClient = useQueryClient()

  // CG-B2: reject reason dialog state (reason is user-entered, not hard-coded).
  const [rejectTarget, setRejectTarget] = React.useState<string | null>(null)
  const [rejectReason, setRejectReason] = React.useState('')

  // SSE entry point on the /paper route. Layout/DashboardPage do not subscribe
  // when this route is mounted, so this page owns the single subscription.
  useAdminEvents()

  const statsQ = useQuery({
    queryKey: ['stats', 'today'],
    queryFn: () => apiFetch<PaperStatsToday>('/api/admin/stats/today'),
    refetchInterval: 30_000,
  })
  const positionsQ = useQuery({
    queryKey: ['positions', 'open'],
    queryFn: () =>
      apiFetch<PositionsOpenResponse>('/api/admin/positions/open'),
    refetchInterval: 30_000,
  })
  const pendingQ = useQuery({
    queryKey: ['confirm-gate', 'pending'],
    queryFn: () =>
      apiFetch<PendingResponse>('/api/admin/confirm-gate/pending'),
    refetchInterval: 15_000,
  })

  const invalidateAll = React.useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['stats', 'today'] })
    queryClient.invalidateQueries({ queryKey: ['positions', 'open'] })
    queryClient.invalidateQueries({ queryKey: ['confirm-gate', 'pending'] })
  }, [queryClient])

  const confirmM = useMutation({
    mutationFn: (decision_id: string) =>
      apiFetch('/api/admin/confirm-gate/confirm', {
        method: 'POST',
        body: JSON.stringify({ decision_id, user: 'mark' }),
      }),
    onSettled: invalidateAll,
  })

  const rejectM = useMutation({
    // CG-B2: reason is collected from the user via the reject dialog (no longer
    // hard-coded). Backend RejectRequest requires a non-empty `reason`.
    mutationFn: ({
      decision_id,
      reason,
    }: {
      decision_id: string
      reason: string
    }) =>
      apiFetch('/api/admin/confirm-gate/reject', {
        method: 'POST',
        body: JSON.stringify({ decision_id, user: 'mark', reason }),
      }),
    onSuccess: () => {
      setRejectTarget(null)
      setRejectReason('')
    },
    onSettled: invalidateAll,
  })

  const sweepM = useMutation({
    mutationFn: () =>
      apiFetch('/api/admin/confirm-gate/sweep-expired', {
        method: 'POST',
        body: '{}',
      }),
    onSettled: invalidateAll,
  })

  const onConfirm = React.useCallback(
    (decision_id: string) => confirmM.mutate(decision_id),
    [confirmM],
  )
  const onReject = React.useCallback((decision_id: string) => {
    setRejectReason('')
    setRejectTarget(decision_id)
  }, [])
  const onSweep = React.useCallback(() => {
    if (!window.confirm('確定要 sweep 所有過期的待確認單？')) return
    sweepM.mutate()
  }, [sweepM])

  // Stable refs so the keydown listener (mounted once) sees latest handlers.
  const onConfirmRef = useRef(onConfirm)
  const onRejectRef = useRef(onReject)
  const onSweepRef = useRef(onSweep)
  onConfirmRef.current = onConfirm
  onRejectRef.current = onReject
  onSweepRef.current = onSweep

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const tgt = event.target as HTMLElement | null
      if (
        tgt &&
        (tgt.tagName === 'INPUT' ||
          tgt.tagName === 'TEXTAREA' ||
          tgt.isContentEditable)
      ) {
        return
      }

      const key = event.key.toLowerCase()

      if ((event.metaKey || event.ctrlKey) && event.shiftKey && key === 'e') {
        event.preventDefault()
        onSweepRef.current()
        return
      }

      if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return
      if (key !== 'y' && key !== 'n') return

      const active = document.activeElement as HTMLElement | null
      if (!active) return
      const card = active.closest('[data-pending-card]') as HTMLElement | null
      if (!card) return
      const decisionId = card.getAttribute('data-decision-id')
      if (!decisionId) return

      event.preventDefault()
      if (key === 'y') onConfirmRef.current(decisionId)
      else onRejectRef.current(decisionId)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // SSE → invalidate on whitelisted event_type (newest at index 0).
  useEffect(() => {
    let prevLen = useLiveFeedStore.getState().events.length
    const unsubscribe = useLiveFeedStore.subscribe((state) => {
      if (state.events.length === prevLen) return
      prevLen = state.events.length
      const latest = state.events[0]
      if (!latest) return
      if (PAPER_EVENT_TYPES.has(latest.event_type)) {
        invalidateAll()
      }
    })
    return () => unsubscribe()
  }, [invalidateAll])

  const allEvents = useLiveFeedStore((s) => s.events)
  const filteredEvents = useMemo(
    () =>
      allEvents.filter((e) => PAPER_EVENT_TYPES.has(e.event_type)).slice(0, 8),
    [allEvents],
  )

  const decisionsMade = statsQ.data?.decisions_made
  const entriesFilled = statsQ.data?.entries_filled
  const positionsCount = positionsQ.data?.count
  const pendingCount = pendingQ.data?.items.length

  const pendingItems = pendingQ.data?.items ?? []
  const positionsItems = positionsQ.data?.items ?? []
  const positionsTop5 = positionsItems.slice(0, 5)

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">模擬交易</h1>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onSweep}
          disabled={sweepM.isPending}
          title="Cmd/Ctrl+Shift+E"
        >
          <Trash2 className="size-3" aria-hidden />
          全部 sweep 過期
        </Button>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {statsQ.error ? (
          <KpiCellError label="今日決策" message={(statsQ.error as Error).message} />
        ) : (
          <KpiCard
            label="今日決策"
            value={decisionsMade != null ? numFmt.format(decisionsMade) : ''}
            direction="neutral"
            loading={statsQ.isLoading}
          />
        )}
        {positionsQ.error ? (
          <KpiCellError label="持倉檔數" message={(positionsQ.error as Error).message} />
        ) : (
          <KpiCard
            label="持倉檔數"
            value={positionsCount != null ? numFmt.format(positionsCount) : ''}
            direction="neutral"
            loading={positionsQ.isLoading}
          />
        )}
        {pendingQ.error ? (
          <KpiCellError label="待確認" message={(pendingQ.error as Error).message} />
        ) : (
          <KpiCard
            label="待確認"
            value={pendingCount != null ? numFmt.format(pendingCount) : ''}
            direction="neutral"
            loading={pendingQ.isLoading}
          />
        )}
        {statsQ.error ? (
          <KpiCellError label="今日已成交" message={(statsQ.error as Error).message} />
        ) : (
          <KpiCard
            label="今日已成交"
            value={entriesFilled != null ? numFmt.format(entriesFilled) : ''}
            direction="neutral"
            loading={statsQ.isLoading}
          />
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-4">
          <section className="rounded-lg border bg-card shadow-sm">
            <header className="flex items-center justify-between border-b px-4 py-2.5">
              <h2 className="text-sm font-semibold">待確認列表</h2>
              <span className="text-[11px] text-muted-foreground">
                Y 確認 / N 拒絕（focus 該卡）
              </span>
            </header>
            <div className="p-3">
              {pendingQ.isLoading ? (
                <div className="text-xs text-muted-foreground">載入中…</div>
              ) : pendingQ.error ? (
                <div className="flex items-center gap-2 text-sm text-destructive">
                  <AlertCircle className="size-4" aria-hidden />
                  <span>載入失敗：{(pendingQ.error as Error).message}</span>
                </div>
              ) : pendingItems.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-6 text-sm text-muted-foreground">
                  <Inbox className="size-6" aria-hidden />
                  <span>目前無待確認</span>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {pendingItems.map((item) => (
                    <PendingCard
                      key={item.decision_id}
                      item={item}
                      onConfirm={onConfirm}
                      onReject={onReject}
                      pending={confirmM.isPending || rejectM.isPending}
                    />
                  ))}
                </div>
              )}
            </div>
          </section>

          <section className="rounded-lg border bg-card shadow-sm">
            <header className="flex items-center justify-between border-b px-4 py-2.5">
              <h2 className="text-sm font-semibold">開倉摘要</h2>
              {positionsItems.length > 5 && (
                <Link
                  to="/paper/positions"
                  className="text-xs text-primary hover:underline"
                >
                  → 詳細看 /paper/positions
                </Link>
              )}
            </header>
            <div className="p-3">
              {positionsQ.error ? (
                <div className="flex items-center gap-2 text-sm text-destructive">
                  <AlertCircle className="size-4" aria-hidden />
                  <span>載入失敗：{(positionsQ.error as Error).message}</span>
                </div>
              ) : !positionsQ.isLoading && positionsItems.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-6 text-sm text-muted-foreground">
                  <ListOrdered className="size-6" aria-hidden />
                  <span>目前無開倉</span>
                </div>
              ) : (
                <DataTable<PaperPositionItem>
                  rows={positionsTop5}
                  columns={POSITIONS_COLUMNS}
                  loading={positionsQ.isLoading}
                  rowKey={(r) => r.decision_id}
                  skeletonRows={3}
                />
              )}
            </div>
          </section>
        </div>

        <section className="flex h-full flex-col rounded-lg border bg-card shadow-sm">
          <header className="flex items-center justify-between border-b px-4 py-2.5">
            <h2 className="text-sm font-semibold">即時事件</h2>
            <span className="text-[11px] text-muted-foreground">
              {filteredEvents.length} / 8
            </span>
          </header>
          {filteredEvents.length === 0 ? (
            <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted-foreground">
              等待事件中…
            </div>
          ) : (
            <ul className="overflow-y-auto">
              {filteredEvents.map((e, i) => (
                <LiveFeedRow key={`${e.timestamp}-${i}`} e={e} />
              ))}
            </ul>
          )}
        </section>
      </div>

      <Dialog
        open={rejectTarget !== null}
        onOpenChange={(o) => {
          if (!o) {
            setRejectTarget(null)
            setRejectReason('')
          }
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>拒絕決策</DialogTitle>
            <DialogDescription>
              輸入拒絕原因後送出（會寫入 journal）。
            </DialogDescription>
          </DialogHeader>
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">拒絕原因（必填）</span>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={3}
              placeholder="例：這檔我前年被套過，先觀望"
              aria-label="拒絕原因"
              className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setRejectTarget(null)
                setRejectReason('')
              }}
              disabled={rejectM.isPending}
            >
              取消
            </Button>
            <Button
              type="button"
              onClick={() => {
                const reason = rejectReason.trim()
                if (!rejectTarget || !reason) return
                rejectM.mutate({ decision_id: rejectTarget, reason })
              }}
              disabled={rejectM.isPending || rejectReason.trim().length === 0}
            >
              確認拒絕
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
