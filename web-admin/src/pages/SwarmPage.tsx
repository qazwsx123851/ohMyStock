/**
 * /swarm — preset cards launching swarm-style pipeline runs.
 *
 * v0 ships exactly one preset (phase5-review). Clicking [Run...] opens
 * <RunSwarmDialog>; on success the user is navigated to
 * /swarm/<preset>/<run_id>.
 *
 * Spec: openspec/changes/admin-swarm-endpoints-and-pages/specs/web-admin-swarm-pages/spec.md
 */
import * as React from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, Inbox, Workflow } from 'lucide-react'
import {
  ApiError,
  listSwarmPresets,
  type SwarmPreset,
} from '@/lib/api'
import { RunSwarmDialog } from '@/components/run-swarm-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

function PresetCard({
  preset,
  onRun,
}: {
  preset: SwarmPreset
  onRun: (preset: SwarmPreset) => void
}) {
  return (
    <Card className="flex h-[180px] flex-col gap-3 p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-base font-semibold leading-tight tracking-tight">
            {preset.title}
          </h3>
          <p className="font-mono text-xs text-muted-foreground">
            {preset.name}
          </p>
        </div>
        <Workflow
          className="size-5 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
      </div>
      <p className="line-clamp-2 text-sm text-muted-foreground">
        {preset.description}
      </p>
      <div className="flex flex-wrap gap-1">
        {preset.nodes.map((n) => (
          <Badge key={n} variant="outline" className="text-[10px]">
            {n}
          </Badge>
        ))}
      </div>
      <div className="mt-auto flex justify-end pt-1">
        <Button size="sm" onClick={() => onRun(preset)}>
          Run…
        </Button>
      </div>
    </Card>
  )
}

function LoadingGrid() {
  return (
    <div
      className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
      data-testid="swarm-loading"
    >
      {Array.from({ length: 3 }).map((_, i) => (
        <Card key={i} className="flex h-[180px] flex-col gap-3 p-5">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-5/6" />
          <Skeleton className="mt-auto h-8 w-20 self-end" />
        </Card>
      ))}
    </div>
  )
}

function EmptyPresets() {
  return (
    <Card className="flex flex-col items-center justify-center gap-2 p-12 text-center">
      <Inbox className="size-8 text-muted-foreground" aria-hidden="true" />
      <p className="text-sm text-muted-foreground">尚無 preset</p>
    </Card>
  )
}

function ErrorPanel({
  error,
  onRetry,
}: {
  error: ApiError
  onRetry: () => void
}) {
  return (
    <Card
      role="alert"
      className={cn('border-destructive/50 bg-destructive/5 p-6')}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="size-4" aria-hidden="true" />
          <span>載入 preset 失敗 — {error.message}</span>
        </div>
        <Button size="sm" variant="outline" onClick={onRetry}>
          重試
        </Button>
      </div>
    </Card>
  )
}

export function SwarmPage() {
  const [open, setOpen] = React.useState(false)
  const [active, setActive] = React.useState<SwarmPreset | null>(null)

  const query = useQuery<{ items: SwarmPreset[] }, ApiError>({
    queryKey: ['swarm-presets'],
    queryFn: listSwarmPresets,
    retry: false,
  })

  const presets = query.data?.items ?? []

  const handleRun = (preset: SwarmPreset) => {
    setActive(preset)
    setOpen(true)
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Swarm</h1>
        <p className="text-sm text-muted-foreground">
          選股、復盤、報表、策略提案…
        </p>
      </header>

      {query.isLoading && <LoadingGrid />}

      {query.error && (
        <ErrorPanel error={query.error} onRetry={() => query.refetch()} />
      )}

      {query.data && presets.length === 0 && <EmptyPresets />}

      {query.data && presets.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {presets.map((p) => (
            <PresetCard key={p.name} preset={p} onRun={handleRun} />
          ))}
        </div>
      )}

      <RunSwarmDialog
        preset={active}
        open={open}
        onOpenChange={setOpen}
      />
    </div>
  )
}
