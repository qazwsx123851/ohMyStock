## 1. 共用型別與常數

- [x] 1.1 在 `web-admin/src/lib/api.ts` 匯出 `OpenPosition` type，欄位涵蓋 `symbol` / `side: 'long' | 'short'` / `qty` / `entry_price` / `mark_price` / `unrealized_pnl_twd` / `unrealized_pnl_pct` / `stop_loss` / `t1_target` / `hold_days` / `time_stop_date` / `entry_reason` / `entry_at`
- [x] 1.2 在 `web-admin/src/lib/api.ts` 匯出 `JournalRow` type（最少 `id` / `kind` / `symbol?` / `decision_id?` / `created_at` / `payload` / `status`）
- [x] 1.3 在 `web-admin/src/lib/api.ts` 匯出 `PaginatedRows<T>` type（`items` / `total` / `limit` / `offset` / `has_more`）
- [x] 1.4 新檔 `web-admin/src/lib/journal-kinds.ts`，匯出 `JOURNAL_KIND_ENTRY_LIKE` / `JOURNAL_KIND_ALL` `as const` 陣列與 `JournalKind` type alias
- [x] 1.5 新檔 `web-admin/src/lib/journal-kinds.test.ts`，斷言 `JOURNAL_KIND_ENTRY_LIKE` 為 `['entry','fill','exit','reject']` 且為 `JOURNAL_KIND_ALL` 的子集
- [x] 1.6 commit 1：`feat(web-admin): JournalRow / OpenPosition / PaginatedRows types + journal-kinds constants`

## 2. DataTable 擴充：opt-in expandedRow / onRowClick

- [x] 2.1 在 `web-admin/src/components/data-table.tsx` props 介面新增 `onRowClick?: (row: T) => void` 與 `expandedRowRender?: (row: T, isExpanded: boolean) => ReactNode | null`
- [x] 2.2 內部新增 `expandedRowId` state（`Set<string | number>` 或單一 id）；只有當 `expandedRowRender` 與 `onRowClick` 同時提供時才啟用 toggle 行為
- [x] 2.3 點擊 row → 呼叫 `onRowClick(row)` + toggle expanded id；展開時下方多一列 `<tr><td colSpan={cols.length}>{expandedRowRender(row, true)}</td></tr>`
- [x] 2.4 既有 `data-table.test.tsx` 不修改即通過；新增 2 個 test：`onRowClick fires with row` 與 `expandedRowRender renders below clicked row`
- [x] 2.5 commit 2：`feat(web-admin): DataTable opt-in expandedRowRender / onRowClick`

## 3. `/paper/positions` 實作

- [x] 3.1 新檔 `web-admin/src/pages/PaperPositionsPage.tsx`：useQuery 拉 `/api/admin/positions/open`，`refetchInterval: 30_000`
- [x] 3.2 用 `<DataTable>` 列 10 欄（依 `docs/web-admin-page-designs.md` §9 順序）；P&L / P&L% 欄使用 `directionOf(value)` + `--up`/`--down` token + Lucide ArrowUp/ArrowDown；方向欄同樣處理
- [x] 3.3 selectedRowId state；點 row → 切換；下方 render `<Card>` detail panel（`entry_at` / `entry_reason` / 停損距離 / T1 距離 / `time_stop_date`）；若 selectedRowId 為 null 則不渲染 panel
- [x] 3.4 三態：loading 顯 5 列 Skeleton + panel Skeleton；empty 顯「目前無開倉」+ Lucide `ListOrdered`；error 顯 `--destructive` 區塊 + retry
- [x] 3.5 從 `web-admin/src/pages/stubs.tsx` 移除 `PaperPositionsPage` 的 export
- [x] 3.6 在 `web-admin/src/router.tsx` 將 `/paper/positions` 的 import 由 `./pages/stubs` 改為 `./pages/PaperPositionsPage`
- [x] 3.7 新檔 `web-admin/src/pages/__tests__/paper-positions-page.test.tsx`：mock `apiFetch`；4 個 test 涵蓋 loading / resolved（含紅漲綠跌雙重編碼 assert）/ empty / error
- [x] 3.8 `pnpm tsc --noEmit && pnpm test` 全綠
- [x] 3.9 commit 3：`feat(web-admin): PaperPositionsPage real implementation + tests`

## 4. `/paper/orders` 實作

