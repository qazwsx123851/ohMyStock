## Context

`/paper` 是 admin 18 頁中**唯一**所有後端依賴都已上線的頁面，但目前仍是 stub。本 change 把它接上既有四個 read endpoints + SSE 串流 + 三個 confirm-gate action endpoints，把「Mark 早盤第一站」實裝為純 frontend 工作。

**既有可重用元件（`web-admin-design-system-and-page-wireframes` archive 落地）：**
- `@/components/kpi-card` — `KpiCard` + `directionOf` helper
- `@/components/status-badge` — 7 狀態 (`pending` / `approved` / `rejected` / `executed` / `expired` / `canceled` / `errored`)
- `@/components/data-table` — 分頁/排序/density
- `@/hooks/useAdminEvents` — SSE 訂閱（含 `[1s, 2s, 4s, 8s, 30s]` backoff、401 abort、push 進 `useLiveFeedStore`）
- `@/lib/api` — `apiFetch<T>`、`openSSE`、`ApiError`
- `@/stores` — `useAuthStore`、`useLiveFeedStore`

**既有後端 endpoints（已驗證 + spec'd）：**
- `GET /api/admin/stats/today` → `{asof_date, decisions_made, entries_pending, entries_filled, rejects, expires, auto_execute_audits}`
- `GET /api/admin/positions/open` → `{items: [...], count, asof_iso}`
- `GET /api/admin/confirm-gate/pending` → `{items: [...], timeout_minutes}`
- `POST /api/admin/confirm-gate/{confirm,reject,sweep-expired}`
- SSE `GET /api/admin/events`（已有 9 種 event_type wired）

## Goals / Non-Goals

**Goals:**
- `/paper` 路由顯示 KPI Row + 待確認列表 + 開倉摘要 + Live Feed 四 slot 真實資料。
- 待確認卡的 `Y` / `N` hotkey 與 `Cmd/Ctrl+Shift+E` sweep 可用。
- SSE event 推播時 KPI Row 數字 + 待確認列表 + Live Feed 即時更新（無需 reload）。
- Vitest 覆蓋四 slot 的 loading / empty / error / SSE update。

**Non-Goals:**
- **不**新增任何 backend endpoint。P&L / LLM cost 等 v0 backend 不提供的數字在 KPI Row 標 `n/a`，補後端是後續 change。
- **不**修復 `DashboardPage` 對 `stats/today` 欄位名假設（`realized_pnl_twd` / `open_positions` / `pending_confirms` / `llm_cost_usd` 與後端實際 schema 不符）— 這是預先存在 bug，由獨立 change 處理。
- **不**改 `useAdminEvents` 或 `useLiveFeedStore`（已能滿足需求）。
- **不**做「快速下單」（design SSOT §7 只列為 future endpoint，本 change 不含）。
- **不**抽 `FilterBar` / `ConfirmDialog` 共用 composite（design SSOT §0.4 列為 future）— sweep 用原生 `window.confirm`。

## Decisions

### D1. KPI Row 四卡映射 — 用「決策數 / 開倉數 / 待確認 / 今日成交」取代 design §7 原列「P&L / 開倉 / 待確認 / LLM 成本」

**選項：**
- (a) 照 design §7 原文渲染，但 P&L 與 LLM cost 顯示 `NaN` / `0`（沿用 DashboardPage 現狀的 silent break）。
- (b) **採用** — 改成四個 v0 backend **真的**會回的 counter：`decisions_made` / `positions/open.count` / `entries_pending` / `entries_filled`，標 zh-TW label「今日決策」「持倉檔數」「待確認」「今日已成交」。
- (c) 只放 3 卡（去掉一個），等 backend 補欄位。

**選 (b) 的理由：** 個人專案 + solo dev，四卡都顯示真實 counter > 兩卡有意義兩卡假數字。日後 backend 補 `realized_pnl_twd` / `today_llm_cost_usd` 後，再加一輪 spec change 替換對應卡。

### D2. KPI Row 資料 source —「待確認」與「開倉檔數」用 list endpoint 的 count，而非 stats endpoint

**選項：**
- (a) 全四卡都讀 stats/today。
- (b) **採用** — KPI Row 同時 fetch `stats/today` + `positions/open` + `confirm-gate/pending`，待確認用 `confirm-gate/pending.items.length`、開倉用 `positions/open.count`。
- (c) 只讀 stats/today + 把 list 留給其他 slot。

**選 (b) 的理由：** 待確認列表 slot 一定要 fetch `confirm-gate/pending`（否則沒資料畫卡）；開倉摘要 slot 一定要 fetch `positions/open`。共用 react-query cache key 後 KPI Row 直接從同一份資料 derive 數字，不增加 request 數，且**保證 KPI 數字與下方列表零延遲一致**（避免 stats/today 與 list 短暫脫節，造成「KPI 顯示 2 但卡只有 1 張」的視覺 bug）。

