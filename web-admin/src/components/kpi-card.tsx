import * as React from 'react'
import { ArrowDown, ArrowUp } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export type KpiDirection = 'up' | 'down' | 'neutral'

export interface KpiCardProps {
  label: string
  value?: React.ReactNode
  /** 'up' = 紅漲, 'down' = 綠跌, 'neutral'/undefined = no directional color or glyph. */
  direction?: KpiDirection
  /**
   * - 'auto' (default): pick `<ArrowUp/>` when direction='up', `<ArrowDown/>`
   *   when direction='down', nothing when direction='neutral'.
   * - `null`: no glyph at all.
   * - `ReactNode`: render as-is (e.g. a custom Lucide icon).
   */
  glyph?: 'auto' | React.ReactNode | null
  /** Trailing unit token (e.g. "TWD", "USD") rendered in muted text. */
  unit?: string
  /** When true, renders a `<Skeleton/>` in place of the value row. */
  loading?: boolean
  className?: string
}

/**
 * Single KPI tile. Pairs `--up`/`--down` color with a Lucide arrow so colour
 * is never the only signal. See `docs/web-admin-page-designs.md` §0.3.
 */
export function KpiCard({
  label,
  value,
  direction = 'neutral',
  glyph = 'auto',
  unit,
  loading = false,
  className,
}: KpiCardProps) {
  let renderedGlyph: React.ReactNode = null
  if (glyph === 'auto') {
    if (direction === 'up') {
      renderedGlyph = <ArrowUp className="size-4 self-center" aria-hidden />
    } else if (direction === 'down') {
      renderedGlyph = <ArrowDown className="size-4 self-center" aria-hidden />
    }
  } else if (glyph !== null) {
    renderedGlyph = glyph
  }

  return (
    <Card className={cn('rounded-lg p-4', className)}>
      <div className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      {loading ? (
        <Skeleton
          className="mt-2 h-8 w-32"
          aria-busy="true"
          aria-label="載入中"
        />
      ) : (
        <div
          className={cn(
            'mt-2 flex items-baseline gap-1.5 tabular text-2xl font-semibold',
            direction === 'up' && 'text-up',
            direction === 'down' && 'text-down',
          )}
          data-direction={direction}
        >
          {renderedGlyph !== null && (
            <span className="inline-flex">{renderedGlyph}</span>
          )}
          <span>{value}</span>
          {unit && (
            <span className="text-sm font-normal text-muted-foreground">
              {unit}
            </span>
          )}
        </div>
      )}
    </Card>
  )
}

/** Helper: derive direction from a signed number; null/undefined/0 → neutral. */
export function directionOf(n: number | null | undefined): KpiDirection {
  if (n == null || n === 0) return 'neutral'
  return n > 0 ? 'up' : 'down'
}
