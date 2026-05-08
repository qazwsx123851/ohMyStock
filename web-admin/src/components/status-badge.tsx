import * as React from 'react'
import {
  AlertCircle,
  Ban,
  Check,
  CheckCircle,
  Clock,
  Hourglass,
  X,
  type LucideIcon,
} from 'lucide-react'
import { Badge, type BadgeProps } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export type Status =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'executed'
  | 'expired'
  | 'canceled'
  | 'errored'

type StatusConfig = {
  icon: LucideIcon
  label: string
  variant: BadgeProps['variant']
  className?: string
}

const STATUS_CONFIG: Record<Status, StatusConfig> = {
  pending: { icon: Clock, label: '待處理', variant: 'secondary' },
  approved: {
    icon: Check,
    label: '已核准',
    variant: 'outline',
    className: 'border-[color:var(--up)]/40 text-[color:var(--up)]',
  },
  rejected: { icon: X, label: '已拒絕', variant: 'destructive' },
  executed: {
    icon: CheckCircle,
    label: '已執行',
    variant: 'default',
    className:
      'border-transparent bg-[color:var(--up)] text-white hover:bg-[color:var(--up)]/90',
  },
  expired: {
    icon: Hourglass,
    label: '已過期',
    variant: 'outline',
    className: 'text-muted-foreground',
  },
  canceled: {
    icon: Ban,
    label: '已取消',
    variant: 'outline',
    className: 'text-muted-foreground',
  },
  errored: { icon: AlertCircle, label: '錯誤', variant: 'destructive' },
}

export interface StatusBadgeProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, 'children'> {
  status: Status
  /** Override the default zh-TW label */
  label?: string
}

export function StatusBadge({
  status,
  label,
  className,
  ...props
}: StatusBadgeProps) {
  const config = STATUS_CONFIG[status]
  const Icon = config.icon
  return (
    <Badge
      variant={config.variant}
      className={cn('gap-1', config.className, className)}
      data-status={status}
      {...props}
    >
      <Icon className="size-3 shrink-0" aria-hidden />
      <span>{label ?? config.label}</span>
    </Badge>
  )
}
