/**
 * <ValidationDialog> — fires WFA validation against a `validating` proposal.
 *
 * Spec: openspec/changes/admin-proposal-validate-action/specs/web-admin-proposals-pages/spec.md
 *
 * Mounted from <ProposalDetailPage> when status === "validating". Submits to
 * `POST /api/admin/proposals/{slug}/validate`; on 200 closes + invalidates the
 * ['proposal', slug] React Query cache + fires a toast describing the verdict.
 * On non-2xx the dialog stays open with an inline `{code}: {message}` error.
 *
 * Layout (post ui-ux-pro review): single-column for decision-relevant fields
 * (Strategy / Period / Universe / Params); 3-col grid for the numeric tuning
 * triad (WFA windows / IS ratio / Initial capital); Dry-run lives at the
 * bottom above the footer (submit-modifier semantics).
 */
import * as React from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import {
  ApiError,
  validateProposal,
  type BacktestStrategy,
  type ValidateRequest,
  type ValidateResponse,
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

const LAST_VALIDATION_KEY = 'ohmystock.admin.lastValidation'

type PersistedFields = {
  strategy: string
  universe: string
  wfa_windows: number
  in_sample_ratio: number
  initial_capital: number
}

function loadPersisted(): Partial<PersistedFields> {
  try {
    const raw = localStorage.getItem(LAST_VALIDATION_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Partial<PersistedFields>
    if (typeof parsed !== 'object' || parsed === null) return {}
    return parsed
  } catch {
    return {}
  }
}

function persist(fields: PersistedFields): void {
  try {
    localStorage.setItem(LAST_VALIDATION_KEY, JSON.stringify(fields))
  } catch {
    /* localStorage unavailable — non-fatal */
  }
}

function toastMessage(
  dryRun: boolean,
  result: ValidateResponse,
): string {
  const n = result.failures.length
  if (dryRun) {
    return result.verdict === 'pass'
      ? 'Dry run: verdict=pass — no state change'
      : `Dry run: verdict=fail — no state change — ${n} failure(s)`
  }
  return result.verdict === 'pass'
    ? 'Validated: verdict=pass — moved to PENDING_REVIEW'
    : `Validated: verdict=fail — moved to rejected — ${n} failure(s)`
}

export interface ValidationDialogProps {
  slug: string
  strategies: BacktestStrategy[]
  open: boolean
  onOpenChange: (next: boolean) => void
}

const fieldClasses =
  'block w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60'

export function ValidationDialog({
  slug,
  strategies,
  open,
  onOpenChange,
}: ValidationDialogProps) {
  const queryClient = useQueryClient()

  const [strategy, setStrategy] = React.useState('')
  const [periodFrom, setPeriodFrom] = React.useState('')
  const [periodTo, setPeriodTo] = React.useState('')
  const [universeRaw, setUniverseRaw] = React.useState('2330,0050,2317')
  const [paramOverridesRaw, setParamOverridesRaw] = React.useState('')
  const [wfaWindows, setWfaWindows] = React.useState(5)
  const [inSampleRatio, setInSampleRatio] = React.useState(0.7)
  const [initialCapital, setInitialCapital] = React.useState(1_000_000)
  const [dryRun, setDryRun] = React.useState(false)
  const [inlineError, setInlineError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!open) return
    const p = loadPersisted()
    setStrategy(p.strategy ?? strategies[0]?.name ?? '')
    setUniverseRaw(p.universe ?? '2330,0050,2317')
    setWfaWindows(p.wfa_windows ?? 5)
    setInSampleRatio(p.in_sample_ratio ?? 0.7)
    setInitialCapital(p.initial_capital ?? 1_000_000)
    // Date-specific + proposal-specific fields always reset per spec D7.
    setPeriodFrom('')
    setPeriodTo('')
    setParamOverridesRaw('')
    setDryRun(false)
    setInlineError(null)
  }, [open, strategies])

  const mutation = useMutation<ValidateResponse, unknown, ValidateRequest>({
    mutationFn: (body) => validateProposal(slug, body),
    onSuccess: (data) => {
      persist({
        strategy,
        universe: universeRaw,
        wfa_windows: wfaWindows,
        in_sample_ratio: inSampleRatio,
        initial_capital: initialCapital,
      })
      queryClient.invalidateQueries({ queryKey: ['proposal', slug] })
      queryClient.invalidateQueries({ queryKey: ['proposals'] })
      onOpenChange(false)
      toast(toastMessage(dryRun, data))
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
    if (submitting) return

    setInlineError(null)

    const universe = universeRaw
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0)

    const paramOverrides = paramOverridesRaw
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0)

    const body: ValidateRequest = {
      strategy,
      period: { from: periodFrom, to: periodTo },
      param_overrides: paramOverrides,
      universe,
      wfa_windows: wfaWindows,
      in_sample_ratio: inSampleRatio,
      initial_capital: initialCapital,
      dry_run: dryRun,
    }
    mutation.mutate(body)
  }

  const isFormValid =
    strategy.length > 0 &&
    periodFrom.length > 0 &&
    periodTo.length > 0 &&
    universeRaw.trim().length > 0 &&
    wfaWindows >= 2 &&
    inSampleRatio > 0 &&
    inSampleRatio < 1 &&
    initialCapital > 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Run Validation</DialogTitle>
          <DialogDescription>
            對 validating proposal 跑 walk-forward 驗證；pass 移到
            PENDING_REVIEW，fail 移到 rejected。勾選 Dry run 只算 verdict
            不變動狀態。
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-3">
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">Strategy</span>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              required
              disabled={submitting || strategies.length === 0}
              className={fieldClasses}
            >
              {strategies.length === 0 && (
                <option value="">（無可用策略）</option>
              )}
              {strategies.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name} — {s.description}
                </option>
              ))}
            </select>
          </label>

          <div className="grid grid-cols-2 gap-2">
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">Period from</span>
              <input
                type="date"
                value={periodFrom}
                onChange={(e) => setPeriodFrom(e.target.value)}
                required
                disabled={submitting}
                className={fieldClasses}
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">Period to</span>
              <input
                type="date"
                value={periodTo}
                onChange={(e) => setPeriodTo(e.target.value)}
                required
                disabled={submitting}
                className={fieldClasses}
              />
            </label>
          </div>

          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">
              Universe (comma-separated)
            </span>
            <input
              type="text"
              value={universeRaw}
              onChange={(e) => setUniverseRaw(e.target.value)}
              placeholder="2330,0050,2317"
              required
              disabled={submitting}
              className={`${fieldClasses} font-mono`}
            />
          </label>

          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">
              Parameter overrides (one key=value per line)
            </span>
            <textarea
              value={paramOverridesRaw}
              onChange={(e) => setParamOverridesRaw(e.target.value)}
              placeholder={'fast=10\nslow=20'}
              rows={3}
              disabled={submitting}
              className={`${fieldClasses} font-mono`}
            />
          </label>

          <div className="grid grid-cols-3 gap-2">
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">WFA windows</span>
              <input
                type="number"
                min={2}
                value={wfaWindows}
                onChange={(e) => setWfaWindows(Number(e.target.value))}
                required
                disabled={submitting}
                className={fieldClasses}
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">IS ratio</span>
              <input
                type="number"
                step={0.01}
                min={0}
                max={1}
                value={inSampleRatio}
                onChange={(e) => setInSampleRatio(Number(e.target.value))}
                required
                disabled={submitting}
                className={fieldClasses}
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">Initial capital</span>
              <input
                type="number"
                min={1}
                value={initialCapital}
                onChange={(e) => setInitialCapital(Number(e.target.value))}
                required
                disabled={submitting}
                className={fieldClasses}
              />
            </label>
          </div>

          <label className="flex cursor-pointer items-center gap-2 border-t pt-3 text-sm">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              disabled={submitting}
              className="size-4 cursor-pointer rounded border-input"
            />
            <span>
              Dry run
              <span className="ml-1 text-muted-foreground">
                — 只算 verdict 不變動狀態
              </span>
            </span>
          </label>

          {inlineError && (
            <p
              role="alert"
              aria-live="polite"
              className="text-sm text-destructive"
              data-testid="validation-error"
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
                  <Loader2 className="animate-spin" aria-hidden />
                  驗證中…
                </>
              ) : (
                'Run Validation'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
