# web-admin-paper-overview-page Specification

## Purpose
TBD - created by archiving change web-admin-paper-overview-page. Update Purpose after archive.

## Requirements

### Requirement: `/paper` 路由 SHALL 渲染 `PaperOverviewPage` 元件

`web-admin/src/router.tsx` 中 `path: 'paper'` 的 `element` SHALL 為 `<PaperOverviewPage />`，且該元件 SHALL 由 `web-admin/src/pages/PaperOverviewPage.tsx` 預設或具名 export 取得。`web-admin/src/pages/stubs.tsx` SHALL **不**再 export 名為 `PaperPage` 的元件。

#### Scenario: 路由掛載真實頁面
- **GIVEN** 已登入（valid Bearer token in `useAuthStore`）、`MemoryRouter` initial entry `/paper`、各 GET endpoint 均 mock 回空 200 envelope
- **WHEN** 渲染 `RouterProvider`
- **THEN** DOM 中 SHALL 出現由 `PaperOverviewPage.tsx` 帶入的 page heading（含字串 `"模擬交易"`）；SHALL **不**出現 `ComingSoon` stub 文字 `"建置中"`

#### Scenario: stubs.tsx 不再 export PaperPage
- **WHEN** import `web-admin/src/pages/stubs.tsx`
- **THEN** module exports SHALL **不**包含 key `PaperPage`

---

### Requirement: KPI Row SHALL 顯示四個 v0 backend 真實 counter

KPI Row SHALL 顯示 4 張 `<KpiCard>`，依序為「今日決策」、「持倉檔數」、「待確認」、「今日已成交」。資料來源 SHALL 為 `react-query` cache：
- 「今日決策」`stats/today.decisions_made`
- 「持倉檔數」`positions/open.count`
- 「待確認」`confirm-gate/pending.items.length`
- 「今日已成交」`stats/today.entries_filled`

每張 `<KpiCard>` SHALL 設 `direction='neutral'`（counter 類，不套紅綠 directional 色），`<KpiCard label>` 為 zh-TW 字串。

#### Scenario: 三 endpoint 都成功回傳 → 四卡顯示對應數字
- **GIVEN** `stats/today` 回 `{asof_date: "2026-05-08", decisions_made: 3, entries_pending: 1, entries_filled: 2, rejects: 0, expires: 0, auto_execute_audits: 0}`、`positions/open` 回 `{items: [...4 rows...], count: 4, asof_iso: "..."}`、`confirm-gate/pending` 回 `{items: [...2 rows...], timeout_minutes: 30}`
- **WHEN** 渲染 PaperOverviewPage
- **THEN** KPI Row 4 卡的 value 文字 SHALL 分別含 `"3"` / `"4"` / `"2"` / `"2"`

#### Scenario: 任一 endpoint 失敗 → 對應卡顯示 error 樣式，不影響其他卡
- **GIVEN** `stats/today` 回 500、其他兩個回 200
- **WHEN** 渲染 PaperOverviewPage
- **THEN** 「今日決策」與「今日已成交」兩卡 SHALL 顯示 `<AlertCircle/>` icon + zh-TW 錯誤訊息；「持倉檔數」與「待確認」兩卡 SHALL 顯示真實數字

#### Scenario: 三 endpoint 都 in-flight → 四卡顯示 skeleton
- **GIVEN** 三個 endpoint 都 pending
- **WHEN** 渲染 PaperOverviewPage
- **THEN** 4 張 `<KpiCard>` 皆 SHALL 帶 `loading=true` prop（`<Skeleton>` 取代 value）

---

### Requirement: 待確認列表 SHALL 渲染 `confirm-gate/pending.items` 並支援 confirm/reject hotkey

待確認列表 SHALL 為 `<Card>` 集合，每筆 item 一張。每張卡 SHALL 顯示 `symbol`、`current_price`、`final_sizing_pct`、`age_seconds` / `ttl_seconds` 倒數進度。每張卡 SHALL 含「✓ 確認」與「✗ 拒絕」兩個 `<Button>`，分別對應 `POST /api/admin/confirm-gate/confirm` 與 `POST /api/admin/confirm-gate/reject`。

Confirm body SHALL 為 `{decision_id: <該卡 decision_id>, user: "mark"}`。

Reject body SHALL 為 `{decision_id: <該卡 decision_id>, user: "mark", reason: "user_reject"}`，因後端 `RejectRequest` schema 要求 `reason` 為非空字串；前端固定送預設值 `"user_reject"`，未來如要在 UI 收集自訂 reason，再起獨立 change。

