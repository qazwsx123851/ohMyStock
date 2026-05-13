# web-admin-swarm-pages Specification

## Purpose

Defines the web-admin `/swarm` (preset card grid) and `/swarm/:preset/:runId` (vertical stepper with SSE-patched live state) pages, the `<RunSwarmDialog>` form component with localStorage persistence + DialogDescription + per-input Labels, the new `web-admin/src/lib/api.ts` exports (`SwarmPreset`/`SwarmRunRequest`/`SwarmRunSummary`/`SwarmRunRow` types + `listSwarmPresets`/`runSwarm`/`listSwarmRuns`/`getSwarmRun` helpers), router wiring + stubs cleanup, and stepper-row keyboard a11y (button + focus-visible ring + aria-live polite + Loader2 motion-reduce:animate-none + aria-hidden icons).

## Requirements

### Requirement: /swarm 頁取代 stub，列出 preset cards 與「Run」按鈕

`web-admin/src/pages/SwarmPage.tsx` SHALL 取代 `stubs.tsx` 內的 `SwarmPage` export，渲染：

- **Header**: `<h1>` 「Swarm」+ 副標 `<p className="text-muted-foreground">「選股、復盤、報表、策略提案…」`
- **Preset grid**: responsive `1/2/3-col`（mobile/tablet/desktop），每張 `<Card>` 一個 preset，含：
  - `<CardTitle>` = `preset.title`
  - `<CardDescription>` = `preset.description`
  - 5 顆 `<Badge variant="outline">` 列出 `preset.nodes`（Phase 5 preset 顯示 `data_loader` / `attributor` / `aggregator` / `critic` / `proposer`）
  - 底部 `[Run...]` button（`disabled={!presets}` loading 期）
- 點 `[Run...]` SHALL 開 `<RunSwarmDialog>` 並填入該 preset 的 `params_schema`
- **States**:
  - loading：3-skeleton card grid，每個 skeleton SHALL 為 `h-[180px]` 以符合實際 Card 高度（避免 CLS）
  - error: destructive Card + retry button
  - empty (`data.items.length === 0`): 中性提示「尚無 preset」（防呆，v0 不會發生）

`SwarmPage` SHALL 透過 `useQuery(['swarm-presets'], listSwarmPresets)` 取得 preset list。

#### Scenario: 顯示 phase5-review preset card
- **GIVEN** mock API 回 `{items: [{name:"phase5-review", title:"Phase 5 復盤", description:"...", nodes:[...], params_schema:{...}}]}`
- **WHEN** route `/swarm` mount
- **THEN** DOM 含 `<h1>Swarm</h1>`、含一張 card 標題為「Phase 5 復盤」、含 5 顆 node badge、含 `[Run...]` button

#### Scenario: 點 Run 開 RunSwarmDialog
- **WHEN** user click `[Run...]` button on `phase5-review` card
- **THEN** `<RunSwarmDialog>` SHALL 開啟，內含 preset.params_schema 對應的 input 欄位（period_from / period_to / limit_trades / dry_run / force）

#### Scenario: API loading 顯示 skeleton
- **GIVEN** API 尚未回應
- **WHEN** route `/swarm` mount
- **THEN** DOM 含 3 個 `data-slot="skeleton"` 元素

---

### Requirement: <RunSwarmDialog> 表單行為

`web-admin/src/components/run-swarm-dialog.tsx` SHALL 提供 controlled `<Dialog>`，props `{ open, onOpenChange, preset }`。內含：

- `<DialogHeader>` 內 `<DialogTitle>`（preset.title）+ `<DialogDescription>`（固定文案，例：「跑一次 Phase 5 復盤；勾 dry-run 則不呼叫 LLM 也不寫檔」）
- 5 個欄位（Phase 5 preset），**每個欄位 SHALL 有對應 `<Label htmlFor>`**（placeholder-only 不被允許）：
  - `period_from: <input type="date" required>` + `<Label htmlFor="period_from">起始日</Label>`
  - `period_to: <input type="date" required>` + `<Label htmlFor="period_to">結束日</Label>`
  - `limit_trades: <input type="number" min="1">` (optional, 預設空 = 全部) + `<Label>`
  - `dry_run: <Checkbox defaultChecked>` + `<Label>`（醒目標示「不會實際呼叫 LLM、不寫檔」+ Lucide AlertTriangle icon）
  - `force: <Checkbox>` + `<Label>`（標示「覆寫既有 reviews/<review_id>/ 資料夾」）
