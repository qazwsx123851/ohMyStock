/**
 * /settings — read-only Settings snapshot.
 *
 * 4 sections (API keys / Theme / Safety / Breakers) per
 * docs/web-admin-page-designs.md §16. All controls are disabled; users
 * edit `.env` and restart to change values. The Safety card switches
 * between `--warning` (auto_execute=false) and `--destructive`
 * (auto_execute=true) variants, paired with AlertTriangle / AlertCircle
 * so colour is never the only signal.
 *
 * Spec: openspec/changes/web-admin-settings-page/specs/web-admin-settings-page/spec.md
 */
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertCircle, AlertTriangle, CheckCircle2, Loader2, XCircle } from 'lucide-react'
import {
  ApiError,
  getSettings,
  testConnection,
  type ConnectionProvider,
  type SettingsBreakers,
  type SettingsBudget,
  type SettingsPayload,
  type TestConnectionResult,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const ENV_HINT = '編輯 .env 並重啟以變更'
const intFmt = new Intl.NumberFormat('zh-TW')
const usdFmt = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

function pctDisplay(v: number): string {
  // 0.25 -> "25"; -0.05 -> "-5". One-decimal precision dropped when integer.
  const pct = v * 100
  if (Number.isInteger(pct)) return String(pct)
  return pct.toFixed(1)
}

// ---------------------------------------------------------------------------
// Section: API keys
// ---------------------------------------------------------------------------

function ApiKeysCard({ data }: { data: SettingsPayload['api_keys'] }) {
  const rows: Array<{ label: string; key: keyof SettingsPayload['api_keys'] }> =
    [
      { label: 'Anthropic', key: 'anthropic' },
      { label: 'FinMind', key: 'finmind' },
      { label: 'Shioaji', key: 'shioaji' },
    ]
  return (
    <Card className="p-6">
      <h2 className="text-base font-semibold">API keys</h2>
      <div className="mt-4 space-y-3">
        {rows.map((r) => {
          const isSet = data[r.key]
          return (
            <div
              key={r.key}
              className="flex items-center justify-between gap-4 border-b pb-3 last:border-b-0 last:pb-0"
            >
              <span className="text-sm font-medium">{r.label}</span>
              {isSet ? (
                <Badge
                  variant="secondary"
                  data-state="set"
                  className="bg-muted text-foreground"
                >
                  已設定
                </Badge>
              ) : (
                <Badge
                  variant="outline"
                  data-state="unset"
                  className="text-muted-foreground"
                >
                  未設定
                </Badge>
              )}
            </div>
          )
        })}
      </div>
      <p className="mt-4 text-xs text-muted-foreground">{ENV_HINT}</p>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Section: Theme
// ---------------------------------------------------------------------------

function ThemeCard() {
  return (
    <Card className="p-6">
      <h2 className="text-base font-semibold">主題</h2>
      <div className="mt-4">
        <select
          disabled
          className="block w-full max-w-xs rounded-md border border-input bg-muted px-3 py-2 text-sm text-muted-foreground disabled:cursor-not-allowed disabled:opacity-100"
          value="system"
          onChange={() => {
            /* disabled */
          }}
          aria-label="主題模式"
        >
          <option value="system">跟隨系統</option>
        </select>
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        此版本未提供主題切換 UI
      </p>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Section: Safety
// ---------------------------------------------------------------------------

function SafetyCard({ data }: { data: SettingsPayload['safety'] }) {
  const isLive = data.auto_execute
  const Icon = isLive ? AlertCircle : AlertTriangle
  return (
    <Card
      className={cn(
        'p-6',
        isLive
          ? 'border-destructive bg-destructive/5'
          : 'border-warning bg-warning/5',
      )}
      data-auto-execute={isLive ? 'on' : 'off'}
    >
      <div className="flex items-center gap-2">
        <Icon
          className={cn(
            'size-4',
            isLive ? 'text-destructive' : 'text-warning',
          )}
          aria-hidden
        />
        <h2 className="text-base font-semibold">Safety</h2>
      </div>
      <div className="mt-3 space-y-2 text-sm">
        {isLive ? (
          <p className="font-medium text-destructive">
            ⚠ AUTO_EXECUTE 已啟用
          </p>
        ) : (
          <p className="text-foreground">
            AUTO_EXECUTE 關閉（人工 Confirm Gate）
          </p>
        )}
        <p className="text-muted-foreground">
          Broker：<span className="font-mono">{data.broker}</span>
        </p>
      </div>
      <p className="mt-4 text-xs text-muted-foreground">{ENV_HINT}</p>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Section: Breakers
// ---------------------------------------------------------------------------

type BreakerField = {
  label: string
  key: keyof SettingsBreakers
  format: (v: number) => string
  suffix?: string
}

const BREAKER_FIELDS: BreakerField[] = [
  {
    label: '信心下限',
    key: 'min_confidence',
    format: (v) => v.toFixed(2),
  },
  {
    label: '單日上限',
    key: 'daily_limit',
    format: (v) => String(v),
    suffix: '筆',
  },
  {
    label: '配額（單筆 Notional）',
    key: 'max_notional_pct',
    format: pctDisplay,
    suffix: '%',
  },
  {
    label: '偏離上限',
    key: 'max_sizing_deviation',
    format: pctDisplay,
    suffix: '%',
  },
  {
    label: '虧損鎖定（小時）',
    key: 'loss_lockout_hours',
    format: (v) => String(v),
    suffix: 'h',
  },
  {
    label: '虧損鎖定觸發',
    key: 'loss_pct_threshold',
    format: pctDisplay,
    suffix: '%',
  },
  {
    label: '帳戶權益',
    key: 'account_equity_twd',
    format: (v) => intFmt.format(v),
    suffix: 'TWD',
  },
]

function BreakersCard({ data }: { data: SettingsBreakers }) {
  return (
    <Card className="p-6">
      <h2 className="text-base font-semibold">Breakers</h2>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {BREAKER_FIELDS.map((f) => (
          <label key={f.key} className="block">
            <span className="block text-xs text-muted-foreground">
              {f.label}
            </span>
            <span className="mt-1 flex items-center gap-2">
              <input
                type="text"
                inputMode="numeric"
                disabled
                readOnly
                value={f.format(data[f.key])}
                className="block w-full rounded-md border border-input bg-muted px-3 py-2 text-sm tabular text-foreground disabled:cursor-not-allowed disabled:opacity-100"
                aria-label={f.label}
                onChange={() => {
                  /* disabled */
                }}
              />
              {f.suffix && (
                <span className="text-xs text-muted-foreground">
                  {f.suffix}
                </span>
              )}
            </span>
          </label>
        ))}
      </div>
      <p className="mt-4 text-xs text-muted-foreground">{ENV_HINT}</p>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Section: Connection test (ST-B1)
// ---------------------------------------------------------------------------

function ProviderTestRow({
  provider,
  label,
}: {
  provider: ConnectionProvider
  label: string
}) {
  const m = useMutation<TestConnectionResult, ApiError>({
    mutationFn: () => testConnection(provider),
  })
  const result = m.data
  return (
    <div
      className="flex items-center justify-between gap-4 border-b pb-3 last:border-b-0 last:pb-0"
      data-provider={provider}
    >
      <span className="text-sm font-medium">{label}</span>
      <div className="flex items-center gap-3">
        <div className="min-w-0 text-sm" data-testid={`result-${provider}`}>
          {m.isPending ? (
            <span className="flex items-center gap-1 text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" aria-hidden /> 測試中…
            </span>
          ) : m.error ? (
            <span className="flex items-center gap-1 text-destructive">
              <XCircle className="size-3.5" aria-hidden /> {m.error.message}
            </span>
          ) : result ? (
            result.ok ? (
              <span className="flex items-center gap-1 text-up">
                <CheckCircle2 className="size-3.5" aria-hidden /> 連線成功
                {result.latency_ms != null && (
                  <span className="text-muted-foreground">
                    （{result.latency_ms} ms）
                  </span>
                )}
              </span>
            ) : (
              <span className="flex items-center gap-1 text-destructive">
                <XCircle className="size-3.5" aria-hidden /> 失敗：
                {result.error ?? '未知錯誤'}
              </span>
            )
          ) : null}
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={m.isPending}
          onClick={() => m.mutate()}
        >
          測試連線
        </Button>
      </div>
    </div>
  )
}

function ConnectionTestCard() {
  return (
    <Card className="p-6">
      <h2 className="text-base font-semibold">連線測試</h2>
      <div className="mt-4 space-y-3">
        <ProviderTestRow provider="shioaji" label="Shioaji（模擬倉登入）" />
        <ProviderTestRow provider="finmind" label="FinMind（最小查詢）" />
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        測試僅做輕量呼叫，不下單、不消耗顯著額度。
      </p>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Section: Budget / model mix (ST-B2)
// ---------------------------------------------------------------------------

const MODEL_MIX_ROWS: Array<{ label: string; key: keyof SettingsBudget['model_mix'] }> = [
  { label: 'Opus', key: 'opus' },
  { label: 'Sonnet', key: 'sonnet' },
  { label: 'Haiku', key: 'haiku' },
]

function BudgetCard({ data }: { data: SettingsBudget }) {
  return (
    <Card className="p-6">
      <h2 className="text-base font-semibold">本月額度與模型分布</h2>
      <div className="mt-4 grid grid-cols-3 gap-4">
        <div>
          <span className="block text-xs text-muted-foreground">已用</span>
          <span className="mt-1 block tabular text-lg font-semibold">
            {usdFmt.format(data.used_usd)}
          </span>
        </div>
        <div>
          <span className="block text-xs text-muted-foreground">預算</span>
          <span className="mt-1 block tabular text-lg font-semibold">
            {usdFmt.format(data.budget_usd)}
          </span>
        </div>
        <div>
          <span className="block text-xs text-muted-foreground">剩餘</span>
          <span className="mt-1 block tabular text-lg font-semibold">
            {usdFmt.format(data.remaining_usd)}
          </span>
        </div>
      </div>
      <div className="mt-4 space-y-2">
        <span className="block text-xs text-muted-foreground">模型分布</span>
        {MODEL_MIX_ROWS.map((r) => (
          <div
            key={r.key}
            className="flex items-center justify-between text-sm"
            data-model={r.key}
          >
            <span>{r.label}</span>
            <span className="tabular text-muted-foreground">
              {(data.model_mix[r.key] * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
      <p className="mt-4 text-xs text-muted-foreground">USD · 本月累計（唯讀）</p>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// SettingsPage
// ---------------------------------------------------------------------------

export function SettingsPage() {
  const q = useQuery<SettingsPayload, ApiError>({
    queryKey: ['settings'],
    queryFn: getSettings,
    retry: false,
  })

  if (q.isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="p-6">
            <Skeleton className="h-5 w-24" />
            <div className="mt-4 space-y-3">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-2/3" />
            </div>
          </Card>
        ))}
      </div>
    )
  }

  if (q.error) {
    return (
      <Card
        role="alert"
        className="border-destructive/50 bg-destructive/5 p-6"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm text-destructive">
            <AlertCircle className="size-4" aria-hidden />
            <span>載入失敗 — {q.error.message}</span>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => q.refetch()}
          >
            重試
          </Button>
        </div>
      </Card>
    )
  }

  if (!q.data) return null
  const data = q.data

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">設定</h1>
        <p className="text-sm text-muted-foreground">
          只讀檢視。變更請編輯 <span className="font-mono">.env</span> 並重啟服務。
        </p>
      </header>
      <ApiKeysCard data={data.api_keys} />
      <ConnectionTestCard />
      {data.budget && <BudgetCard data={data.budget} />}
      <ThemeCard />
      <SafetyCard data={data.safety} />
      <BreakersCard data={data.breakers} />
    </div>
  )
}
