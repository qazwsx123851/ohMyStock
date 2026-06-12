/**
 * /swarm/:preset/:runId — vertical stepper view of a single run.
 *
 * v0 supports the phase5-review preset. Stepper rows are real <button>s,
 * carry textual state labels alongside Lucide state icons (icons are
 * aria-hidden), respect prefers-reduced-motion via motion-reduce:animate-none,
 * and the container uses aria-live="polite" so SSE-driven transitions get
 * announced.
 *
 * Spec: openspec/changes/admin-swarm-endpoints-and-pages/specs/web-admin-swarm-pages/spec.md
 */
import * as React from 'react'
import { Link, useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Loader2,
  XCircle,
} from 'lucide-react'
import {
  ApiError,
  getSwarmRun,
  type SwarmRunRow,
} from '@/lib/api'
import { useLiveFeedStore } from '@/stores'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

type NodeState = 'done' | 'running' | 'failed' | 'queued'

const PHASE5_NODES = [
  'data_loader',
  'attributor',
  'aggregator',
  'critic',
  'proposer',
] as const

function deriveBaselineStates(
  row: SwarmRunRow,
  nodes: readonly string[],
): Record<string, NodeState> {
  const out: Record<string, NodeState> = {}
  const result = row.result as {
    node_outputs?: Record<string, unknown>
    failed_node?: string
    completed_nodes?: string[]
  }
  const completedSet = new Set<string>([
    ...(result.completed_nodes ?? []),
    ...Object.keys(result.node_outputs ?? {}),
  ])
  for (const n of nodes) {
    if (n === result.failed_node) {
      out[n] = 'failed'
    } else if (completedSet.has(n)) {
      out[n] = 'done'
    } else {
      out[n] = 'queued'
    }
  }
  return out
}

function StateIcon({ state }: { state: NodeState }) {
  switch (state) {
    case 'done':
      return (
        <CheckCircle2
          className="size-5 text-up"
          aria-hidden="true"
        />
      )
    case 'running':
      return (
        <Loader2
          className="size-5 animate-spin text-foreground motion-reduce:animate-none"
          aria-hidden="true"
        />
      )
    case 'failed':
      return (
        <XCircle
          className="size-5 text-destructive"
          aria-hidden="true"
        />
      )
    default:
      return (
        <Circle
          className="size-5 text-muted-foreground"
          aria-hidden="true"
        />
      )
  }
}

function StateLabel({ state }: { state: NodeState }) {
  return <span className="text-xs uppercase tracking-wide">{state}</span>
}

