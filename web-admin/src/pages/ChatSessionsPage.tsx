/**
 * /chat — session list view.
 *
 * Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/web-admin-chat-pages/spec.md
 *
 * Visual contract: docs/web-admin-page-designs.md §1.
 *
 * - 5-col DataTable: 標題 / 訊息數 / 最後活動 (relative time) / 模型 / 狀態
 * - Cmd/Ctrl+N hotkey → POST /sessions → navigate(/chat/<id>)
 * - Loading: 3 Skeleton rows (via DataTable built-in)
 * - Empty: 「尚無對話 — 點右上『+ 新對話』開始」 + <MessagesSquare/> muted
 * - Error: destructive Card + retry button
 * - Row click → /chat/<row.id>
 */

import * as React from 'react'
import { useNavigate } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, MessagesSquare, Plus } from 'lucide-react'

import {
  ApiError,
  createChatSession,
  listChatSessions,
  type ChatSessionSummary,
  type PaginatedRows,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  DataTable,
  type DataTableColumn,
} from '@/components/data-table'


const PAGE_SIZE = 20


function relativeTime(iso: string): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  const diff = (Date.now() - then) / 1000
  if (diff < 60) return '剛剛'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分鐘前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小時前`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`
  return iso.slice(0, 10)
}


export function ChatSessionsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [page, setPage] = React.useState(1)
  const offset = (page - 1) * PAGE_SIZE

  const query = useQuery<PaginatedRows<ChatSessionSummary>, ApiError>({
    queryKey: ['chat-sessions', PAGE_SIZE, offset],
    queryFn: () => listChatSessions({ limit: PAGE_SIZE, offset }),
  })

  const create = useMutation({
    mutationFn: () => createChatSession({}),
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
      navigate(`/chat/${session.id}`)
    },
  })

  // Cmd/Ctrl+N → 新對話
  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'n' || e.key === 'N')) {
        e.preventDefault()
        if (!create.isPending) create.mutate()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [create])

  const columns: DataTableColumn<ChatSessionSummary>[] = [
    {
      id: 'title',
      header: '標題',
      accessor: (row) => (
        <span className="font-medium">{row.title || '新對話'}</span>
      ),
    },
    {
      id: 'message_count',
      header: '訊息數',
      align: 'right',
      accessor: (row) => row.message_count,
    },
    {
      id: 'updated_at',
      header: '最後活動',
      accessor: (row) => relativeTime(row.updated_at),
    },
    {
      id: 'model',
      header: '模型',
      accessor: (row) => (
        <Badge variant="outline" className="font-mono text-xs">
          {row.model}
        </Badge>
      ),
    },
    {
      id: 'status',
      header: '狀態',
      accessor: () => (
        <span className="inline-flex items-center gap-1 text-up">
          <span
            aria-hidden="true"
            className="inline-block size-2 rounded-full bg-up"
          />
          進行中
        </span>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">對話模式</h1>
        <Button
          onClick={() => create.mutate()}
          disabled={create.isPending}
          aria-label="新增對話 (Cmd/Ctrl+N)"
        >
          <Plus className="size-4" aria-hidden="true" />
          {create.isPending ? '建立中…' : '新對話 (⌘N)'}
        </Button>
      </div>

      {create.isError && (
        <Card
          className="border-destructive p-4 text-sm"
          role="alert"
          aria-live="polite"
        >
          <div className="flex items-start gap-2">
            <AlertCircle
              className="size-4 mt-0.5 text-destructive"
              aria-hidden="true"
            />
            <span>
              建立 session 失敗：
              {(create.error as ApiError | undefined)?.code ?? 'unknown'}
            </span>
          </div>
        </Card>
      )}

      <DataTable<ChatSessionSummary>
        rows={query.data?.items ?? []}
        columns={columns}
        loading={query.isLoading}
        error={query.error}
        emptyMessage={
          <div className="flex flex-col items-center gap-2 py-8 text-muted-foreground">
            <MessagesSquare className="size-8" aria-hidden="true" />
            <span>尚無對話 — 點右上「+ 新對話」開始</span>
          </div>
        }
        onRowClick={(row) => navigate(`/chat/${row.id}`)}
        pageSize={PAGE_SIZE}
        total={query.data?.total}
        page={page}
        onPageChange={setPage}
        rowKey={(row) => row.id}
        skeletonRows={3}
      />
    </div>
  )
}