當卡或其 descendant 為 `document.activeElement` 時，全域 `keydown` listener SHALL：
- 收到 `Y` (case-insensitive，無修飾鍵) → 觸發該卡「確認」
- 收到 `N` (case-insensitive，無修飾鍵) → 觸發該卡「拒絕」

當 `event.target` 為 `<input>` / `<textarea>` / `[contenteditable]` 時，hotkey SHALL **不**觸發。

#### Scenario: 列表 0 筆 → empty state
- **GIVEN** `confirm-gate/pending` 回 `{items: [], timeout_minutes: 30}`
- **WHEN** 渲染 PaperOverviewPage
- **THEN** 待確認區 SHALL 顯示 zh-TW 文字 `"目前無待確認"` 與一個 muted glyph

#### Scenario: 列表 2 筆 → 渲染 2 張卡
- **GIVEN** `confirm-gate/pending` 回 `{items: [{decision_id: "d1", symbol: "2330", ...}, {decision_id: "d2", symbol: "2454", ...}], timeout_minutes: 30}`
- **WHEN** 渲染 PaperOverviewPage
- **THEN** 待確認區 SHALL 顯示 2 張 `<Card>`；DOM 中 SHALL 各能找到字串 `"2330"` 與 `"2454"`

#### Scenario: 點「✓ 確認」 → POST 對應 endpoint
- **GIVEN** 1 筆 pending row `decision_id="d1"` 已渲染
- **WHEN** 使用者 click 該卡「✓ 確認」按鈕
- **THEN** SHALL 對 `/api/admin/confirm-gate/confirm` 發 POST 一次，body JSON parse 後 SHALL 等於 `{decision_id: "d1", user: "mark"}`

#### Scenario: 點「✗ 拒絕」 → POST 對應 endpoint with reason
- **GIVEN** 1 筆 pending row `decision_id="d1"` 已渲染
- **WHEN** 使用者 click 該卡「✗ 拒絕」按鈕
- **THEN** SHALL 對 `/api/admin/confirm-gate/reject` 發 POST 一次，body JSON parse 後 SHALL 等於 `{decision_id: "d1", user: "mark", reason: "user_reject"}`

#### Scenario: focused 卡 + 按 `Y` → 等同點 confirm
- **GIVEN** 1 筆 pending row `decision_id="d1"` 已渲染、卡或其 descendant 為 `document.activeElement`、無 input focus
- **WHEN** 使用者按下 `Y`
- **THEN** SHALL 對 `/api/admin/confirm-gate/confirm` 發 POST 一次，body JSON 等於 `{decision_id: "d1", user: "mark"}`

#### Scenario: input focused 時按 `Y` → 不觸發 confirm
- **GIVEN** 1 筆 pending row 渲染、頁面內某 `<input>` 為 focused element
- **WHEN** 使用者按下 `Y`
- **THEN** SHALL **不**對 `/api/admin/confirm-gate/confirm` 發任何 request

---

### Requirement: 「全部 sweep 過期」按鈕 SHALL 跳確認後觸發 sweep endpoint

頁面 SHALL 含一個全頁按鈕「全部 sweep 過期」，並對應全域 hotkey `Cmd+Shift+E`（Mac）或 `Ctrl+Shift+E`（Win）。觸發後 SHALL 先呼叫 `window.confirm(...)`（zh-TW 警告文案）；使用者按 OK 才 SHALL 對 `POST /api/admin/confirm-gate/sweep-expired` 發 request，body 為空 JSON object `{}`。

#### Scenario: 點按鈕 → confirm 後送 request
- **WHEN** 使用者 click「全部 sweep 過期」、`window.confirm` 被 spy 為回 `true`
- **THEN** SHALL 對 `/api/admin/confirm-gate/sweep-expired` 發 POST 一次

#### Scenario: 點按鈕 → confirm 取消後不送 request
- **WHEN** 使用者 click「全部 sweep 過期」、`window.confirm` 被 spy 為回 `false`
- **THEN** SHALL **不**對任何 `/api/admin/confirm-gate/*` endpoint 發 request

#### Scenario: Cmd+Shift+E hotkey → 等同點按鈕
- **GIVEN** macOS 環境、無 input focused、`window.confirm` spy 回 `true`
- **WHEN** 使用者按下 `Cmd+Shift+E`
- **THEN** SHALL 對 `/api/admin/confirm-gate/sweep-expired` 發 POST 一次

---

### Requirement: 開倉摘要 SHALL 渲染 `positions/open.items` 前 5 列