function StepperRow({
  node,
  state,
  output,
  errorMessage,
  expanded,
  onToggle,
}: {
  node: string
  state: NodeState
  output: unknown
  errorMessage?: string | null
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={`swarm-node-${node}`}
        className={cn(
          'flex w-full cursor-pointer items-center gap-3 rounded-md border border-border bg-background px-4 py-3 text-left transition-colors',
          'hover:bg-accent/40',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        )}
      >
        <StateIcon state={state} />
        <div className="flex-1 space-y-0.5">
          <p className="font-mono text-sm font-medium">{node}</p>
          <StateLabel state={state} />
        </div>
        {expanded ? (
          <ChevronDown
            className="size-4 text-muted-foreground"
            aria-hidden="true"
          />
        ) : (
          <ChevronRight
            className="size-4 text-muted-foreground"
            aria-hidden="true"
          />
        )}
      </button>
      {expanded && (
        <div
          id={`swarm-node-${node}`}
          className="mt-2 space-y-2 rounded-md border border-dashed border-border bg-muted/30 p-3"
        >
          {state === 'failed' && errorMessage && (
            <p className="text-sm text-destructive">{errorMessage}</p>
          )}
          <pre className="max-h-[40vh] overflow-auto whitespace-pre-wrap text-xs">
            {output === undefined
              ? '（尚無輸出）'
              : JSON.stringify(output, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

function SwarmRunHeader({
  row,
  presetSlug,
}: {
  row: SwarmRunRow | null
  presetSlug: string
}) {
  const reviewId =
    row && typeof (row.result as Record<string, unknown>).review_id === 'string'
      ? ((row.result as Record<string, unknown>).review_id as string)
      : null
  return (
    <header className="space-y-2">
      <Link
        to="/swarm"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Swarm
      </Link>
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">
          {presetSlug}
        </h1>
        {row && (
          <Badge
            variant={row.status === 'completed' ? 'secondary' : 'destructive'}
          >
            {row.status}
          </Badge>
        )}
      </div>
      {row && (
        <p className="text-xs text-muted-foreground">
          run_id <code className="font-mono">{row.id}</code> ·
          created {row.created_at} · elapsed {row.elapsed_ms} ms
          {reviewId && (
            <>
              {' · '}
              <Link
                to={`/reviews/${reviewId}`}
                className="text-foreground underline-offset-2 hover:underline"
              >
                review {reviewId}
              </Link>
            </>
          )}
        </p>
      )}
    </header>
  )
}

function NotFoundView() {
  return (
    <Card className="flex flex-col items-center justify-center gap-3 p-12 text-center">
      <p className="text-sm text-muted-foreground">找不到 run</p>
      <Button asChild size="sm" variant="outline">
        <Link to="/swarm">回到 Swarm</Link>
      </Button>
    </Card>
  )
}

function ErrorView({
  error,
  onRetry,
}: {
  error: ApiError
  onRetry: () => void
}) {
  return (
    <Card
      role="alert"
      className="border-destructive/50 bg-destructive/5 p-6"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="size-4" aria-hidden="true" />
          <span>載入 run 失敗 — {error.message}</span>
        </div>
        <Button size="sm" variant="outline" onClick={onRetry}>
          重試
        </Button>
      </div>
    </Card>
  )
}

function LoadingView() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-4 w-64" />
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  )
}

export function SwarmRunPage() {
  const params = useParams()
  const presetSlug = params.preset ?? ''
  const runId = params.runId ?? ''

  const query = useQuery<SwarmRunRow, ApiError>({
    queryKey: ['swarm-run', runId],
    queryFn: () => getSwarmRun(runId),
    retry: false,
    enabled: runId.length > 0,
  })

  // Subscribe to live feed scoped to this run. Select the raw array and
  // filter in useMemo — filtering inside the selector returns a fresh array
  // per getSnapshot call, which React 18 treats as an ever-changing store
  // and loops re-renders forever (React error #185).
  const allEvents = useLiveFeedStore((s) => s.events)
  const liveEvents = React.useMemo(
    () =>
      allEvents.filter((e) => {
        if (!e.event_type.startsWith('swarm_')) return false
        const payload = (e.payload ?? {}) as Record<string, unknown>
        return payload.run_id === runId
      }),
    [allEvents, runId],
  )

  const baseline = React.useMemo<Record<string, NodeState>>(
    () =>
      query.data
        ? deriveBaselineStates(query.data, PHASE5_NODES)
        : Object.fromEntries(PHASE5_NODES.map((n) => [n, 'queued'])),
    [query.data],
  )

  const states = React.useMemo<Record<string, NodeState>>(() => {
    const out: Record<string, NodeState> = { ...baseline }
    // Replay events oldest-first so latest wins; live feed stores newest first.
    const ordered = [...liveEvents].reverse()
    for (const e of ordered) {
      const payload = (e.payload ?? {}) as Record<string, unknown>
      const node = payload.node as string | undefined
      if (e.event_type === 'swarm_run_failed') {
        const failed = payload.failed_node as string | undefined
        if (failed && failed in out) out[failed] = 'failed'
        continue
      }
      if (!node || !(node in out)) continue
      if (e.event_type === 'swarm_node_started') {
        if (out[node] === 'queued') out[node] = 'running'
      } else if (e.event_type === 'swarm_node_completed') {
        out[node] = 'done'
      }
    }
    return out
  }, [baseline, liveEvents])

  const [expanded, setExpanded] = React.useState<Record<string, boolean>>({})
  const toggle = (n: string) =>
    setExpanded((prev) => ({ ...prev, [n]: !prev[n] }))

  const result = (query.data?.result ?? {}) as {
    node_outputs?: Record<string, unknown>
    error?: { code?: string; message?: string }
    failed_node?: string
  }
  const errorMessage = result.error?.message ?? null

  if (query.isLoading) return <LoadingView />
  if (query.error) {
    if (query.error.code === 'not_found') return <NotFoundView />
    return <ErrorView error={query.error} onRetry={() => query.refetch()} />
  }

  return (
    <div className="space-y-4">
      <SwarmRunHeader row={query.data ?? null} presetSlug={presetSlug} />
      <div
        className="space-y-2"
        aria-live="polite"
        aria-label="Swarm pipeline stepper"
      >
        {PHASE5_NODES.map((node) => (
          <StepperRow
            key={node}
            node={node}
            state={states[node]}
            output={result.node_outputs?.[node]}
            errorMessage={
              states[node] === 'failed' ? errorMessage : null
            }
            expanded={Boolean(expanded[node])}
            onToggle={() => toggle(node)}
          />
        ))}
      </div>
    </div>
  )
}
