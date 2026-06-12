/**
 * <TransitionDialog> — collects required args and submits a proposal
 * status transition.
 *
 * One Dialog component drives 3 forms by `target` prop:
 *   - 'approved' → actor + validation_report_path
 *   - 'merged'   → actor + merged_to_version
 *   - 'rejected' → actor + reason (Textarea)
 *
 * For 'validating' the caller uses <ValidatingConfirmDialog> instead
 * (an AlertDialog-style confirmation with only an actor input).
 *
 * On 200 success: persist `actor` to localStorage['ohmystock.admin.actor'],
 * close the dialog, invalidate the ['proposal', slug] react-query cache.
 * On non-200: show envelope `{code}: {message}` inline below the form,
 * keep dialog open, re-enable submit.
 *
 * Spec: openspec/changes/admin-proposals-endpoints-and-pages/specs/web-admin-proposals-pages/spec.md
 */
import * as React from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ApiError,
  transitionProposal,
  type ProposalTransitionBody,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const ACTOR_STORAGE_KEY = 'ohmystock.admin.actor'

type DialogTarget = 'approved' | 'merged' | 'rejected'

const TARGET_COPY: Record<
  DialogTarget,
  { title: string; description: string; submitLabel: string }
> = {
  approved: {
    title: 'Approve proposal',
    description: 'WFA 驗證通過後設為 approved；檔案會搬到 PENDING_REVIEW/。',
    submitLabel: 'Approve',
  },
  merged: {
    title: 'Mark as merged',
    description:
      'cheatsheet 改動已合併進指定版本後設為 merged；檔案搬到 merged/。',
    submitLabel: 'Mark merged',
  },
  rejected: {
    title: 'Reject proposal',
    description:
      '不採用此提案；檔案搬到 rejected/，frontmatter 加上 rejected_reason。',
    submitLabel: 'Reject',
  },
}

export interface TransitionDialogProps {
  slug: string
  target: DialogTarget
  open: boolean
  onOpenChange: (next: boolean) => void
}

