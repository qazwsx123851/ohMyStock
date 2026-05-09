/**
 * /skills/:name — read-only skill detail.
 *
 * Renders header (back-link + h1 + CategoryBadge + description) → cited
 * specs row (chips, no links) → body Card with `<pre>` (no markdown
 * parser per design D7).
 *
 * 404 from the endpoint surfaces as a "找不到 skill: <name>" empty state
 * with a "返回 Skills" button. Other errors use the same destructive
 * banner + retry as SkillsPage.
 *
 * Spec: openspec/changes/web-admin-skills-pages/specs/web-admin-skills-pages/spec.md
 */
import { Link, useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, ArrowLeft, FileText, FileX } from 'lucide-react'
import { ApiError, getSkill, type SkillDetail } from '@/lib/api'
import { CategoryBadge } from '@/components/category-badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

function LoadingState() {
  return (
    <div className="space-y-4" data-testid="skill-detail-loading">
      <div className="space-y-3">
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-4 w-full max-w-prose" />
      </div>
      <Card className="p-4">
        <Skeleton className="h-4 w-32" />
      </Card>
      <Card className="p-4">
        <Skeleton className="h-48 w-full" />
      </Card>
    </div>
  )
}

function NotFound({ name }: { name: string }) {
  return (
    <Card className="flex flex-col items-center justify-center gap-3 p-12 text-center">
      <FileX className="size-8 text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground">
        找不到 skill: <span className="font-mono">{name}</span>
      </p>
      <Button variant="outline" size="sm" asChild>
        <Link to="/skills">返回 Skills</Link>
      </Button>
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

function CitedSpecsRow({ specs }: { specs: string[] }) {
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">
          Cited specs
        </span>
        {specs.length === 0 ? (
          <span className="text-xs italic text-muted-foreground">
            （無 cited_specs）
          </span>
        ) : (
          specs.map((s) => (
            <code
              key={s}
              className="rounded-md border border-border bg-muted px-2 py-0.5 font-mono text-xs"
            >
              {s}
            </code>
          ))
        )}
      </div>
    </Card>
  )
}

function BodyCard({ body }: { body: string }) {
  return (
    <Card className="overflow-hidden p-0">
      <div className="flex items-center gap-2 border-b bg-muted/40 px-4 py-2 text-xs text-muted-foreground">
        <FileText className="size-3.5" aria-hidden />
        <span>Body</span>
        <span className="ml-auto font-mono">{`${body.length} chars`}</span>
      </div>
      <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-sm leading-relaxed text-foreground">
{body}
      </pre>
    </Card>
  )
}

export function SkillDetailPage() {
  const { name } = useParams<{ name: string }>()
  const query = useQuery<SkillDetail, ApiError>({
    queryKey: ['skill', name],
    queryFn: () => getSkill(name as string),
    retry: false,
    enabled: Boolean(name),
  })

  if (!name) {
    return <NotFound name="" />
  }

  if (query.isLoading) {
    return <LoadingState />
  }

  if (query.error?.code === 'not_found') {
    return <NotFound name={name} />
  }

  if (query.error) {
    return (
      <div className="space-y-4">
        <Link
          to="/skills"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:underline focus-visible:outline-none"
        >
          <ArrowLeft className="size-4" aria-hidden /> Skills
        </Link>
        <ErrorPanel error={query.error} onRetry={() => query.refetch()} />
      </div>
    )
  }

  if (!query.data) return null
  const skill = query.data

  return (
    <div className="space-y-4">
      <header className="space-y-3">
        <Link
          to="/skills"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:underline focus-visible:outline-none"
        >
          <ArrowLeft className="size-4" aria-hidden /> Skills
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-xl font-semibold tracking-tight">
            {skill.name}
          </h1>
          <CategoryBadge category={skill.category} />
        </div>
        <p className="max-w-prose text-sm text-muted-foreground">
          {skill.description}
        </p>
      </header>

      <CitedSpecsRow specs={skill.cited_specs} />

      <BodyCard body={skill.body} />
    </div>
  )
}