### D3. SSE live-update 路徑 — 既有 `useAdminEvents` push 進 `useLiveFeedStore`，本頁額外用 react-query cache invalidate 觸發 KPI / 列表 refetch

**選項：**
- (a) 收到 SSE event 直接 mutate react-query cache（樂觀更新）。
- (b) **採用** — 收到 5 種事件之一 → `queryClient.invalidateQueries(['stats','today'])` + `['positions','open']` + `['confirm-gate','pending']` 重抓。
- (c) 完全 push-based，不 fetch。

**選 (b) 的理由：** event payload 不一定含完整 row（例如 `awaiting_confirm` payload 只有 `symbol / timeout_at / expected_price`，沒 `decision_id` / `final_sizing_pct`），如果樂觀更新會漏欄位。Invalidate + 重抓最簡單、最不會錯。三個 endpoint 都很輕（單 SQL aggregate / 單 join），refetch 成本低。

### D4. 鍵盤捷徑實作 — 全域 keydown listener 僅在 `<input>/<textarea>` 不 focused 且本頁掛載時生效

**選項：**
- (a) 用 react-hotkeys-hook 之類 library。
- (b) **採用** — Page 在 mount 時掛 `window.addEventListener('keydown', ...)`，unmount 時 remove。判 `event.target` 是否為 form element + 是否 `event.metaKey/ctrlKey/shiftKey` 組合。
- (c) 不做 hotkey，全靠按鈕點擊。

**選 (b) 的理由：** 一個檔內 ~20 行純 React effect，不引新依賴。design SSOT §0.4 也未把 hotkey lib 列為 shared。

### D5. 「全部 sweep 過期」確認 dialog — 用 `window.confirm` 而非 shadcn Dialog

**選項：**
- (a) 引入 shadcn Dialog（design SSOT §0.4 列為「future composite」）。
- (b) **採用** — 用 `window.confirm("確定要 sweep 所有過期的待確認單？")`，按 OK 才打 POST。
- (c) inline 二段確認（先 highlight，再點一次）。

**選 (b) 的理由：** Sweep 是 destructive action，要「明確的 yes/no 阻塞」，原生 confirm 對 solo dev 場景**夠用**且可 keyboard-accessible。design SSOT §0.4 已明文允許 future composite 之前用原生 confirm fallback。

## Risks / Trade-offs

- **DashboardPage 與 stats/today 欄位名 mismatch 持續存在** → Mitigation：本 change 不碰 DashboardPage，但在 design.md / proposal 顯式 note，留 follow-up change 修正（重命名 `StatsToday` 型別 + 改 DashboardPage KPI mapping）。
- **`stats/today` + `positions/open` + `confirm-gate/pending` 三 fetch 並發，任一失敗 → 對應 slot 顯示 retry card** → Mitigation：每個 slot 自己一個 `useQuery`，失敗只影響自己；KPI Row 任一卡 fail 顯灰底 + `<AlertCircle/>` 對齊既有 Dashboard 行為。
- **SSE invalidate 風暴**：若 5 種事件每秒多次推 → react-query 會合併 in-flight refetch，但極端高頻仍可能造成 spam → Mitigation：用 `queryClient.invalidateQueries` 而非 `refetchQueries` 讓 react-query 自動合併；如後續觀察到問題，加 200ms debounce（本 change 不預先做）。
- **「Y / N」hotkey 與待確認卡 focused 狀態判定**：若多張卡同時顯示，Y/N 應作用於哪張？ → 採 design SSOT §7 原方案：focused 卡（`document.activeElement` 為該卡或其 descendant）才生效，否則 hotkey 無作用；Tab 鍵在卡之間切換。
- **`useLiveFeedStore` 在 DashboardPage 也會 push** → 兩頁同時開（理論上 SPA 內只一頁掛載）不會衝突；本頁直接 read store，不獨立另開 SSE。

## Migration Plan

1. 新增 `web-admin/src/pages/PaperOverviewPage.tsx`。
2. 修改 `web-admin/src/router.tsx`：把 `path: 'paper'` 的 element 從 `<PaperPage />` 換成 `<PaperOverviewPage />`，並調整 import。
3. 修改 `web-admin/src/pages/stubs.tsx`：移除 `PaperPage` export（避免 dead code）。
4. 新增 `web-admin/src/pages/__tests__/paper-overview-page.test.tsx`。
5. `bun run typecheck` + `bun run test` + `bun run build` 全綠。
6. 直接 push 到 main（per user memory：solo dev 不開 PR）。

**Rollback：** revert single commit；無 schema migration / 無新 endpoint，沒有狀態殘留風險。

## Open Questions

無（fields 限制與 fallback 已在 D1 / D2 拍板）。
