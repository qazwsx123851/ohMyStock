import * as React from 'react'
import {
  AlertCircle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ChevronsUpDown,
} from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export type SortDir = 'asc' | 'desc' | null
export type Align = 'left' | 'right' | 'center'
export type Density = 'comfortable' | 'compact'

export interface DataTableColumn<T> {
  id: string
  header: React.ReactNode
  accessor: (row: T) => React.ReactNode
  sortable?: boolean
  align?: Align
}

export interface DataTableProps<T> {
  rows: T[]
  columns: DataTableColumn<T>[]
  loading?: boolean
  error?: Error | null
  emptyMessage?: React.ReactNode
  onRowClick?: (row: T) => void
  /** Page size used by the consumer; required for the pager to render. */
  pageSize?: number
  /** Total row count across pages; pager hides when undefined. */
  total?: number
  /** 1-indexed current page. Defaults to 1. */
  page?: number
  onPageChange?: (page: number) => void
  /** Emits (column id, direction); both null when sort cleared. */
  onSortChange?: (column: string | null, direction: SortDir) => void
  density?: Density
  className?: string
  /** Skeleton rows while loading. Default 3. */
  skeletonRows?: number
  /** Stable React key per row; defaults to index. */
  rowKey?: (row: T, index: number) => React.Key
}

const ALIGN_CLASS: Record<Align, string> = {
  left: 'text-left',
  right: 'text-right tabular',
  center: 'text-center',
}

export function DataTable<T>({
  rows,
  columns,
  loading = false,
  error = null,
  emptyMessage = '無資料',
  onRowClick,
  pageSize,
  total,
  page,
  onPageChange,
  onSortChange,
  density = 'comfortable',
  className,
  skeletonRows = 3,
  rowKey,
}: DataTableProps<T>) {
  const [sort, setSort] = React.useState<{ id: string; dir: SortDir }>({
    id: '',
    dir: null,
  })

  const rowMinH =
    density === 'compact'
      ? 'var(--density-row-h-compact)'
      : 'var(--density-row-h)'
  const rowStyle: React.CSSProperties = { minHeight: rowMinH }

  const handleHeaderClick = (col: DataTableColumn<T>) => {
    if (!col.sortable) return
    let nextDir: SortDir
    if (sort.id !== col.id) nextDir = 'asc'
    else if (sort.dir === 'asc') nextDir = 'desc'
    else if (sort.dir === 'desc') nextDir = null
    else nextDir = 'asc'
    const nextId = nextDir === null ? '' : col.id
    setSort({ id: nextId, dir: nextDir })
    onSortChange?.(nextDir === null ? null : col.id, nextDir)
  }

  const handleRowKeyDown =
    (row: T) => (e: React.KeyboardEvent<HTMLTableRowElement>) => {
      if (e.key === 'Enter' && onRowClick) {
        e.preventDefault()
        onRowClick(row)
      }
    }

  if (error) {
    return (
      <Card className={cn('border-destructive/50 p-6', className)}>
        <div className="flex items-start gap-3">
          <AlertCircle
            className="size-5 shrink-0 text-destructive"
            aria-hidden
          />
          <div className="flex-1 text-sm">
            <p className="font-medium">載入失敗</p>
            <p className="mt-1 text-muted-foreground">{error.message}</p>
          </div>
        </div>
      </Card>
    )
  }

  if (!loading && rows.length === 0) {
    return (
      <Card
        className={cn(
          'p-8 text-center text-sm text-muted-foreground',
          className,
        )}
      >
        {emptyMessage}
      </Card>
    )
  }

  const totalPages =
    typeof total === 'number' && pageSize && pageSize > 0
      ? Math.max(1, Math.ceil(total / pageSize))
      : null
  const currentPage = page ?? 1
  const showPager =
    totalPages !== null && typeof onPageChange === 'function'

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((col) => {
              const sortActive =
                col.sortable && sort.id === col.id ? sort.dir : null
              const ariaSort: 'ascending' | 'descending' | 'none' =
                sortActive === 'asc'
                  ? 'ascending'
                  : sortActive === 'desc'
                    ? 'descending'
                    : 'none'
              return (
                <TableHead
                  key={col.id}
                  scope="col"
                  aria-sort={col.sortable ? ariaSort : undefined}
                  className={cn(ALIGN_CLASS[col.align ?? 'left'])}
                >
                  {col.sortable ? (
                    <button
                      type="button"
                      onClick={() => handleHeaderClick(col)}
                      className="inline-flex cursor-pointer items-center gap-1 rounded hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <span>{col.header}</span>
                      {sortActive === 'asc' && (
                        <ChevronUp className="size-3" aria-hidden />
                      )}
                      {sortActive === 'desc' && (
                        <ChevronDown className="size-3" aria-hidden />
                      )}
                      {sortActive === null && (
                        <ChevronsUpDown
                          className="size-3 opacity-40"
                          aria-hidden
                        />
                      )}
                    </button>
                  ) : (
                    col.header
                  )}
                </TableHead>
              )
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading
            ? Array.from({ length: skeletonRows }).map((_, i) => (
                <TableRow key={`skeleton-${i}`} style={rowStyle}>
                  {columns.map((col) => (
                    <TableCell
                      key={col.id}
                      className={ALIGN_CLASS[col.align ?? 'left']}
                    >
                      <Skeleton className="h-4 w-20" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            : rows.map((row, i) => (
                <TableRow
                  key={rowKey ? rowKey(row, i) : i}
                  tabIndex={onRowClick ? 0 : undefined}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onKeyDown={onRowClick ? handleRowKeyDown(row) : undefined}
                  style={rowStyle}
                  className={cn(
                    onRowClick &&
                      'cursor-pointer focus-visible:bg-muted/60 focus-visible:outline-none',
                  )}
                >
                  {columns.map((col) => (
                    <TableCell
                      key={col.id}
                      className={ALIGN_CLASS[col.align ?? 'left']}
                    >
                      {col.accessor(row)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
        </TableBody>
      </Table>
      {showPager && (
        <div className="flex items-center justify-end gap-2 px-1 text-xs text-muted-foreground">
          <span>
            第 {currentPage} / {totalPages} 頁
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={currentPage <= 1}
            onClick={() => onPageChange!(currentPage - 1)}
          >
            <ChevronLeft className="size-3" aria-hidden />
            上一頁
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={currentPage >= (totalPages ?? 1)}
            onClick={() => onPageChange!(currentPage + 1)}
          >
            下一頁
            <ChevronRight className="size-3" aria-hidden />
          </Button>
        </div>
      )}
    </div>
  )
}
