/**
 * <RunSwarmDialog> — fires a swarm run for a chosen preset.
 *
 * Spec: openspec/changes/admin-swarm-endpoints-and-pages/specs/web-admin-swarm-pages/spec.md
 *
 * Triggered from <SwarmPage>'s preset Card "[Run...]" button. Submits to
 * `POST /api/admin/swarm/runs`; on success closes + invalidates the
 * ['swarm-runs'] React Query cache + toasts + navigates to the detail
 * page. On non-2xx the dialog stays open with an inline `{code}: {message}`.
 */
import * as React from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { AlertTriangle, Loader2 } from 'lucide-react'
import {
  ApiError,
  runSwarm,
  type SwarmPreset,
  type SwarmRunRow,
} from '@/lib/api'
import { toast } from '@/lib/toast'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const LAST_SWARM_KEY = 'ohmystock.admin.lastSwarm'

type PersistedFields = {
  period_from?: string
  period_to?: string
  limit_trades?: number | null
}

function loadPersisted(): PersistedFields {
  try {
    const raw = localStorage.getItem(LAST_SWARM_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as PersistedFields
    return typeof parsed === 'object' && parsed !== null ? parsed : {}
  } catch {
    return {}
  }
}

function persist(fields: PersistedFields): void {
  try {
    localStorage.setItem(LAST_SWARM_KEY, JSON.stringify(fields))
  } catch {
    /* localStorage unavailable */
  }
}

const fieldClasses =
  'block w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60'

export interface RunSwarmDialogProps {
  preset: SwarmPreset | null
  open: boolean
  onOpenChange: (next: boolean) => void
}

export function RunSwarmDialog({
  preset,
  open,
  onOpenChange,
}: RunSwarmDialogProps) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const [periodFrom, setPeriodFrom] = React.useState('')
  const [periodTo, setPeriodTo] = React.useState('')
  const [limitTradesRaw, setLimitTradesRaw] = React.useState('')
  const [dryRun, setDryRun] = React.useState(true)
  const [force, setForce] = React.useState(false)
  const [inlineError, setInlineError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!open) return
    const p = loadPersisted()
    setPeriodFrom(p.period_from ?? '')
    setPeriodTo(p.period_to ?? '')
    setLimitTradesRaw(
      p.limit_trades != null ? String(p.limit_trades) : '',
    )
    // dry_run + force always reset to safe defaults per spec.
    setDryRun(true)
    setForce(false)
    setInlineError(null)
  }, [open])

  const mutation = useMutation<
    SwarmRunRow,
    unknown,
    { presetName: string; params: Record<string, unknown> }
  >({
    mutationFn: ({ presetName, params }) =>
      runSwarm({ preset: presetName, params }),
    onSuccess: (row) => {
      persist({
        period_from: periodFrom,
        period_to: periodTo,
        limit_trades:
          limitTradesRaw === '' ? null : Number(limitTradesRaw),
      })
      queryClient.invalidateQueries({ queryKey: ['swarm-runs'] })
      onOpenChange(false)
      toast(
        row.status === 'completed'
          ? `Swarm 完成 — ${row.id}`
          : `Swarm 失敗 — ${row.id}`,
      )
      navigate(`/swarm/${row.preset}/${row.id}`)
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setInlineError(`${err.code}: ${err.message}`)
      } else {
        setInlineError(`unknown_error: ${String(err ?? 'unknown error')}`)
      }
    },
  })

  const submitting = mutation.isPending

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (submitting || !preset) return
    setInlineError(null)
    mutation.mutate({
      presetName: preset.name,
      params: {
        period_from: periodFrom,
        period_to: periodTo,
        limit_trades:
          limitTradesRaw === '' ? null : Number(limitTradesRaw),
        dry_run: dryRun,
        force,
      },
    })
  }

  const isFormValid =
    preset !== null &&
    periodFrom.length > 0 &&
    periodTo.length > 0 &&
    (limitTradesRaw === '' || Number(limitTradesRaw) >= 1)

  if (!preset) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{preset.title}</DialogTitle>
          <DialogDescription>
            跑一次 {preset.title}；勾選 dry-run 則不呼叫 LLM 也不寫檔。
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <label htmlFor="swarm-period-from" className="block space-y-1 text-sm">
              <span className="text-muted-foreground">起始日</span>
              <input
                id="swarm-period-from"
                type="date"
                value={periodFrom}
                onChange={(e) => setPeriodFrom(e.target.value)}
                required
                disabled={submitting}
                className={fieldClasses}
              />
            </label>
            <label htmlFor="swarm-period-to" className="block space-y-1 text-sm">
              <span className="text-muted-foreground">結束日</span>
              <input
                id="swarm-period-to"
                type="date"
                value={periodTo}
                onChange={(e) => setPeriodTo(e.target.value)}
                required
                disabled={submitting}
                className={fieldClasses}
              />
            </label>
          </div>

          <label htmlFor="swarm-limit-trades" className="block space-y-1 text-sm">
            <span className="text-muted-foreground">
              Limit trades（debug 用，留空 = 全部）
            </span>
            <input
              id="swarm-limit-trades"
              type="number"
              min={1}
              value={limitTradesRaw}
              onChange={(e) => setLimitTradesRaw(e.target.value)}
              disabled={submitting}
              className={fieldClasses}
            />
          </label>

          <label
            htmlFor="swarm-dry-run"
            className="flex cursor-pointer items-start gap-2 border-t pt-3 text-sm"
          >
            <input
              id="swarm-dry-run"
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              disabled={submitting}
              className="mt-0.5 size-4 cursor-pointer rounded border-input"
            />
            <span className="flex-1">
              <span className="inline-flex items-center gap-1">
                <AlertTriangle
                  className="size-4 text-warning"
                  aria-hidden="true"
                />
                Dry run
              </span>
              <span className="block text-xs text-muted-foreground">
                不呼叫 LLM、不寫檔；用來估 token / cost 並驗 pipeline 流。
              </span>
            </span>
          </label>

          <label
            htmlFor="swarm-force"
            className="flex cursor-pointer items-start gap-2 text-sm"
          >
            <input
              id="swarm-force"
              type="checkbox"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
              disabled={submitting}
              className="mt-0.5 size-4 cursor-pointer rounded border-input"
            />
            <span className="flex-1">
              Force overwrite
              <span className="block text-xs text-muted-foreground">
                覆寫既有 reviews/&lt;review_id&gt;/ 資料夾（提案檔仍受保護不被覆寫）。
              </span>
            </span>
          </label>

          {inlineError && (
            <p
              role="alert"
              aria-live="polite"
              className="text-sm text-destructive"
              data-testid="run-swarm-error"
            >
              {inlineError}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!isFormValid || submitting}>
              {submitting ? (
                <>
                  <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden />
                  執行中…
                </>
              ) : (
                'Submit'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
