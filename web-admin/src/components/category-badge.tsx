/**
 * CategoryBadge — neutral shadcn `secondary` Badge paired with a Lucide icon.
 *
 * The skills pages MUST NOT use 紅漲綠跌 (`--up`/`--down`/`--destructive`)
 * for categories (no price semantics). Instead, the icon carries the
 * differentiation; the colour stays muted-neutral. This satisfies both the
 * "no semantic colours" constraint and the universal
 * "color-is-never-the-only-signal" rule from
 * `docs/web-admin-page-designs.md` §0.3.
 */
import {
  Brain,
  Database,
  FileText,
  LineChart,
  Shield,
  Wrench,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { SkillCategory } from '@/lib/api'

const ICON_MAP: Record<SkillCategory, LucideIcon> = {
  data: Database,
  indicator: LineChart,
  signal: Zap,
  decider: Brain,
  gate: Shield,
  tool: Wrench,
  report: FileText,
}

export function CategoryBadge({
  category,
  className,
}: {
  category: SkillCategory
  className?: string
}) {
  const Icon = ICON_MAP[category]
  return (
    <Badge
      variant="secondary"
      className={cn('gap-1.5 px-2 py-0.5 font-medium', className)}
      data-category={category}
    >
      <Icon className="size-3" aria-hidden />
      {category}
    </Badge>
  )
}