- 底部 `[Submit]` + `[Cancel]`
- Submit 行為：呼叫 `runSwarm({preset: preset.name, params: {...}})`、loading 時 disable submit + 顯示 `Loader2` spinner
- 成功：`toast({title:"Swarm 完成", description:"run_id: <id>"})` + invalidate `['swarm-runs']` query + `onOpenChange(false)` + navigate `/swarm/<preset>/<run_id>`
- 失敗：保持 dialog 開啟、底部紅字顯示 `{code}: {message}`、`role="alert" aria-live="polite"`

最後一次成功的 form values（period_from / period_to / limit_trades）SHALL persist 到 `localStorage['ohmystock.admin.lastSwarm']`；`dry_run` 與 `force` 永遠 reset 為預設值。

#### Scenario: 提交 happy path 跳轉 detail
- **GIVEN** dialog 開啟，user 填 period_from=2026-04-01、period_to=2026-04-30、dry_run=true
- **WHEN** click Submit、API 回 `{ok:true, data:{id:"swr_abc123def456", status:"completed", preset:"phase5-review", ...}}`
- **THEN** SHALL 顯示 toast、invalidate `['swarm-runs']`、navigate 到 `/swarm/phase5-review/swr_abc123def456`

#### Scenario: 提交失敗保留 dialog 並顯示錯誤
- **GIVEN** dialog 開啟、API 回 `{ok:false, error:{code:"missing_api_key", message:"ANTHROPIC_API_KEY not set"}}`
- **WHEN** click Submit
- **THEN** dialog 仍然開啟、底部含 `role="alert"` 元素、文字含 `"missing_api_key"` 與 `"ANTHROPIC_API_KEY not set"`

#### Scenario: 表單值 persist 到 localStorage
- **GIVEN** 上次成功提交 period_from=2026-03-01、period_to=2026-03-31
- **WHEN** dialog 重新打開
- **THEN** period_from input value 為 `"2026-03-01"`、period_to 為 `"2026-03-31"`、dry_run 為 `true`（reset，**非** persist）

---

### Requirement: /swarm/:preset/:runId 頁取代 stub，顯示 vertical stepper + node outputs

`web-admin/src/pages/SwarmRunPage.tsx` SHALL 取代 `stubs.tsx` 內的 `SwarmRunPage` export。透過 `useParams` 取 `preset` 與 `runId`、透過 `useQuery(['swarm-run', runId], () => getSwarmRun(runId))` 取資料。

渲染：

- **Header**: 返回連結 `<Link to="/swarm">← Swarm</Link>` + `<h1>` = `<preset.title> · <runId>` + `<Badge>` 顯示 status (`completed` neutral secondary、`failed` destructive，**不**用紅漲綠跌)
- **Meta**: `created_at`、`elapsed_ms`、（若 `result.review_id` 存在）`<Link to={'/reviews/' + review_id}>` cross-link
- **Vertical stepper**: 5 個節點各自一 row。Stepper 容器 SHALL 設 `aria-live="polite"`，SSE-driven 狀態變化能被 screen reader 即時讀出。從 `result.node_outputs` 推狀態：
  - 已完成（key 存在）→ `CheckCircle2` icon (text-green-600, `aria-hidden="true"`) + `<span>done</span>` + `elapsed_ms`
  - 進行中（SSE 收到 `swarm_node_started` 但尚未 `swarm_node_completed`）→ `Loader2` 旋轉（`animate-spin motion-reduce:animate-none`、`aria-hidden="true"`）+ `<span>running</span>`
  - 失敗節點（`result.failed_node === node.name`）→ `XCircle` (text-destructive, `aria-hidden="true"`) + `<span>failed</span>`
  - 其他 → `Circle` (text-muted-foreground, `aria-hidden="true"`) + `<span>queued</span>`
  - 每 row click 展開 `<pre className="text-xs whitespace-pre-wrap max-h-[40vh] overflow-auto">` 顯示對應 `result.node_outputs[node]`（JSON 格式化），失敗節點額外顯示 `result.error.message`
