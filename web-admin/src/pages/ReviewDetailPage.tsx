/**
 * /reviews/:reviewId — read-only detail view for a single review.
 *
 * Layout (top-down):
 *   header (back-link + review_id + kind badge + period)
 *   partial-banner (conditional, when payload.partial === true)
 *   3 KPI cards (conditional, when summary !== null)
 *   File checklist Card (dense definition list of 6 files)
 *   Report Card (conditional, when report !== null) — <pre>, no md parser
 *   Proposals Created Card (4-col mini-table → /proposals/<slug>)
 *
 * 404 → status Card + back-link. Other errors → destructive Card + retry.
 *
 * Spec: openspec/changes/admin-reviews-endpoints-and-pages/specs/web-admin-reviews-pages/spec.md
 */
import { Link, useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Circle,
  PackageSearch,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import {
  ApiError,
  getReview,
  type ReviewDetail,
  type ReviewFiles,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const FILE_ROW_ORDER: { key: keyof ReviewFiles; filename: string }[] = [
  { key: 'data_json', filename: 'data.json' },
  { key: 'attribution_json', filename: 'attribution.json' },
  { key: 'metrics_json', filename: 'metrics.json' },
  { key: 'critique_md', filename: 'critique.md' },
  { key: 'report_md', filename: 'report.md' },
  { key: 'proposals_created_md', filename: 'proposals_created.md' },
]

// ---------------------------------------------------------------------------
// KPI tile — local, because we render TrendingUp/Down at >=0.5 / >=1 thresholds
// that the generic kpi-card glyph='auto' (which keys off sign) cannot express.
// ---------------------------------------------------------------------------

function KpiTile({
  label,
  value,
  up,
}: {
  label: string
  value: string | number
  up: boolean | null
}) {
  const Icon = up === null ? null : up ? TrendingUp : TrendingDown
  return (
    <Card className="rounded-lg p-4">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          'mt-2 flex items-baseline gap-1.5 tabular text-2xl font-semibold',
          up === true && 'text-up',
          up === false && 'text-down',
        )}
      >
        {Icon && (
          <span className="inline-flex">
            <Icon className="size-5 self-center" aria-hidden />
          </span>
        )}
        <span>{value}</span>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// State components
// ---------------------------------------------------------------------------

function LoadingState() {
  return (
    <div className="space-y-4" data-testid="review-detail-loading">
      <Skeleton className="h-6 w-1/2" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
      <Skeleton className="h-48 w-full" />
    </div>
  )
}

function NotFoundState({ reviewId }: { reviewId: string }) {
  return (
    <Card
      role="status"
      className="flex flex-col items-center justify-center gap-3 p-12 text-center"
    >
      <PackageSearch className="size-8 text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground">
        Review not found: <span className="font-mono">{reviewId}</span>
      </p>
      <Link
        to="/reviews"
        className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        回到 Reviews 列表
      </Link>
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
    <Card role="alert" className="border-destructive/50 bg-destructive/5 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="size-4" aria-hidden />
          <span>
            {error.code}: {error.message}
          </span>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          重試
        </Button>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Page body — split so the wrapper above can swap loading / 404 / error
// states without re-running the data-dependent branches.
// ---------------------------------------------------------------------------

function DetailBody({ data }: { data: ReviewDetail }) {
  const { summary, files, report, metrics_overall, proposals_created, partial } =
    data

  return (
    <>
      {partial && (
        <Card className="flex items-center gap-2 border-warning bg-warning/5 p-3 text-sm">
          <AlertTriangle className="size-4 text-warning" aria-hidden />
          <span className="text-foreground">
            部分節點未完成 — 下方僅顯示已落檔的中間產物
          </span>
        </Card>
      )}

      {summary !== null && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <KpiTile
            label="期間交易筆數"
            value={summary.trade_count}
            up={null}
          />
          <KpiTile
            label="勝率"
            value={`${(summary.win_rate * 100).toFixed(1)}%`}
            up={summary.win_rate >= 0.5}
          />
          <KpiTile
            label="Profit Factor"
            value={summary.pf.toFixed(2)}
            up={summary.pf >= 1}
          />
        </div>
      )}

      <Card className="p-4">
        <h2 className="text-sm font-semibold text-foreground">本期復盤檔案</h2>
        <ul className="mt-3 space-y-1">
          {FILE_ROW_ORDER.map(({ key, filename }) => {
            const entry = files[key]
            const present = entry.exists
            return (
              <li
                key={key}
                className="flex items-center gap-3 rounded py-1.5"
              >
                {present ? (
                  <CheckCircle2
                    className="size-4 shrink-0 text-foreground"
                    aria-label="已產出"
                  />
                ) : (
                  <Circle
                    className="size-4 shrink-0 text-muted-foreground/50"
                    aria-label="缺漏"
                  />
                )}
                <span className="text-sm">{filename}</span>
                <span className="ml-auto truncate font-mono text-xs text-muted-foreground">
                  {present && entry.path ? (
                    entry.path
                  ) : (
                    <span className="text-muted-foreground/50">—</span>
                  )}
                </span>
              </li>
            )
          })}
        </ul>
      </Card>

      {report !== null && (
        <Card className="p-6">
          <h2 className="text-sm font-semibold text-foreground">Report</h2>
          <pre className="mt-3 max-h-[70vh] overflow-auto whitespace-pre-wrap rounded bg-muted/30 p-3 font-mono text-sm">
            {report}
          </pre>
        </Card>
      )}

      <Card className="p-4">
        <h2 className="text-sm font-semibold text-foreground">本次產出的提案</h2>
        {proposals_created.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">本期無提案</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">Slug</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 font-medium">Priority</th>
                  <th className="py-2 font-medium">Target</th>
                </tr>
              </thead>
              <tbody>
                {proposals_created.map((row) => (
                  <tr key={row.slug} className="border-b last:border-0">
                    <td className="py-2 pr-3 font-mono text-xs">
                      <Link
                        to={`/proposals/${row.slug}`}
                        className="text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {row.slug}
                      </Link>
                    </td>
                    <td className="py-2 pr-3">
                      <Badge variant="secondary">{row.status}</Badge>
                    </td>
                    <td className="py-2 pr-3">
                      <Badge variant="outline">{row.priority}</Badge>
                    </td>
                    <td className="py-2 text-muted-foreground">{row.target}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {metrics_overall !== null && summary === null && (
        <Card className="p-4 text-xs text-muted-foreground">
          <p>
            metrics.json 已落檔但 _index.json 尚無對應 row;此處僅列出 6 個關鍵
            metric 供參考(KPI cards 因 summary 缺漏未顯示)。
          </p>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 font-mono">
            <dt>win_rate</dt>
            <dd className="text-right">
              {(metrics_overall.win_rate * 100).toFixed(1)}%
            </dd>
            <dt>profit_factor</dt>
            <dd className="text-right">
              {metrics_overall.profit_factor.toFixed(2)}
            </dd>
            <dt>expectancy_pct</dt>
            <dd className="text-right">
              {(metrics_overall.expectancy_pct * 100).toFixed(2)}%
            </dd>
            <dt>max_drawdown_pct</dt>
            <dd className="text-right">
              {(metrics_overall.max_drawdown_pct * 100).toFixed(2)}%
            </dd>
            <dt>max_consecutive_loss</dt>
            <dd className="text-right">{metrics_overall.max_consecutive_loss}</dd>
            <dt>avg_hold_days</dt>
            <dd className="text-right">
              {metrics_overall.avg_hold_days.toFixed(1)}
            </dd>
          </dl>
        </Card>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function ReviewDetailPage() {
  const { reviewId = '' } = useParams<{ reviewId: string }>()

  const query = useQuery<ReviewDetail, ApiError>({
    queryKey: ['review', reviewId],
    queryFn: () => getReview(reviewId),
    enabled: reviewId.length > 0,
    retry: false,
  })

  const header = (
    <header className="space-y-1">
      <Link
        to="/reviews"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        ← Reviews
      </Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-xl font-semibold tracking-tight">
          {reviewId}
        </h1>
        {query.data?.summary && (
          <>
            <Badge variant="secondary">{query.data.summary.kind}</Badge>
            <span className="font-mono text-xs text-muted-foreground">
              {query.data.summary.period.from} →{' '}
              {query.data.summary.period.to}
            </span>
          </>
        )}
      </div>
    </header>
  )

  return (
    <div className="space-y-4">
      {header}

      {query.isLoading && <LoadingState />}

      {query.error?.code === 'not_found' && (
        <NotFoundState reviewId={reviewId} />
      )}

      {query.error && query.error.code !== 'not_found' && (
        <ErrorPanel error={query.error} onRetry={() => query.refetch()} />
      )}

      {query.data && <DetailBody data={query.data} />}
    </div>
  )
}
