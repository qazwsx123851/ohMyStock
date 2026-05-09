/**
 * /skills — read-only list of every registered skill.
 *
 * Layout per docs/web-admin-page-designs.md §12 v0 scope:
 *   header → filter bar (search + category select) → responsive grid of
 *   clickable Cards. Cards show name (font-mono) + 2-line description
 *   (line-clamp-2) + CategoryBadge pinned to the bottom.
 *
 * Filter is purely client-side over the single initial fetch — no debounce,
 * no server-side ?q=. Loading is 12 Skeleton placeholders in the same grid
 * shape so the layout doesn't jump when data resolves.
 *
 * Spec: openspec/changes/web-admin-skills-pages/specs/web-admin-skills-pages/spec.md
 */
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  ChevronRight,
  Inbox,
  PackageSearch,
  Search,
  X,
} from 'lucide-react'
import {
  ApiError,
  listSkills,
  type Skill,
  type SkillCategory,
} from '@/lib/api'
import { CategoryBadge } from '@/components/category-badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const CATEGORIES: readonly SkillCategory[] = [
  'data',
  'indicator',
  'signal',
  'decider',
  'gate',
  'tool',
  'report',
] as const

type CategoryFilter = '' | SkillCategory

function matches(skill: Skill, q: string, cat: CategoryFilter): boolean {
  if (cat && skill.category !== cat) return false
  if (q) {
    const needle = q.toLowerCase()
    if (
      !skill.name.toLowerCase().includes(needle) &&
      !skill.description.toLowerCase().includes(needle)
    ) {
      return false
    }
  }
  return true
}

function SkillCard({
  skill,
  onOpen,
}: {
  skill: Skill
  onOpen: (name: string) => void
}) {
  return (
    <Card
      role="button"
      tabIndex={0}
      aria-label={`${skill.name}：${skill.description}`}
      onClick={() => onOpen(skill.name)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen(skill.name)
        }
      }}
      className={cn(
        'group flex h-full cursor-pointer flex-col gap-3 p-5 transition-colors',
        'hover:bg-accent/40',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-mono text-sm font-semibold leading-tight tracking-tight text-foreground">
          {skill.name}
        </h3>
        <ChevronRight
          className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
          aria-hidden
        />
      </div>
      <p className="line-clamp-2 text-sm text-muted-foreground">
        {skill.description}
      </p>
      <div className="mt-auto pt-2">
        <CategoryBadge category={skill.category} />
      </div>
    </Card>
  )
}

function LoadingGrid() {
  return (
    <div
      className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
      data-testid="skills-loading"
    >
      {Array.from({ length: 12 }).map((_, i) => (
        <Card key={i} className="flex h-[148px] flex-col gap-3 p-5">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-5/6" />
          <Skeleton className="mt-auto h-5 w-20" />
        </Card>
      ))}
    </div>
  )
}

function EmptyAfterFilter({ onClear }: { onClear: () => void }) {
  return (
    <Card className="flex flex-col items-center justify-center gap-3 p-12 text-center">
      <PackageSearch className="size-8 text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground">無符合條件的 skill</p>
      <Button variant="outline" size="sm" onClick={onClear}>
        清除 filter
      </Button>
    </Card>
  )
}

function EmptyRegistry() {
  return (
    <Card className="flex flex-col items-center justify-center gap-2 p-12 text-center">
      <Inbox className="size-8 text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground">尚未註冊任何 skill</p>
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
          <span>載入 skills 失敗 — {error.message}</span>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          重試
        </Button>
      </div>
    </Card>
  )
}

export function SkillsPage() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [cat, setCat] = useState<CategoryFilter>('')

  const query = useQuery<{ items: Skill[] }, ApiError>({
    queryKey: ['skills'],
    queryFn: listSkills,
    retry: false,
  })

  const all = query.data?.items ?? []
  const filtered = useMemo(
    () => all.filter((s) => matches(s, q, cat)),
    [all, q, cat],
  )

  const filterActive = q !== '' || cat !== ''
  const clearFilters = () => {
    setQ('')
    setCat('')
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Skills</h1>
        <p className="text-sm text-muted-foreground">
          已註冊 skill 清單（read-only v0）。
          {query.data && (
            <>
              {' '}共 {filtered.length}/{all.length} 筆。
            </>
          )}
        </p>
      </header>

      <Card className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <input
              type="search"
              placeholder="搜尋 name / description…"
              className="block w-full rounded-md border border-input bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="搜尋 skills"
            />
          </div>
          <select
            className="rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:w-44"
            value={cat}
            onChange={(e) => setCat(e.target.value as CategoryFilter)}
            aria-label="類別過濾"
          >
            <option value="">全部類別</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          {filterActive && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearFilters}
              className="self-start sm:self-auto"
            >
              <X className="mr-1 size-4" aria-hidden /> 清除
            </Button>
          )}
        </div>
      </Card>

      {query.isLoading && <LoadingGrid />}

      {query.error && (
        <ErrorPanel error={query.error} onRetry={() => query.refetch()} />
      )}

      {query.data && all.length === 0 && <EmptyRegistry />}

      {query.data && all.length > 0 && filtered.length === 0 && (
        <EmptyAfterFilter onClear={clearFilters} />
      )}

      {query.data && filtered.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((s) => (
            <SkillCard
              key={s.name}
              skill={s}
              onOpen={(name) => navigate(`/skills/${name}`)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