- **States**:
  - 404 → 中性 empty state「找不到 run」+ 返回連結（**不**顯示 destructive Card）
  - error → destructive Card + retry button
  - loading → header skeleton + 5 row skeleton（每個 skeleton row SHALL 為 `h-12` 以匹配真實 row 高度，避免 CLS）

紅漲綠跌 SHALL **不**套用於本頁（無價格語意）。圖示 + 文字 + 顏色三重編碼狀態以滿足 a11y。

#### Scenario: 完成的 run 顯示 5 個 done 節點
- **GIVEN** API 回 `{id:"swr_x", status:"completed", preset:"phase5-review", result:{node_outputs:{data_loader:..., attributor:..., aggregator:..., critic:..., proposer:...}}, elapsed_ms:12345, ...}`
- **WHEN** route `/swarm/phase5-review/swr_x` mount
- **THEN** DOM 含 5 個 stepper row 各自 `done` 標記、Badge 顯示 `completed`

#### Scenario: 失敗的 run 標出失敗節點
- **GIVEN** API 回 `{id:"swr_y", status:"failed", result:{failed_node:"aggregator", completed_nodes:["data_loader","attributor"], error:{code:"runtime_error", message:"aggregator boom"}}}`
- **WHEN** route mount
- **THEN** DOM 含 stepper：data_loader=done、attributor=done、aggregator=failed、critic=queued、proposer=queued
- **AND** Badge 顯示 `failed`（destructive variant）
- **AND** aggregator row 展開時可見 `"aggregator boom"` 字串

#### Scenario: SSE 即時 patch 進行中的 run
- **GIVEN** 進入頁面時 SSE subscriber 已掛
- **WHEN** SSE 推 `{event_type:"swarm_node_started", payload:{run_id:"swr_y", node:"attributor"}}`
- **THEN** stepper attributor row SHALL 顯示 `running`（含 `Loader2` 旋轉 icon）
- **WHEN** SSE 推 `{event_type:"swarm_node_completed", payload:{run_id:"swr_y", node:"attributor", elapsed_ms:230}}`
- **THEN** attributor row SHALL 變 `done`、顯示 `230ms`

#### Scenario: SSE event 不屬於本 run 的 ignored
- **GIVEN** 頁面在 `swr_y`
- **WHEN** SSE 推 `{event_type:"swarm_node_started", payload:{run_id:"swr_other", node:"data_loader"}}`
- **THEN** 本頁 stepper SHALL 不變動

#### Scenario: 404 顯示 empty state
- **GIVEN** API 回 `{ok:false, error:{code:"not_found", message:"swarm run not found: swr_zzz"}}`
- **WHEN** route `/swarm/phase5-review/swr_zzz` mount
- **THEN** DOM 含「找不到 run」字樣 + 返回連結，**不**含 destructive Card

#### Scenario: review_id cross-link
- **GIVEN** API 回的 `result.review_id == "manual-2026-04-01-to-2026-04-30"`
- **WHEN** route mount
- **THEN** DOM 含 `<a href="/reviews/manual-2026-04-01-to-2026-04-30">` 元素

---

### Requirement: Stepper row 為可鍵盤操作的 button

每個 stepper row SHALL 渲染為 `<button type="button">`（若必須容納 `<pre>` 展開區則改用 `<div role="button" tabIndex={0} onKeyDown>` 並對 Enter / Space 觸發 toggle）。Row SHALL 套用 `cursor-pointer` + `focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-md` 樣式，確保鍵盤焦點清晰可見。狀態文字 `<span>done|running|failed|queued</span>` SHALL 為 SR 朗讀的主要來源（icon 一律 `aria-hidden="true"`）。

