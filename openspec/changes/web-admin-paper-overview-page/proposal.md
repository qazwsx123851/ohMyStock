## Why

`/paper` 是 `docs/web-admin-page-designs.md` §7 標示為 Mark「每日早盤第一站」的核心看板，但目前仍是 `ComingSoon` stub。這是 18 頁中**唯一一個**所有依賴後端端點都已上線（`stats/today`、`positions/open`、`confirm-gate/pending` + 5 種 SSE event_type）、不需要任何 backend 新增就能落地的頁面。先把這頁實裝完，`/paper` 三件組（overview + orders + positions）就完整收尾，後續再依序處理需要新後端的批次（settings / skills / market / chat / swarm / backtest）。

## What Changes

- 把 `web-admin/src/pages/stubs.tsx` 的 `PaperPage` 改寫為 `web-admin/src/pages/PaperOverviewPage.tsx` 真實實作；router 切換到新檔案，stub 移除。
- 頁面四個 slot 全部接真資料：
  - **KPI Row** 4 卡（今日 P&L / 開倉數 / 待確認 / 今日 LLM 成本）讀 `GET /api/admin/stats/today`。注意：v0 `stats/today` envelope 欄位為 `decisions_made / entries_pending / entries_filled / rejects / expires / auto_execute_audits`，**未含** `realized_pnl_twd` / `today_llm_cost_usd`；本 change KPI Row 以「待確認」「開倉數」「今日決策數」「今日 fills」四個 derive-able 數字實作，P&L 與 LLM 成本卡標 `n/a` 並引註 future endpoint。
  - **待確認列表** 讀 `GET /api/admin/confirm-gate/pending`，每張卡支援 `POST /confirm-gate/confirm` / `POST /confirm-gate/reject` 與全頁 `POST /confirm-gate/sweep-expired`。
  - **開倉摘要 mini DataTable** 讀 `GET /api/admin/positions/open`，僅顯示前 5 列、提供「→ 詳細看 /paper/positions」連結。
  - **Live Feed**（最近 8 筆）訂閱既有 SSE 串流 `/api/admin/events`，過濾 5 種 event_type：`awaiting_confirm` / `order_sent` / `decision_made` / `journal_written` / `risk_off_triggered`。
- SSE live-update 行為：`awaiting_confirm` → 待確認區頂部插卡 + 啟動倒數；`order_sent` → 對應卡 fade out；KPI Row 對應數字直接更新；Live Feed 頂部插列並 0.5s 黃底 flash。
- 鍵盤捷徑：focused 待確認卡 `Y` 確認、`N` 拒絕；全域 `Cmd/Ctrl+Shift+E` 觸發 sweep（含確認 dialog）。
- Vitest 測試覆蓋四 slot 的 loading / empty / error，加上 SSE live-update 的卡片插入 / 移除與 KPI 更新行為。

## Capabilities

### New Capabilities
- `web-admin-paper-overview-page`: `/paper` 頁面（overview）的視覺、互動、狀態契約 — KPI Row、待確認列表、開倉摘要、Live Feed 四 slot；資料來源、SSE 訂閱、鍵盤可達性與 loading/empty/error 行為。

### Modified Capabilities
（無）

## Impact

- **Frontend (web-admin/)**
  - 新增 `web-admin/src/pages/PaperOverviewPage.tsx`
  - 修改 `web-admin/src/router.tsx`：`<PaperPage />` → `<PaperOverviewPage />`
  - 修改 `web-admin/src/pages/stubs.tsx`：移除 `PaperPage` export
  - 新增 `web-admin/src/pages/__tests__/paper-overview-page.test.tsx`
- **Backend**：無變動（純消費既有端點）
- **Docs**：archive 後 `CLAUDE.md` §5 補一列 paper-overview SSOT 指向 spec + page tsx；`docs/web-admin-page-designs.md` §7 不變（本 change 即按該節實作）。
- **Dependencies**：無新增 npm package（沿用 react-router、shadcn/ui、lucide-react、既有 `KpiCard` / `StatusBadge` / `DataTable` 與 `useAdminEvents` SSE hook）。
