/**
 * shadcn/ui Skeleton — copied from upstream as of 2026-05-08.
 * Source: https://github.com/shadcn-ui/ui/blob/main/apps/www/registry/new-york-v4/ui/skeleton.tsx
 *
 * Third-party source. Do NOT customize here; wrap in `web-admin/src/components/`.
 */
import { cn } from '@/lib/utils'

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-muted', className)}
      {...props}
    />
  )
}

export { Skeleton }