#### Scenario: row 可由鍵盤展開
- **GIVEN** 焦點在第 2 個 stepper row 上
- **WHEN** user 按 Enter 或 Space
- **THEN** 對應 `<pre>` SHALL 展開（與 click 行為一致）

#### Scenario: focus ring 可見
- **WHEN** user Tab 到第 1 個 stepper row
- **THEN** DOM 在該元素上 SHALL 含 `focus-visible:ring-2` 對應的 outline ring

#### Scenario: aria-live 公告狀態變化
- **GIVEN** stepper 容器有 `aria-live="polite"`
- **WHEN** SSE 推 `swarm_node_completed` 將 attributor row 從 `running` 改為 `done`
- **THEN** screen reader SHALL 朗讀新的文字內容（包含 `done` 字樣）

#### Scenario: motion-reduce 停止旋轉
- **GIVEN** user OS 設定 `prefers-reduced-motion: reduce`
- **WHEN** running 狀態的 `Loader2` icon 渲染
- **THEN** computed style `animation` SHALL 為 `none`（`motion-reduce:animate-none` 生效）

---

### Requirement: web-admin/src/lib/api.ts 新增 4 個 helper 與 4 個型別

`web-admin/src/lib/api.ts` SHALL 新增以下 export（沿用 `apiFetch` 與 `{ok,data,error}` envelope 解包）：

- `listSwarmPresets(): Promise<{items: SwarmPreset[]}>`
- `runSwarm(body: SwarmRunRequest): Promise<SwarmRunRow>`
- `listSwarmRuns(limit?: number): Promise<{items: SwarmRunSummary[], limit: number}>`
- `getSwarmRun(id: string): Promise<SwarmRunRow>`

對應 TypeScript 型別：

- `SwarmPreset`: `{name, title, description, nodes: string[], params_schema: Record<string, unknown>}`
- `SwarmRunRequest`: `{preset: string, params: Record<string, unknown>}`
- `SwarmRunSummary`: `{id, preset, status: "completed"|"failed", elapsed_ms, created_at}`
- `SwarmRunRow`: `SwarmRunSummary & {params, result: Record<string, unknown>}`

#### Scenario: api.ts 含 4 個新 export
- **WHEN** import `{ listSwarmPresets, runSwarm, listSwarmRuns, getSwarmRun } from '@/lib/api'`
- **THEN** 4 個 binding SHALL 全部為 function 型別（不 undefined）

#### Scenario: getSwarmRun 對 404 拋 ApiError
- **GIVEN** mock fetch 回 status=404、body `{ok:false, error:{code:"not_found", message:"..."}}`
- **WHEN** await getSwarmRun("swr_zzz")
- **THEN** SHALL 拋 ApiError，instance code === "not_found"

---

### Requirement: 路由表 wiring 與 stubs 清理

`web-admin/src/main.tsx`（或 router 定義所在）SHALL 將 `/swarm` route 從 `stubs.SwarmPage` 換成新 `SwarmPage`，將 `/swarm/:preset/:runId` 換成 `SwarmRunPage`。

`web-admin/src/pages/stubs.tsx` SHALL 移除 `SwarmPage` 與 `SwarmRunPage` 兩個 export（相對應的 `make(...)` 行整段刪除）。其他 stub (`ChatPage`, `ChatSessionPage`, `SessionsPage`) SHALL 不受影響。

#### Scenario: stubs.tsx 不再 export SwarmPage
- **WHEN** 執行 grep `^export const SwarmPage` on `web-admin/src/pages/stubs.tsx`
- **THEN** 0 個 match

#### Scenario: 路由表指向真實組件
- **WHEN** grep `from '@/pages/SwarmPage'` 與 `from '@/pages/SwarmRunPage'` on `web-admin/src/main.tsx` (或 router file)
- **THEN** 各至少 1 個 match