- [x] 4.1 新檔 `web-admin/src/pages/PaperOrdersPage.tsx`：用 `useSearchParams` 讀 / 寫 filter（kind multi、symbol、date_from、date_to、page）；queryKey 含 search params 序列化
- [x] 4.2 Filter bar：依 `JOURNAL_KIND_ENTRY_LIKE` 渲染 4 個原生 `<input type="checkbox">`、symbol `<input>`、`<input type="date">` x2、「套用」/「清空」/「匯出本頁 N 列 CSV」按鈕
- [x] 4.3 Pending state（local React state）追使用者改動；按「套用」才寫回 URL；「清空」reset 至 default 並清 URL
- [x] 4.4 useQuery 對 `/api/admin/journal/rows?...` 拉資料；`limit=50`、`offset=(page-1)*50`；`keepPreviousData: true`；`refetchInterval: 60_000`
- [x] 4.5 `<DataTable>` 7 欄：時間 / Kind / Symbol / 方向 / Qty / Price / 狀態（`<StatusBadge>`）；`onRowClick` + `expandedRowRender` 顯示 row 完整 raw payload (JSON pretty `<pre>`)
- [x] 4.6 方向欄套色（`payload.side` 'long' → up + ArrowUp，'short' → down + ArrowDown）
- [x] 4.7 「匯出本頁 N 列 CSV」：當前 items → CSV blob → `URL.createObjectURL` 下載；header 行為 7 欄欄名
- [x] 4.8 三態：loading Skeleton 表格、empty「此 filter 無紀錄」+「清空 filter」、error retry
- [x] 4.9 從 `stubs.tsx` 移除 `PaperOrdersPage` export；router import 切換
- [x] 4.10 新檔 `paper-orders-page.test.tsx`：4 個三態 test + 1 filter→fetch query 對齊 test
- [x] 4.11 `pnpm tsc --noEmit && pnpm test` 全綠
- [x] 4.12 commit 4：`feat(web-admin): PaperOrdersPage real implementation + tests`

## 5. `/audit` 實作

- [x] 5.1 新檔 `web-admin/src/pages/AuditPage.tsx`：與 PaperOrdersPage 相同的 `useSearchParams` 模式；額外讀寫 `decision_id` 與 `density`
- [x] 5.2 Filter bar：依 `JOURNAL_KIND_ALL` 渲染 N 個 checkbox、symbol input、decision_id input、date range x2、套用 / 清空 / 「匯出本頁 N 列 JSONL」、density toggle button
- [x] 5.3 useQuery 對 `/api/admin/journal/rows?...&decision_id=...`；`limit=50`、`refetchInterval: 60_000`、`keepPreviousData: true`
- [x] 5.4 `<DataTable density={density}>` 6 欄：時間 / Kind / Symbol / Decision id / 狀態（`<StatusBadge>`） / 摘要（payload 取 1–2 關鍵欄位）；`expandedRowRender` 同 PaperOrdersPage
- [x] 5.5 分頁列右側顯示 `共 {Intl.NumberFormat('zh-TW').format(total)} 列`
- [x] 5.6 「匯出本頁 N 列 JSONL」：items 逐筆 `JSON.stringify` 用 `\n` 接 → blob 下載
- [x] 5.7 三態：與 PaperOrdersPage 相同
- [x] 5.8 從 `stubs.tsx` 移除 `AuditPage` export；router import 切換
- [x] 5.9 新檔 `audit-page.test.tsx`：4 個三態 + 1 個 filter→fetch query 對齊 test（含 decision_id）+ 1 個 density toggle test（共 6 test）
- [x] 5.10 `pnpm tsc --noEmit && pnpm test` 全綠
- [x] 5.11 commit 5：`feat(web-admin): AuditPage real implementation + tests`

## 6. 收尾

- [x] 6.1 全集 `pnpm tsc --noEmit && pnpm test && pnpm build` 全綠
- [ ] 6.2 啟動 `pnpm dev` 並在瀏覽器手動驗證三頁：
   - `/paper/positions`：empty / 有資料兩態
   - `/paper/orders`：filter 改 → 套用 → URL 變 → 結果變；CSV 下載
   - `/audit`：density toggle 切換生效；JSONL 下載
- [x] 6.3 `openspec validate --change web-admin-paper-and-audit-pages --strict` 通過（CLI 旗標：`openspec validate web-admin-paper-and-audit-pages --type change --strict`）
- [ ] 6.4 commit 6（archive）：執行 `/opsx:archive web-admin-paper-and-audit-pages` 由該 skill 處理 archive + delta sync + commit
- [ ] 6.5 `git push origin main`