開倉摘要區 SHALL 渲染 `<DataTable>`，欄位順序為：Symbol / 方向（恆 `多`）/ Qty（`qty_lots`）/ Entry（`entry_price`）/ 停損（`stop_loss`，null 顯示 `—`）/ 剩餘日（`hold_days`/`time_stop_date` 推導，null 顯示 `—`）。資料 SHALL 取 `items.slice(0, 5)`；當 `items.length > 5` 時 SHALL 顯示 zh-TW 文字 `"→ 詳細看 /paper/positions"` 連結（`<Link to="/paper/positions">`）。

#### Scenario: 0 筆 → empty state
- **GIVEN** `positions/open` 回 `{items: [], count: 0, asof_iso: "..."}`
- **WHEN** 渲染 PaperOverviewPage
- **THEN** 開倉摘要區 SHALL 顯示 zh-TW 文字 `"目前無開倉"`

#### Scenario: 3 筆 → 渲染 3 列、不顯示 overflow link
- **GIVEN** `positions/open` 回 `{items: [..3 rows..], count: 3, asof_iso: "..."}`
- **WHEN** 渲染 PaperOverviewPage
- **THEN** `<DataTable>` body SHALL 含 3 個 `<tr>`（不計 header）；DOM 中 SHALL **不**含 `"→ 詳細看 /paper/positions"`

#### Scenario: 7 筆 → 只渲染前 5 列、顯示 overflow link
- **GIVEN** `positions/open` 回 `{items: [..7 rows..], count: 7, asof_iso: "..."}`
- **WHEN** 渲染 PaperOverviewPage
- **THEN** `<DataTable>` body SHALL 含 5 個 `<tr>`；DOM 中 SHALL 含 anchor 文字 `"→ 詳細看 /paper/positions"`，`href` 結尾 SHALL 為 `"/paper/positions"`

---

### Requirement: Live Feed SHALL 過濾 SSE event 為 5 種 event_type

Live Feed slot SHALL 從 `useLiveFeedStore` 讀 events、過濾 `event_type ∈ {"awaiting_confirm", "order_sent", "decision_made", "journal_written", "risk_off_triggered"}`、取最近 8 筆。每筆 SHALL 顯示 `timestamp` (relative)、`event_type`、`payload.symbol`（缺則 `"—"`）。

#### Scenario: store 含 5 筆混合 event_type → 只渲染本頁關心的 3 筆
- **GIVEN** `useLiveFeedStore` 含 5 筆 events，event_type 分別為 `"awaiting_confirm"`、`"order_sent"`、`"foo_bar"`、`"baz_qux"`、`"journal_written"`
- **WHEN** 渲染 PaperOverviewPage
- **THEN** Live Feed `<ul>` SHALL 含 3 個 `<li>`，分別對應前述清單中的 `awaiting_confirm` / `order_sent` / `journal_written`

#### Scenario: store 為空 → empty state
- **GIVEN** `useLiveFeedStore` events 為 `[]`
- **WHEN** 渲染 PaperOverviewPage
- **THEN** Live Feed slot SHALL 顯示 zh-TW 文字 `"等待事件中…"`

#### Scenario: store 含 12 筆關心的 event → 只渲染前 8 筆
- **GIVEN** `useLiveFeedStore` events 含 12 筆 `event_type="awaiting_confirm"`
- **WHEN** 渲染 PaperOverviewPage
- **THEN** Live Feed `<ul>` SHALL 含 8 個 `<li>`

---

### Requirement: SSE event 推播 SHALL 觸發 react-query refetch

當 `useLiveFeedStore` 收到 event_type ∈ {`"awaiting_confirm"`, `"order_sent"`, `"decision_made"`, `"journal_written"`, `"risk_off_triggered"`} 任一者時，本頁 SHALL 呼叫 `queryClient.invalidateQueries`，對應 query key `['stats','today']`、`['positions','open']`、`['confirm-gate','pending']`。其他 event_type SHALL **不**觸發 invalidate。

#### Scenario: 推 awaiting_confirm → 三 query 全部 refetch
- **GIVEN** PaperOverviewPage 已渲染，三 query 已 settle 一次
- **WHEN** 透過 `useLiveFeedStore.getState().pushEvent(...)` 推一筆 `event_type="awaiting_confirm"` 的 LiveEvent
- **THEN** `stats/today` / `positions/open` / `confirm-gate/pending` 三個 endpoint SHALL 在 microtask flush 後各被多 fetch 至少一次

#### Scenario: 推 unrelated event → 不 refetch
- **GIVEN** PaperOverviewPage 已渲染、三 query 已成功且 `staleTime` 內
- **WHEN** push 一筆 `event_type="foo_bar"`（非 5 種之一）
- **THEN** 三 endpoint SHALL **不**被多 fetch（fetch 計數不變）
