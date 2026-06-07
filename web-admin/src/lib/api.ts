/**
 * web-admin API client.
 *
 * - apiFetch: REST call with Bearer header injection + envelope parsing.
 * - openSSE:  fetch-based SSE stream (allows custom Authorization header,
 *             which native EventSource does not).
 *
 * Both honour the { ok, data, error } envelope from
 * openspec/specs/server-action-endpoints/spec.md and trigger logout()
 * on HTTP 401.
 */

import { useAuthStore, logout } from '@/stores'

// ---------------------------------------------------------------------------
// Domain types - what backend endpoints return, hand-written until codegen
// ---------------------------------------------------------------------------

export type StatsToday = {
  realized_pnl_twd: number
  open_positions: number
  pending_confirms: number
  llm_cost_usd: number
}

// Dashboard summary additions from GET /api/admin/stats/today
// (web-admin-scenario-gaps: DB-B1/B2/B3). risk_gate is optional until the
// market risk gate backend ships.
export type RiskGateStatus = 'green' | 'yellow' | 'red'

export type RiskGate = {
  status: RiskGateStatus
  triggers: string[]
}

export type MonthlyBreaker = {
  tripped: boolean
  month_pnl_pct: number
}

export type CostSummary = {
  used_usd: number
  budget_usd: number
  pct: number
}

export type StatsSummary = {
  asof_date: string
  decisions_made: number
  entries_pending: number
  entries_filled: number
  rejects: number
  expires: number
  auto_execute_audits: number
  monthly_breaker: MonthlyBreaker
  cost: CostSummary
  risk_gate?: RiskGate
}

// Open position row from GET /api/admin/positions/open
export type OpenPosition = {
  symbol: string
  side: 'long' | 'short'
  qty: number
  entry_price: number
  mark_price: number
  unrealized_pnl_twd: number
  unrealized_pnl_pct: number
  stop_loss: number
  t1_target: number
  hold_days: number
  time_stop_date: string
  entry_reason: string
  entry_at: string
}

// Envelope returned by GET /api/admin/positions/open ({ items, asof_iso, count }).
export type PositionsOpenResponse = {
  items: OpenPosition[]
  asof_iso: string
  count: number
}

// Single row in GET /api/admin/journal/rows
export type JournalRow = {
  id: number | string
  kind: string
  symbol?: string | null
  decision_id?: string | null
  created_at: string
  payload: Record<string, unknown>
  status?: string
}

