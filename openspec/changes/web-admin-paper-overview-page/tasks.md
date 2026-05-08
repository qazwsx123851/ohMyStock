## 1. 建立 PaperOverviewPage 骨架 + 路由切換

- [x] 1.1 新增 `web-admin/src/pages/PaperOverviewPage.tsx`，先放 page heading「模擬交易」+ 空白 4 區（KPI Row / 待確認 / 開倉摘要 / Live Feed）骨架；無資料 fetch、無 hotkey
- [x] 1.2 修改 `web-admin/src/router.tsx`：移除 `PaperPage` import、改 import `PaperOverviewPage`、把 `path: 'paper'` 的 element 換成 `<PaperOverviewPage />`
- [x] 1.3 修改 `web-admin/src/pages/stubs.tsx`：刪除 `PaperPage` export
- [x] 1.4 跑 `bun run typecheck` 全綠

## 2. KPI Row 接真資料

- [x] 2.1 在 `PaperOverviewPage.tsx` 裡寫三個 `useQuery`：
  - `['stats','today']` → `apiFetch('/api/admin/stats/today')`，回傳 type 在本檔 inline 定義（`PaperStatsToday`，不動 `web-admin/src/lib/api.ts` 的舊 `StatsToday`）
  - `['positions','open']` → `apiFetch('/api/admin/positions/open')`
  - `['confirm-gate','pending']` → `apiFetch('/api/admin/confirm-gate/pending')`
- [x] 2.2 渲染 4 張 `<KpiCard>`（「今日決策」/「持倉檔數」/「待確認」/「今日已成交」），值對應 §D1 mapping；`direction="neutral"`、`loading={isLoading}`
- [x] 2.3 任一 query error 時，對應卡顯示 `<AlertCircle/>` + zh-TW 錯誤訊息（沿用 DashboardPage `KpiRow` 的 error UI 樣式）
- [x] 2.4 跑 `bun run typecheck`、`bun run dev` 手測四卡顯示真實 counter

## 3. 待確認列表 slot

- [x] 3.1 `PendingList` sub-component：從 `useQuery(['confirm-gate','pending'])` 拉 items，map 為 `<Card>`；每張卡顯示 `symbol` / `current_price` / `final_sizing_pct` / 倒數進度條（`age_seconds`/`ttl_seconds`）
- [x] 3.2 每張卡含 `<Button>` 「✓ 確認」與「✗ 拒絕」；用 `useMutation` 呼叫 `apiFetch('/api/admin/confirm-gate/confirm', {method:'POST', body:JSON.stringify({decision_id, user:'mark'})})`、reject 同形（**spec amendment:** 後端 `RejectRequest` 要求 `reason: str (>=1 char)`，因此 reject body 增加 `reason: 'user_reject'` 預設值）
- [x] 3.3 mutation `onSettled` 觸發 §6 的 invalidate（覆蓋成功與失敗兩 path）
- [x] 3.4 empty state（items 為 0）顯示 zh-TW「目前無待確認」+ muted glyph
- [x] 3.5 卡 root 加 `tabIndex={0}` + `data-pending-card` + `data-decision-id`，hotkey 透過 `document.activeElement.closest('[data-pending-card]')` 解析

## 4. Sweep 過期按鈕 + Y/N + Cmd/Ctrl+Shift+E hotkey

- [x] 4.1 頁首 action row 加 `<Button>` 「全部 sweep 過期」；click 時 `if (!window.confirm("確定要 sweep 所有過期的待確認單？")) return;` 然後 `apiFetch('/api/admin/confirm-gate/sweep-expired', {method:'POST', body:'{}'})`
- [x] 4.2 PaperOverviewPage `useEffect` 掛 `window.addEventListener('keydown', handler)`，unmount 時 remove
- [x] 4.3 handler 邏輯：
  - 若 `event.target` matches `input, textarea, [contenteditable]` → return
  - `key.toLowerCase() === 'y'` && 無修飾鍵 && 有 focused pending card → trigger 該卡 confirm
  - `key.toLowerCase() === 'n'` && 同上 → trigger 該卡 reject
  - `(metaKey || ctrlKey) && shiftKey && key.toLowerCase() === 'e'` → trigger sweep（含 `window.confirm`）

