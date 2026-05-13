/**
 * /proposals/:slug — read-only detail + status-aware action row.
 *
 * Renders header (back-link + h1 + status/priority badges + meta) → optional
 * extra_frontmatter Card (omitted when empty) → 7 body Cards (each <pre>) →
 * 變更紀錄 Card → action row driven by data.status.
 *
 * 404 (`code: "not_found"`)         → "找不到提案" empty state + back-link
 * 422 (`code: "malformed_proposal"`) → destructive Card + back-link, NO retry
 * other errors                       → destructive Card + AlertCircle + retry
 *
 * Spec: openspec/changes/admin-proposals-endpoints-and-pages/specs/web-admin-proposals-pages/spec.md
 */
import * as React from 'react'
import { Link, useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, ArrowLeft, FileX } from 'lucide-react'
import {
  ApiError,
  getProposal,
  listStrategies,
  type ProposalChangelogEntry,
  type ProposalDetail,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  TransitionDialog,
  ValidatingConfirmDialog,
} from '@/components/transition-dialog'
import { ValidationDialog } from '@/components/validation-dialog'

const BODY_SECTIONS: {
  key: keyof ProposalDetail['body']
  title: string
}[] = [
  { key: 'description', title: '## 1. 改動描述' },
  { key: 'motivation', title: '## 2. 動機與佐證' },
  { key: 'diff_draft', title: '## 3. 改動 diff 草稿' },
  { key: 'expected_impact', title: '## 4. 預期影響範圍' },
  { key: 'risk_assessment', title: '## 5. 風險評估' },
  { key: 'validation_plan', title: '## 6. 驗證計畫' },
  { key: 'expected_improvement', title: '## 7. 預期改善幅度' },
]

const EXTRA_FRONTMATTER_LABELS: Record<
  'validation_report_path' | 'merged_to_version' | 'merged_at' | 'rejected_reason',
  string
> = {
  validation_report_path: 'validation_report_path',
  merged_to_version: 'merged_to_version',
  merged_at: 'merged_at',
  rejected_reason: 'rejected_reason',
}

function LoadingState() {
  return (
    <div className="space-y-4" data-testid="proposal-detail-loading">
      <div className="space-y-3">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-7 w-72" />
        <Skeleton className="h-4 w-96" />
      </div>
      {Array.from({ length: 7 }).map((_, i) => (
        <Card key={i} className="p-4">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="mt-3 h-24 w-full" />
        </Card>
      ))}
    </div>
  )
}

function NotFound({ slug }: { slug: string }) {
  return (
    <Card className="flex flex-col items-center justify-center gap-3 p-12 text-center">
      <FileX className="size-8 text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground">
        找不到提案: <span className="font-mono">{slug}</span>
      </p>
      <Button variant="outline" size="sm" asChild>
        <Link to="/proposals">返回 Proposals</Link>
      </Button>
    </Card>
  )
}

function MalformedPanel({ message }: { message: string }) {
  return (
    <div className="space-y-4">
      <Link
        to="/proposals"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:underline focus-visible:outline-none"
      >
        <ArrowLeft className="size-4" aria-hidden /> Proposals
      </Link>
      <Card
        role="alert"
        className="border-destructive/50 bg-destructive/5 p-6"
      >
        <div className="flex items-start gap-2 text-sm text-destructive">
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>提案檔案格式錯誤，請手動修復後再讀取 — {message}</span>
        </div>
      </Card>
    </div>
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
      className="border-destructive/50 bg-destructive/5 p-6"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="size-4" aria-hidden />
          <span>載入失敗 — {error.message}</span>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          重試
        </Button>
      </div>
    </Card>
  )
}

function ExtraMetadataCard({
  extra,
}: {
  extra: ProposalDetail['extra_frontmatter']
}) {
  const entries = Object.entries(extra) as [
    keyof typeof EXTRA_FRONTMATTER_LABELS,
    string,
  ][]
  if (entries.length === 0) return null
  return (
    <Card className="p-4">
      <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Extra metadata
      </h2>
      <dl className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-[max-content_1fr] sm:gap-x-4">
        {entries.map(([key, value]) => (
          <React.Fragment key={key}>
            <dt className="font-mono text-xs text-muted-foreground">
              {EXTRA_FRONTMATTER_LABELS[key]}
            </dt>
            <dd className="font-mono text-xs">{value}</dd>
          </React.Fragment>
        ))}
      </dl>
    </Card>
  )
}

function BodySectionCard({
  title,
  body,
}: {
  title: string
  body: string
}) {
  return (
    <Card className="overflow-hidden p-0">
      <div className="border-b bg-muted/40 px-4 py-2 text-xs font-medium text-muted-foreground">
        <h2>{title}</h2>
      </div>
      <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-sm leading-relaxed">
{body || '（空白）'}
      </pre>
    </Card>
  )
}