function readDefaultActor(): string {
  try {
    return localStorage.getItem(ACTOR_STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function TransitionDialog({
  slug,
  target,
  open,
  onOpenChange,
}: TransitionDialogProps) {
  const copy = TARGET_COPY[target]
  const queryClient = useQueryClient()

  const [actor, setActor] = React.useState(readDefaultActor)
  const [validationReportPath, setValidationReportPath] = React.useState('')
  const [mergedToVersion, setMergedToVersion] = React.useState('')
  const [reason, setReason] = React.useState('')
  const [submitError, setSubmitError] = React.useState<ApiError | null>(null)

  React.useEffect(() => {
    if (!open) return
    setActor(readDefaultActor())
    // Manual-verdict flow: the report sits at the proposals root as
    // <slug>.validation.json, so prefill (still editable).
    setValidationReportPath(
      target === 'approved' ? `${slug}.validation.json` : '',
    )
    setMergedToVersion('')
    setReason('')
    setSubmitError(null)
  }, [open, target, slug])

  const trimmedActor = actor.trim()
  const trimmedValidationPath = validationReportPath.trim()
  const trimmedVersion = mergedToVersion.trim()
  const trimmedReason = reason.trim()

  const isFormValid =
    trimmedActor.length > 0 &&
    (target === 'approved' ? trimmedValidationPath.length > 0 : true) &&
    (target === 'merged' ? trimmedVersion.length > 0 : true) &&
    (target === 'rejected' ? trimmedReason.length > 0 : true)

  const mutation = useMutation({
    mutationFn: () => {
      const body: ProposalTransitionBody = {
        new_status: target,
        actor: trimmedActor,
      }
      if (target === 'approved') {
        body.validation_report_path = trimmedValidationPath
      }
      if (target === 'merged') {
        body.merged_to_version = trimmedVersion
      }
      if (target === 'rejected') {
        body.reason = trimmedReason
      }
      return transitionProposal(slug, body)
    },
    onSuccess: () => {
      try {
        localStorage.setItem(ACTOR_STORAGE_KEY, trimmedActor)
      } catch {
        /* localStorage unavailable — non-fatal */
      }
      onOpenChange(false)
      queryClient.invalidateQueries({ queryKey: ['proposal', slug] })
      queryClient.invalidateQueries({ queryKey: ['proposals'] })
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setSubmitError(err)
      } else {
        setSubmitError(
          new ApiError('unknown_error', String(err ?? 'unknown error'), 0),
        )
      }
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!isFormValid || mutation.isPending) return
    setSubmitError(null)
    mutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{copy.title}</DialogTitle>
          <DialogDescription>{copy.description}</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-3">
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">Actor</span>
            <input
              type="text"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              placeholder="你的名字（會寫進 changelog）"
              required
              disabled={mutation.isPending}
              className="block w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          {target === 'approved' && (
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">
                Validation report path
              </span>
              <input
                type="text"
                value={validationReportPath}
                onChange={(e) => setValidationReportPath(e.target.value)}
                placeholder="reports/<slug>.validation.json"
                required
                disabled={mutation.isPending}
                className="block w-full rounded-md border border-input bg-background px-3 py-1.5 font-mono text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
              />
            </label>
          )}

          {target === 'merged' && (
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">Merged to version</span>
              <input
                type="text"
                value={mergedToVersion}
                onChange={(e) => setMergedToVersion(e.target.value)}
                placeholder="v3.1"
                required
                disabled={mutation.isPending}
                className="block w-full rounded-md border border-input bg-background px-3 py-1.5 font-mono text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
              />
            </label>
          )}

          {target === 'rejected' && (
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">Reason</span>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="說明拒絕原因（會寫進 changelog 與 frontmatter.rejected_reason）"
                rows={3}
                required
                disabled={mutation.isPending}
                className="block w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
              />
            </label>
          )}

          {submitError && (
            <p
              className="text-sm text-destructive"
              data-testid="transition-error"
            >
              {submitError.code}: {submitError.message}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!isFormValid || mutation.isPending}
            >
              {mutation.isPending ? '送出中…' : copy.submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export interface ValidatingConfirmDialogProps {
  slug: string
  open: boolean
  onOpenChange: (next: boolean) => void
}

/**
 * Confirmation dialog for `pending → validating`. Functionally a
 * single-field form: actor only.
 */
export function ValidatingConfirmDialog({
  slug,
  open,
  onOpenChange,
}: ValidatingConfirmDialogProps) {
  const queryClient = useQueryClient()
  const [actor, setActor] = React.useState(readDefaultActor)
  const [submitError, setSubmitError] = React.useState<ApiError | null>(null)

  React.useEffect(() => {
    if (!open) return
    setActor(readDefaultActor())
    setSubmitError(null)
  }, [open])

  const trimmedActor = actor.trim()

  const mutation = useMutation({
    mutationFn: () =>
      transitionProposal(slug, {
        new_status: 'validating',
        actor: trimmedActor,
      }),
    onSuccess: () => {
      try {
        localStorage.setItem(ACTOR_STORAGE_KEY, trimmedActor)
      } catch {
        /* non-fatal */
      }
      onOpenChange(false)
      queryClient.invalidateQueries({ queryKey: ['proposal', slug] })
      queryClient.invalidateQueries({ queryKey: ['proposals'] })
    },
    onError: (err) => {
      if (err instanceof ApiError) setSubmitError(err)
      else setSubmitError(new ApiError('unknown_error', String(err), 0))
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (trimmedActor.length === 0 || mutation.isPending) return
    setSubmitError(null)
    mutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Mark as validating</DialogTitle>
          <DialogDescription>
            標記 proposal 為 validating（仍留在原位）。確認後會在 changelog 加一行記錄。
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-3">
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">Actor</span>
            <input
              type="text"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              required
              placeholder="你的名字"
              disabled={mutation.isPending}
              className="block w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          {submitError && (
            <p
              className="text-sm text-destructive"
              data-testid="transition-error"
            >
              {submitError.code}: {submitError.message}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={trimmedActor.length === 0 || mutation.isPending}
            >
              {mutation.isPending ? '送出中…' : 'Confirm'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