## 5. 開倉摘要 mini DataTable

- [x] 5.1 `OpenPositionsMini` sub-component：從 `useQuery(['positions','open'])` 拉 items；用 `<DataTable>` 渲染 `items.slice(0, 5)`
- [x] 5.2 欄位：Symbol / 方向（恆顯示 `多`）/ Qty (`qty_lots`) / Entry (`entry_price`) / 停損 (`stop_loss`，null `—`) / 剩餘日（推導 `time_stop_date - today`，null `—`）
- [x] 5.3 `items.length > 5` 時加 `<Link to="/paper/positions">→ 詳細看 /paper/positions</Link>`；否則不顯示
- [x] 5.4 empty state 顯示 zh-TW「目前無開倉」+ muted glyph

## 6. Live Feed slot + SSE invalidate 整合

- [x] 6.1 `LiveFeed` 在 PaperOverviewPage root 一次 `useAdminEvents()`（`/paper` 路由下 Layout 與 DashboardPage 都不掛 SSE，由本頁獨佔訂閱）
- [x] 6.2 從 `useLiveFeedStore` 取 events、過濾 5 種 event_type、`.slice(0, 8)`、map 為 `<li>`（沿用 DashboardPage `LiveFeedRow` 樣式）
- [x] 6.3 在 PaperOverviewPage 寫 `useEffect`：subscribe `useLiveFeedStore`，當最新一筆 event_type 屬於 5 種之一 → `queryClient.invalidateQueries({queryKey:['stats','today']})` + `['positions','open']` + `['confirm-gate','pending']`
- [x] 6.4 empty state 顯示 zh-TW「等待事件中…」

## 7. Vitest 覆蓋（test 檔對齊 spec scenario）

- [x] 7.1 新增 `web-admin/src/pages/__tests__/paper-overview-page.test.tsx`，setup `QueryClient` + `MemoryRouter` + `useAuthStore.setState({token:'t'})` + `vi.spyOn(global, 'fetch')` 工廠
- [x] 7.2 測「路由掛載真實頁面」+「stubs.tsx 不再 export PaperPage」
- [x] 7.3 測 KPI Row 三 scenario：三 endpoint 成功 / stats 失敗其他成功 / 三 in-flight
- [x] 7.4 測待確認列表三 scenario：empty / 2 筆 / click 確認後 POST
- [x] 7.5 測 hotkey：focused 卡按 Y / input focused 按 Y / Cmd+Shift+E 觸發 sweep
- [x] 7.6 測 sweep 按鈕：confirm true / confirm false 兩 path
- [x] 7.7 測開倉摘要：0 / 3 / 7 筆三 scenario
- [x] 7.8 測 Live Feed：mixed 5 筆過濾 / empty / 12 筆截 8
- [x] 7.9 測 SSE invalidate：push awaiting_confirm 觸發三 refetch / push unrelated 不觸發

## 8. 收尾驗證

- [x] 8.1 `npm run typecheck` 全綠（bun 未安裝；`tsc -b --noEmit` 同等）
- [x] 8.2 `npm run test -- paper-overview-page --run` 全綠（21/21）
- [x] 8.3 `npm run test -- --run` 全部測試（dashboard / paper-orders / paper-positions / audit）全綠（75/75 across 9 files）
- [x] 8.4 `npm run build` 全綠
- [x] 8.5 `openspec validate --type change web-admin-paper-overview-page --strict` 全綠

## 9. Commit + push

- [x] 9.1 `git add` 三 source 檔（`PaperOverviewPage.tsx`、`router.tsx`、`stubs.tsx`）+ 1 test 檔 + 5 openspec 檔（`.openspec.yaml` / proposal / design / specs / tasks）
- [x] 9.2 commit `bde6ee4` — `feat(web-admin): PaperOverviewPage real implementation + tests`，body 列 7 個 wired endpoints + 5 SSE event_types + reject body amendment
- [x] 9.3 `git push origin main` 完成（`2e584f5..bde6ee4  main -> main`）