function ChangelogList({ entries }: { entries: ProposalChangelogEntry[] }) {
  if (entries.length === 0) {
    return (
      <p className="text-sm italic text-muted-foreground">（尚無變更紀錄）</p>
    )
  }
  return (
    <ul className="space-y-2">
      {entries.map((entry, idx) => {
        if (entry.kind === 'transition') {
          return (
            <li key={idx} className="text-sm">
              <span className="font-mono text-xs text-muted-foreground">
                {entry.timestamp}
              </span>{' '}
              — <span className="font-mono">{entry.from_status}</span> →{' '}
              <span className="font-mono">{entry.to_status}</span>{' '}
              <span className="text-muted-foreground">by</span>{' '}
              <span className="font-medium">{entry.actor}</span>
              {entry.reason && (
                <span className="ml-1 italic text-muted-foreground">
                  ({entry.reason})
                </span>
              )}
            </li>
          )
        }
        if (entry.kind === 'created') {
          return (
            <li key={idx} className="text-sm">
              <span className="font-mono text-xs text-muted-foreground">
                {entry.timestamp}
              </span>{' '}
              — <span className="text-muted-foreground">created by</span>{' '}
              <span className="font-medium">{entry.actor}</span>
            </li>
          )
        }
        return (
          <li key={idx}>
            <pre className="whitespace-pre-wrap break-words font-mono text-xs">
              {entry.text}
            </pre>
          </li>
        )
      })}
    </ul>
  )
}

type ActiveDialogKind = 'none' | 'validating' | 'approved' | 'merged' | 'rejected'

function ActionRow({
  slug,
  status,
}: {
  slug: string
  status: ProposalDetail['status']
}) {
  const [active, setActive] = React.useState<ActiveDialogKind>('none')
  const [validationOpen, setValidationOpen] = React.useState(false)

  const strategiesQuery = useQuery({
    queryKey: ['strategies'],
    queryFn: listStrategies,
    retry: false,
    // Strategies only matter when the [Run Validation…] button can fire.
    enabled: status === 'validating',
  })

  if (status === 'merged' || status === 'rejected') {
    return (
      <Card className="p-4">
        <p className="text-sm text-muted-foreground">終局狀態</p>
      </Card>
    )
  }

  const transitionTarget =
    active === 'approved' || active === 'merged' || active === 'rejected'
      ? active
      : null

  return (
    <>
      <Card className="flex flex-wrap items-center gap-2 p-4">
        {status === 'pending' && (
          <Button onClick={() => setActive('validating')}>
            Mark Validating
          </Button>
        )}
        {status === 'validating' && (
          <>
            <Button
              variant="default"
              onClick={() => setValidationOpen(true)}
              disabled={strategiesQuery.isLoading || strategiesQuery.isError}
              title={
                strategiesQuery.isLoading
                  ? '載入策略中…'
                  : strategiesQuery.isError
                    ? '策略清單載入失敗'
                    : undefined
              }
            >
              Run Validation…
            </Button>
            <Button onClick={() => setActive('approved')}>Approve…</Button>
            <Button variant="outline" onClick={() => setActive('rejected')}>
              Reject…
            </Button>
          </>
        )}
        {status === 'approved' && (
          <>
            <Button onClick={() => setActive('merged')}>Mark Merged…</Button>
            <Button variant="outline" onClick={() => setActive('rejected')}>
              Reject…
            </Button>
          </>
        )}
      </Card>

      <ValidatingConfirmDialog
        slug={slug}
        open={active === 'validating'}
        onOpenChange={(o) => setActive(o ? 'validating' : 'none')}
      />
      {transitionTarget && (
        <TransitionDialog
          slug={slug}
          target={transitionTarget}
          open
          onOpenChange={(o) => setActive(o ? transitionTarget : 'none')}
        />
      )}
      <ValidationDialog
        slug={slug}
        strategies={strategiesQuery.data?.strategies ?? []}
        open={validationOpen}
        onOpenChange={setValidationOpen}
      />
    </>
  )
}

export function ProposalDetailPage() {
  const { slug } = useParams<{ slug: string }>()
  const query = useQuery<ProposalDetail, ApiError>({
    queryKey: ['proposal', slug],
    queryFn: () => getProposal(slug as string),
    retry: false,
    enabled: Boolean(slug),
  })

  if (!slug) return <NotFound slug="" />

  if (query.isLoading) return <LoadingState />

  if (query.error?.code === 'not_found') return <NotFound slug={slug} />

  if (query.error?.code === 'malformed_proposal') {
    return <MalformedPanel message={query.error.message} />
  }

  if (query.error) {
    return (
      <div className="space-y-4">
        <Link
          to="/proposals"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:underline focus-visible:outline-none"
        >
          <ArrowLeft className="size-4" aria-hidden /> Proposals
        </Link>
        <ErrorPanel error={query.error} onRetry={() => query.refetch()} />
      </div>
    )
  }

  if (!query.data) return null
  const proposal = query.data

  return (
    <div className="space-y-4">
      <header className="space-y-3">
        <Link
          to="/proposals"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:underline focus-visible:outline-none"
        >
          <ArrowLeft className="size-4" aria-hidden /> Proposals
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold tracking-tight">
            {proposal.topic}
          </h1>
          <Badge variant="secondary">{proposal.status}</Badge>
          <Badge variant="outline">{proposal.priority}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">
            {proposal.created_by}
          </span>{' '}
          ·{' '}
          <span className="font-mono text-xs">{proposal.created_at}</span>
        </p>
        <p className="text-sm">
          <span className="text-muted-foreground">Target section:</span>{' '}
          <span className="font-mono text-xs">{proposal.target_section}</span>
        </p>
      </header>

      <ExtraMetadataCard extra={proposal.extra_frontmatter} />

      {BODY_SECTIONS.map(({ key, title }) => (
        <BodySectionCard key={key} title={title} body={proposal.body[key]} />
      ))}

      <Card className="p-4">
        <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          變更紀錄
        </h2>
        <div className="mt-2">
          <ChangelogList entries={proposal.changelog} />
        </div>
      </Card>

      <ActionRow slug={proposal.slug} status={proposal.status} />
    </div>
  )
}