// Paginated envelope shape returned by paginated admin list endpoints
export type PaginatedRows<T> = {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export type LiveEvent = {
  event_type: string
  agent?: string
  timestamp: string
  payload?: Record<string, unknown> & { symbol?: string; price?: number }
}

// ---------------------------------------------------------------------------
// Market endpoint types — mirror admin-market-symbol-endpoint spec
// (openspec/changes/web-admin-market-pages/specs/admin-market-symbol-endpoint/spec.md)
// ---------------------------------------------------------------------------

export type MarketBar = {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export type Quote = {
  price: number
  change: number | null
  change_pct: number | null
  volume: number
  asof: string
}

export type RsRating = {
  value: number
  asof: string
}

export type SepaInfo = {
  stage: number
  since: string | null
}

export type InstitutionalRow = {
  date: string
  foreign: number
  trust: number
  dealer: number
  total: number
}

export type RecentPattern = {
  ts: string
  pattern: string
  score: number
  outcome: string
}

export type MarketSymbolDetail = {
  symbol: string
  quote: Quote
  bars_daily: MarketBar[]
  rs: RsRating | null
  sepa: SepaInfo | null
  institutional: InstitutionalRow[]
  recent_patterns: RecentPattern[]
}

// ---------------------------------------------------------------------------
// Screener types — mirror screener.run server-action endpoint
// ---------------------------------------------------------------------------

export type ScreenerHit = {
  symbol: string
  name?: string
  price?: number
  change_pct?: number | null
  pattern?: string
  score?: number
  [k: string]: unknown
}

export type ScreenerInput = {
  universe: string
  custom_symbols?: string[] | null
  filters?: Array<Record<string, unknown>> | null
  asof_date?: string | null
}

export type ScreenerRun = {
  run_id?: string
  asof_date_used?: string
  candidates?: ScreenerHit[]
  hits?: ScreenerHit[]
  elapsed_ms?: number
  [k: string]: unknown
}

// ---------------------------------------------------------------------------
// Backtest endpoint types — mirror admin-backtest-endpoints spec
// (openspec/changes/web-admin-backtest-pages/specs/admin-backtest-endpoints/spec.md)
// ---------------------------------------------------------------------------

export type BacktestStrategy = {
  name: string
  description: string
}

export type BacktestRunInput = {
  strategy: string
  symbols: string[]
  period_from: string
  period_to: string
  initial_capital?: number
  fee_discount?: number
  slippage_bps?: number
  day_trade?: boolean
}

export type BacktestRunResponse = {
  job_id: string
  status: 'completed' | 'failed'
  elapsed_ms: number
}

export type BacktestJobSummary = {
  id: string
  strategy: string
  period_from: string
  period_to: string
  status: 'completed' | 'failed'
  elapsed_ms: number
  created_at: string
  annual_return_pct: number | null
  sharpe: number | null
  max_drawdown_pct: number | null
  win_rate_pct: number | null
}

export type BacktestEquityPoint = {
  date: string
  equity: number
}

export type BacktestDrawdownPoint = {
  date: string
  dd: number
}

export type BacktestTrade = {
  entry_date: string
  exit_date: string
  symbol: string
  side: string
  qty: number
  entry_price: number
  exit_price: number
  pnl_twd: number
  hold_days: number
  pattern?: string | null
}

export type BacktestJobMetrics = {
  annual_return_pct: number | null
  sharpe: number | null
  max_drawdown_pct: number | null
  win_rate_pct: number | null
  total_return_pct?: number | null
  sortino?: number | null
  profit_factor?: number | null
  expectancy?: number | null
  total_trades?: number | null
}

export type BacktestJobDetail = {
  id: string
  strategy: string
  period_from: string
  period_to: string
  custom_symbols: string[]
  initial_capital: number
  status: 'completed' | 'failed'
  elapsed_ms: number
  created_at: string
  metrics: BacktestJobMetrics | null
  equity_curve: BacktestEquityPoint[]
  drawdown: BacktestDrawdownPoint[]
  trades: BacktestTrade[]
  error: { code: string; message: string } | null
}

// ---------------------------------------------------------------------------
// Settings endpoint types — mirror admin-settings-endpoint spec
// (openspec/changes/web-admin-settings-page/specs/admin-settings-endpoint/spec.md)
// ---------------------------------------------------------------------------

export type SettingsApiKeys = {
  anthropic: boolean
  finmind: boolean
  shioaji: boolean
}

export type SettingsTheme = {
  mode: 'system'
}

export type SettingsSafety = {
  auto_execute: boolean
  broker: 'mock' | 'shioaji-sim' | 'shioaji-live'
}

export type SettingsBreakers = {
  min_confidence: number
  daily_limit: number
  max_notional_pct: number
  max_sizing_deviation: number
  loss_lockout_hours: number
  loss_pct_threshold: number
  account_equity_twd: number
}

export type SettingsModelMix = {
  opus: number
  sonnet: number
  haiku: number
}

export type SettingsBudget = {
  used_usd: number
  budget_usd: number
  remaining_usd: number
  model_mix: SettingsModelMix
}

export type SettingsPayload = {
  api_keys: SettingsApiKeys
  theme: SettingsTheme
  safety: SettingsSafety
  breakers: SettingsBreakers
  budget: SettingsBudget
}

export type ConnectionProvider = 'shioaji' | 'finmind'

export type TestConnectionResult = {
  ok: boolean
  latency_ms?: number
  error?: string
}

// ---------------------------------------------------------------------------
// Skills endpoint types — mirror admin-skills-endpoints spec
// (openspec/changes/web-admin-skills-pages/specs/admin-skills-endpoints/spec.md)
// ---------------------------------------------------------------------------

export type SkillCategory =
  | 'data'
  | 'indicator'
  | 'signal'
  | 'decider'
  | 'gate'
  | 'tool'
  | 'report'

export type Skill = {
  name: string
  description: string
  category: SkillCategory
  body_preview: string
  body_truncated: boolean
  cited_specs: string[]
}

export type SkillDetail = {
  name: string
  description: string
  category: SkillCategory
  body: string
  cited_specs: string[]
}

// ---------------------------------------------------------------------------
// Memory endpoint types — mirror admin-memory-endpoints spec
// (openspec/changes/web-admin-memory-page-and-store/specs/admin-memory-endpoints/spec.md)
// ---------------------------------------------------------------------------

export type MemoryKind = 'note' | 'lesson' | 'proposal' | 'review_summary'

export type MemoryRow = {
  id: number
  kind: MemoryKind
  content: string
  content_preview: string
  content_truncated: boolean
  tags: string[]
  source: string | null
  created_at: string
}

export type MemoryRowsResponse = {
  items: MemoryRow[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

// ---------------------------------------------------------------------------
// Proposal endpoint types — mirror admin-proposals-endpoints spec
// (openspec/changes/admin-proposals-endpoints-and-pages/specs/admin-proposals-endpoints/spec.md)
// ---------------------------------------------------------------------------

export type ProposalStatus =
  | 'pending'
  | 'validating'
  | 'approved'
  | 'merged'
  | 'rejected'

export type ProposalPriority = 'high' | 'medium' | 'low'

export type Proposal = {
  slug: string
  proposal_id: string
  status: ProposalStatus
  topic: string
  target_section: string
  created_by: string
  created_at: string
  review_id: string | null
  priority: ProposalPriority
}

export type ProposalChangelogEntry =
  | {
      kind: 'transition'
      timestamp: string
      from_status: ProposalStatus
      to_status: ProposalStatus
      actor: string
      reason: string | null
    }
  | { kind: 'created'; timestamp: string; actor: string }
  | { kind: 'raw'; text: string }

export type ProposalDetail = Proposal & {
  body: {
    description: string
    motivation: string
    diff_draft: string
    expected_impact: string
    risk_assessment: string
    validation_plan: string
    expected_improvement: string
  }
  changelog: ProposalChangelogEntry[]
  extra_frontmatter: Partial<
    Record<
      | 'validation_report_path'
      | 'merged_to_version'
      | 'merged_at'
      | 'rejected_reason',
      string
    >
  >
}

export type ProposalsListResponse = {
  items: Proposal[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export type ProposalTransitionBody = {
  new_status: ProposalStatus
  actor: string
  reason?: string
  validation_report_path?: string
  merged_to_version?: string
}

export type ProposalTransitionResult = {
  slug: string
  new_status: ProposalStatus
  new_path: string
}

// ---------------------------------------------------------------------------
// Proposal validate endpoint types — mirror admin-proposal-validate-action spec
// (openspec/changes/admin-proposal-validate-action/specs/admin-proposals-endpoints/spec.md)
// ---------------------------------------------------------------------------

export type ValidateRequest = {
  strategy: string
  period: { from: string; to: string }
  param_overrides: string[]
  universe: string[]
  wfa_windows: number
  in_sample_ratio: number
  initial_capital: number | null
  dry_run: boolean
}

export type ValidateResponse = {
  verdict: 'pass' | 'fail'
  slug: string
  new_status: 'approved' | 'rejected' | 'validating'
  new_path: string | null
  report_path: string | null
  deltas: { sharpe: number; max_drawdown: number; win_rate: number }
  failures: string[]
}

// ---------------------------------------------------------------------------
// Review endpoint types — mirror admin-reviews-endpoints spec
// (openspec/changes/admin-reviews-endpoints-and-pages/specs/admin-reviews-endpoints/spec.md)
// ---------------------------------------------------------------------------

export type ReviewKind = 'monthly' | 'quarterly' | 'forced' | 'manual'

export type ReviewSummary = {
  review_id: string
  kind: ReviewKind
  period: { from: string; to: string }
  trade_count: number
  win_rate: number
  pf: number
  proposals_created: number
  completed_at: string
}

export type ReviewFileStatus = {
  exists: boolean
  path: string | null
}

export type ReviewFiles = {
  data_json: ReviewFileStatus
  attribution_json: ReviewFileStatus
  metrics_json: ReviewFileStatus
  critique_md: ReviewFileStatus
  report_md: ReviewFileStatus
  proposals_created_md: ReviewFileStatus
}

export type ReviewMetricsOverall = {
  win_rate: number
  profit_factor: number
  expectancy_pct: number
  max_drawdown_pct: number
  max_consecutive_loss: number
  avg_hold_days: number
}

export type ReviewProposalCreatedRow = {
  slug: string
  status: string
  priority: string
  target: string
}

export type ReviewDetail = {
  review_id: string
  partial: boolean
  summary: ReviewSummary | null
  files: ReviewFiles
  report: string | null
  metrics_overall: ReviewMetricsOverall | null
  proposals_created: ReviewProposalCreatedRow[]
}

export type ReviewsListResponse = {
  items: ReviewSummary[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export type Envelope<T> =
  | { ok: true; data: T }
  | { ok: false; error: { code: string; message: string } }

// ---------------------------------------------------------------------------
// ApiError
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  code: string
  httpStatus: number
  constructor(code: string, message: string, httpStatus: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.httpStatus = httpStatus
  }
}

// ---------------------------------------------------------------------------
// apiFetch
// ---------------------------------------------------------------------------

function authHeader(): Record<string, string> {
  const t = useAuthStore.getState().token
  return t ? { Authorization: `Bearer ${t}` } : {}
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...authHeader(),
    ...((init?.headers as Record<string, string>) ?? {}),
  }
  if (init?.body && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(path, { ...init, headers })

  if (res.status === 401) {
    logout()
    throw new ApiError('auth_invalid', 'unauthorised', 401)
  }

  let body: Envelope<T>
  try {
    body = (await res.json()) as Envelope<T>
  } catch (e) {
    throw new ApiError('non_json_response', `non-JSON response (${res.status}): ${(e as Error).message}`, res.status)
  }

  if ('ok' in body && body.ok) {
    return body.data
  }
  if ('ok' in body && !body.ok) {
    throw new ApiError(body.error.code, body.error.message, res.status)
  }
  throw new ApiError('envelope_invalid', 'response did not match { ok, ... } envelope', res.status)
}

// ---------------------------------------------------------------------------
// openSSE - fetch + ReadableStream parser supporting Authorization header
// ---------------------------------------------------------------------------

export type SseHandle = {
  close: () => void
}

export type SseHandlers = {
  onEvent: (event: LiveEvent) => void
  onUnauthorized: () => void
  onError?: (err: unknown) => void
}

export function openSSE(path: string, handlers: SseHandlers): SseHandle {
  const ctrl = new AbortController()
  const headers: Record<string, string> = { Accept: 'text/event-stream', ...authHeader() }
  let closed = false

  ;(async () => {
    let res: Response
    try {
      res = await fetch(path, { method: 'GET', headers, signal: ctrl.signal })
    } catch (err) {
      if (!closed) handlers.onError?.(err)
      return
    }
    if (res.status === 401) {
      handlers.onUnauthorized()
      return
    }
    if (!res.ok || !res.body) {
      handlers.onError?.(new Error(`SSE handshake failed: ${res.status}`))
      return
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE messages separated by blank line
        let sep = buffer.indexOf('\n\n')
        while (sep !== -1) {
          const raw = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          parseAndDispatch(raw, handlers.onEvent)
          sep = buffer.indexOf('\n\n')
        }
      }
    } catch (err) {
      if (!closed) handlers.onError?.(err)
    }
  })()

  return {
    close() {
      closed = true
      try { ctrl.abort() } catch { /* ignore */ }
    },
  }
}

// ---------------------------------------------------------------------------
// Market + screener wrappers
// ---------------------------------------------------------------------------

export function getMarketSymbol(
  symbol: string,
  options?: { days?: number },
): Promise<MarketSymbolDetail> {
  const path =
    options?.days != null
      ? `/api/admin/market/symbols/${encodeURIComponent(symbol)}?days=${options.days}`
      : `/api/admin/market/symbols/${encodeURIComponent(symbol)}`
  return apiFetch<MarketSymbolDetail>(path)
}

export function runScreener(input: ScreenerInput): Promise<ScreenerRun> {
  return apiFetch<ScreenerRun>('/api/admin/screener/run', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

// ---------------------------------------------------------------------------
// Backtest wrappers
// ---------------------------------------------------------------------------

export function listStrategies(): Promise<{ strategies: BacktestStrategy[] }> {
  return apiFetch<{ strategies: BacktestStrategy[] }>(
    '/api/admin/backtest/strategies',
  )
}

export function runBacktest(
  input: BacktestRunInput,
): Promise<BacktestRunResponse> {
  return apiFetch<BacktestRunResponse>('/api/admin/backtest/run', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function listBacktestJobs(
  limit?: number,
): Promise<{ items: BacktestJobSummary[]; count: number }> {
  const path =
    limit != null
      ? `/api/admin/backtest/jobs?limit=${encodeURIComponent(String(limit))}`
      : '/api/admin/backtest/jobs'
  return apiFetch<{ items: BacktestJobSummary[]; count: number }>(path)
}

export function getBacktestJob(jobId: string): Promise<BacktestJobDetail> {
  return apiFetch<BacktestJobDetail>(
    `/api/admin/backtest/jobs/${encodeURIComponent(jobId)}`,
  )
}

// ---------------------------------------------------------------------------
// Settings wrapper
// ---------------------------------------------------------------------------

export function getSettings(): Promise<SettingsPayload> {
  return apiFetch<SettingsPayload>('/api/admin/settings')
}

export function testConnection(
  provider: ConnectionProvider,
): Promise<TestConnectionResult> {
  return apiFetch<TestConnectionResult>(
    '/api/admin/settings/test-connection',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider }),
    },
  )
}

// ---------------------------------------------------------------------------
// Skills wrappers
// ---------------------------------------------------------------------------

export function listSkills(): Promise<{ items: Skill[] }> {
  return apiFetch<{ items: Skill[] }>('/api/admin/skills')
}

export function getSkill(name: string): Promise<SkillDetail> {
  return apiFetch<SkillDetail>(
    `/api/admin/skills/${encodeURIComponent(name)}`,
  )
}

// ---------------------------------------------------------------------------
// Memory wrappers
// ---------------------------------------------------------------------------

function buildQueryString(params: Record<string, string | number | undefined | null>): string {
  const parts: string[] = []
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue
    if (typeof value === 'string' && value.length === 0) continue
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
  }
  return parts.length === 0 ? '' : `?${parts.join('&')}`
}

export function listMemory(
  params: { kind?: MemoryKind; tag?: string; limit?: number; offset?: number } = {},
): Promise<MemoryRowsResponse> {
  const qs = buildQueryString({
    kind: params.kind,
    tag: params.tag,
    limit: params.limit,
    offset: params.offset,
  })
  return apiFetch<MemoryRowsResponse>(`/api/admin/memory/rows${qs}`)
}

export function searchMemory(
  params: { q: string; limit?: number; offset?: number },
): Promise<MemoryRowsResponse> {
  const qs = `?q=${encodeURIComponent(params.q)}` +
    (params.limit !== undefined ? `&limit=${encodeURIComponent(String(params.limit))}` : '') +
    (params.offset !== undefined ? `&offset=${encodeURIComponent(String(params.offset))}` : '')
  return apiFetch<MemoryRowsResponse>(`/api/admin/memory/search${qs}`)
}

export function createMemory(
  body: {
    kind: MemoryKind
    content: string
    tags?: string[]
    source?: string | null
  },
): Promise<MemoryRow> {
  return apiFetch<MemoryRow>('/api/admin/memory/rows', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// ---------------------------------------------------------------------------
// Proposal wrappers
// ---------------------------------------------------------------------------

export function listProposals(
  params: { status?: ProposalStatus; limit?: number; offset?: number } = {},
): Promise<ProposalsListResponse> {
  const qs = buildQueryString({
    status: params.status,
    limit: params.limit,
    offset: params.offset,
  })
  return apiFetch<ProposalsListResponse>(`/api/admin/proposals${qs}`)
}

export function getProposal(slug: string): Promise<ProposalDetail> {
  return apiFetch<ProposalDetail>(
    `/api/admin/proposals/${encodeURIComponent(slug)}`,
  )
}

export function transitionProposal(
  slug: string,
  body: ProposalTransitionBody,
): Promise<ProposalTransitionResult> {
  return apiFetch<ProposalTransitionResult>(
    `/api/admin/proposals/${encodeURIComponent(slug)}/transition`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
}

export function validateProposal(
  slug: string,
  body: ValidateRequest,
): Promise<ValidateResponse> {
  return apiFetch<ValidateResponse>(
    `/api/admin/proposals/${encodeURIComponent(slug)}/validate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
}

// ---------------------------------------------------------------------------
// Review wrappers
// ---------------------------------------------------------------------------

export function listReviews(
  params: { kind?: ReviewKind; limit?: number; offset?: number } = {},
): Promise<ReviewsListResponse> {
  const qs = buildQueryString({
    kind: params.kind,
    limit: params.limit,
    offset: params.offset,
  })
  return apiFetch<ReviewsListResponse>(`/api/admin/reviews${qs}`)
}

export function getReview(reviewId: string): Promise<ReviewDetail> {
  return apiFetch<ReviewDetail>(
    `/api/admin/reviews/${encodeURIComponent(reviewId)}`,
  )
}

// ---------------------------------------------------------------------------
// Swarm runs — admin-swarm-endpoints-and-pages
// ---------------------------------------------------------------------------

export type SwarmPreset = {
  name: string
  title: string
  description: string
  nodes: string[]
  params_schema: Record<string, unknown>
}

export type SwarmRunRequest = {
  preset: string
  params: Record<string, unknown>
}

export type SwarmRunSummary = {
  id: string
  preset: string
  status: 'completed' | 'failed'
  elapsed_ms: number
  created_at: string
}

export type SwarmRunRow = SwarmRunSummary & {
  params: Record<string, unknown>
  result: Record<string, unknown>
}

export function listSwarmPresets(): Promise<{ items: SwarmPreset[] }> {
  return apiFetch<{ items: SwarmPreset[] }>('/api/admin/swarm/presets')
}

export function runSwarm(body: SwarmRunRequest): Promise<SwarmRunRow> {
  return apiFetch<SwarmRunRow>('/api/admin/swarm/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function listSwarmRuns(
  limit?: number,
): Promise<{ items: SwarmRunSummary[]; limit: number }> {
  const qs = limit !== undefined ? `?limit=${limit}` : ''
  return apiFetch<{ items: SwarmRunSummary[]; limit: number }>(
    `/api/admin/swarm/runs${qs}`,
  )
}

export function getSwarmRun(id: string): Promise<SwarmRunRow> {
  return apiFetch<SwarmRunRow>(
    `/api/admin/swarm/runs/${encodeURIComponent(id)}`,
  )
}

// ---------------------------------------------------------------------------
// Chat — admin-chat-sessions-endpoints-and-pages
// ---------------------------------------------------------------------------

export type ChatSessionStatus = 'active' | 'deleted'

export type ChatSessionSummary = {
  id: string
  title: string
  model: string
  status: ChatSessionStatus
  created_at: string
  updated_at: string
  message_count: number
}

export type ChatMessageRole = 'user' | 'assistant' | 'tool_result'

export type ChatMessage = {
  id: string
  session_id: string
  role: ChatMessageRole
  content: string
  tool_calls_json: string | null
  tool_result_for: string | null
  llm_cost_id: string | null
  created_at: string
}

export type ChatSessionDetail = {
  session: ChatSessionSummary
  messages: ChatMessage[]
}

export type ChatSessionCreateRequest = {
  title?: string
  model?: string
}

export type ChatSnippetHit = {
  message_id: string
  snippet: string
  created_at: string
}

export type ChatSearchGroup = {
  session_id: string
  session_title: string
  session_status: ChatSessionStatus
  hits: ChatSnippetHit[]
}

export type ChatSearchResult = {
  groups: ChatSearchGroup[]
  total_hits: number
}

export function listChatSessions(opts?: {
  limit?: number
  offset?: number
}): Promise<PaginatedRows<ChatSessionSummary>> {
  const params = new URLSearchParams()
  if (opts?.limit !== undefined) params.set('limit', String(opts.limit))
  if (opts?.offset !== undefined) params.set('offset', String(opts.offset))
  const qs = params.toString()
  return apiFetch<PaginatedRows<ChatSessionSummary>>(
    `/api/admin/chat/sessions${qs ? `?${qs}` : ''}`,
  )
}

export function createChatSession(
  body: ChatSessionCreateRequest = {},
): Promise<ChatSessionSummary> {
  return apiFetch<ChatSessionSummary>('/api/admin/chat/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function getChatSession(id: string): Promise<ChatSessionDetail> {
  return apiFetch<ChatSessionDetail>(
    `/api/admin/chat/sessions/${encodeURIComponent(id)}`,
  )
}

export function deleteChatSession(id: string): Promise<{ deleted: boolean }> {
  return apiFetch<{ deleted: boolean }>(
    `/api/admin/chat/sessions/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
  )
}

export function searchChat(opts: {
  q: string
  dateFrom?: string
  dateTo?: string
  limit?: number
}): Promise<ChatSearchResult> {
  const params = new URLSearchParams({ q: opts.q })
  if (opts.dateFrom) params.set('date_from', opts.dateFrom)
  if (opts.dateTo) params.set('date_to', opts.dateTo)
  if (opts.limit !== undefined) params.set('limit', String(opts.limit))
  return apiFetch<ChatSearchResult>(
    `/api/admin/chat/search?${params.toString()}`,
  )
}

function parseAndDispatch(raw: string, onEvent: (e: LiveEvent) => void): void {
  const lines = raw.split('\n')
  const dataLines: string[] = []
  for (const line of lines) {
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''))
    }
  }
  if (dataLines.length === 0) return
  const payload = dataLines.join('\n').trim()
  if (!payload || payload === '{}') return
  try {
    const parsed = JSON.parse(payload) as LiveEvent
    onEvent(parsed)
  } catch {
    // ignore malformed events
  }
}