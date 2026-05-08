## Why

Phase 4 已 ship `web-admin-shell-and-auth` + `web-admin-design-system-and-page-wireframes`：18 路由、Bearer auth、設計語言 + 共用 composite (`DataTable` / `KpiCard` / `StatusBadge`)、17 頁版型契約 SSOT (`docs/web-admin-page-designs.md`) 全部到位。

接下來要把 17 個 `ComingSoon` stub 變真頁，但其中只有 4 頁的後端 endpoint 已 ship。本 change 挑出三頁 **完全 backend-ready、純 read-only、且共用同一組 composite** 的 stub 實作完成，作為「per-page change」這條軌道的第一刀：

- **`/paper/positions`** — `GET /api/admin/positions/open` ✅
- **`/paper/orders`** — `GET /api/admin/journal/rows` ✅
- **`/audit`** — `GET /api/admin/journal/rows` ✅

留下 `/paper` 首頁（含 KPI grid + 多塊 preview，較複雜）給後續一刀。Backend-blocked 的 chat / swarm / backtest / market/:symbol / skills / memory / sessions / settings 在對應 backend endpoint ship 之前不動。

## What Changes

### 1. `/paper/positions` page 實作
- 替換 `web-admin/src/pages/stubs.tsx` 內 `PaperPositionsPage`，改為新檔 `web-admin/src/pages/PaperPositionsPage.tsx`
- 對 `GET /api/admin/positions/open` 拉資料（`useQuery` + `apiFetch`，`refetchInterval: 30_000`）
- 用 `<DataTable>` 顯示 10 欄：Symbol / 方向 / Qty / Entry / 現價 / 未實現 P&L / P&L% / 停損 / T1 / 持倉
- 紅漲綠跌雙重編碼：方向欄與「未實現 P&L」欄套 `--up`/`--down` token + `<ArrowUp>`/`<ArrowDown>`
- 選定列下方 `<Card>` detail panel（進場時間、進場理由、停損距離 / T1 距離 / `time_stop_date`）
- loading / empty / error 三態套 page-designs.md §共用 patterns

### 2. `/paper/orders` page 實作
- 替換 `PaperOrdersPage` stub，新檔 `web-admin/src/pages/PaperOrdersPage.tsx`
- Filter bar：kind multi-checkbox（entry / fill / exit / reject）、symbol input、date range from/to、套用 / 清空 / 匯出 CSV
- 用 `<DataTable>` 顯示 7 欄：時間 / Kind / Symbol / 方向 / Qty / Price / 狀態（`<StatusBadge>`）
- 對 `GET /api/admin/journal/rows?kind=...&symbol=...&date_from=...&date_to=...&limit=...&offset=...` 拉資料；分頁透過 `<DataTable>` 內建
- 「匯出 CSV」：把當前 filter 結果（限當前 page 50 列為上限，不重新打 API） client-side 轉 CSV blob download
- detail drawer (per-page change 加 — 留 future)：本 change 只提供 row click → 內聯展開該 row 的全部 raw payload (JSON pretty)

### 3. `/audit` page 實作
- 替換 `AuditPage` stub，新檔 `web-admin/src/pages/AuditPage.tsx`
- Filter bar：kind multi-checkbox（全部 11 種 kind）、symbol input、decision_id input、date range、套用 / 清空 / 匯出 JSONL、density toggle (`comfortable` / `compact`)
- `<DataTable density="compact">` 顯示 6 欄：時間 / Kind / Symbol / Decision id / 狀態（`<StatusBadge>`） / 摘要（payload 取 1–2 關鍵欄位）
- 「共 N 列」總數顯示在分頁列右側（讀 envelope `total`）
- 「匯出 JSONL」：當前 page 結果 client-side 轉 JSONL blob download
- 本 change **不**處理 `risk_off_triggered` banner 與 SSE live-update（留 future per-page change，避免本刀範圍擴散）

### 4. Vitest 覆蓋
- 每頁一份測試檔（`pages/__tests__/paper-positions-page.test.tsx` 等三份）
- 沿用 `dashboard-page.test.tsx` 模式：mock `apiFetch`、render 後 assert loading skeleton → resolved data → 紅漲綠跌 token 與 icon 同步出現 → empty / error 三態
- Filter bar 測試：改 filter → 「套用」按 → assert `apiFetch` 被以正確 query string 呼叫一次

### 不在範圍（deferred）
- `/paper` 首頁（KpiCard grid + open positions preview + recent orders preview）— 留下一刀
- Drawer 元件（`/paper/orders` 的 decision chain drawer、`/audit` 的 decision chain drawer）— per-page change 第一輪不需要
- SSE live-update（`journal_written` prepend、`order_sent` add/remove、`risk_off_triggered` banner）— per-page change 第二輪
- shadcn `Drawer` / `Sheet` / `Checkbox` / `Popover` / `Calendar` / `Command` 等 primitive — 本 change 用最小裝法：原生 `<input type="checkbox">` 與 `<input type="date">`，避免一次裝太多 primitive
- 後端 API 變更 — 完全不動

## Capabilities

### New Capabilities
- `web-admin-paper-and-audit-pages`：三個 read-only 頁面（`/paper/positions`、`/paper/orders`、`/audit`）的資料取得契約、filter / 分頁 / 排序行為、紅漲綠跌套用、loading / empty / error 三態、匯出格式（CSV / JSONL）契約

### Modified Capabilities
（無）`web-admin-shell` 與 `web-admin-design-system` 既有 requirement 不修改；本 change 沿用 `apiFetch`、`<DataTable>`、`<StatusBadge>`、density tokens、紅漲綠跌 tokens 既有契約。

## Impact

### Affected code
- `web-admin/src/pages/stubs.tsx` — 移除 `PaperPositionsPage`、`PaperOrdersPage`、`AuditPage` 三個 export
- `web-admin/src/pages/PaperPositionsPage.tsx`（新）
- `web-admin/src/pages/PaperOrdersPage.tsx`（新）
- `web-admin/src/pages/AuditPage.tsx`（新）
- `web-admin/src/router.tsx` — 改 import 來源（從 `./pages/stubs` 改為各自檔）
- `web-admin/src/lib/api.ts` — 補 `JournalRow`、`OpenPosition`、`PaginatedRows<T>` 型別
- `web-admin/src/pages/__tests__/paper-positions-page.test.tsx`、`paper-orders-page.test.tsx`、`audit-page.test.tsx`（新）

### Affected docs
- 無新增 SSOT。本 change 是 `docs/web-admin-page-designs.md` §8 / §9 / §17 的「實作」，contract 已存在於該檔。
- `CLAUDE.md` §5 不需變更（page-designs.md 仍是 SSOT）。

### Dependencies
- 不新增 npm package。

### Risk
- 後端 `journal/rows` `kind` 列舉值與前端 filter checkbox 必須對齊（spec 列：entry / fill / exit / reject + decision_made / awaiting_confirm / decider_thinking / risk_off_triggered / breaker_tripped 等）。本 change 在 design.md 列出採用的 kind 集合並驗收對齊。
- 「匯出 CSV / JSONL」只匯出當前 page（≤ 500 列）的決策避免把後端打爆；如果使用者期望「匯出全部」則為 future change。design.md 明確標示此限制。
- 三頁同步落地，diff 較大；本 change 強制每頁一個 commit，方便事後追溯。
