## Context

`web-admin-shell-and-auth` 提供路由 + Bearer auth + Dashboard 真頁；`web-admin-design-system-and-page-wireframes` 提供 `<DataTable>`、`<KpiCard>`、`<StatusBadge>` 三個 composite，以及 `docs/web-admin-page-designs.md` 17 頁版型契約 SSOT。

本 change 是 page-implementation 軌道的 **第一刀**，目標是把三個「全 backend-ready、純 read-only、共用 composite」的 stub 落地。後端 endpoint 規格固定於 `openspec/specs/admin-read-endpoints/spec.md`：

- `GET /api/admin/journal/rows` 接受 `kind`、`symbol`、`decision_id`、`date_from`、`date_to`、`limit`、`offset`，回 `{items, total, limit, offset, has_more}` envelope；`limit` 最大 500，`limit=0` 為 400；`date_from > date_to` 為 400。
- `GET /api/admin/positions/open` 回 array；row 含 `symbol`、`side`、`qty`、`entry_price`、`mark_price`、`unrealized_pnl_twd`、`unrealized_pnl_pct`、`stop_loss`、`t1_target`、`hold_days`、`time_stop_date`、`entry_reason`、`entry_at`。
- 401 → `apiFetch` 自動 logout；錯誤 envelope 不洩 SQL / 路徑 / token（後端已驗）。

Dashboard 既有 pattern：`useQuery({queryKey, queryFn: () => apiFetch<T>(path), refetchInterval})`、紅漲綠跌套 `directionOf(value)` + Lucide arrow + `--up`/`--down` token。

## Goals / Non-Goals

**Goals:**
- 三頁 stub 替換為真實實作，純讀後端 + composite，不引入新 primitive 也不新增 npm package
- 每頁有 vitest 覆蓋三態（loading / empty / error）+ 紅漲綠跌雙重編碼 + filter→fetch query 對齊
- 共用 `JournalRow` / `OpenPosition` / `PaginatedRows<T>` 型別寫進 `lib/api.ts`，後續 page change 可重用
- 每頁一個 commit，方便事後追溯

**Non-Goals:**
- `/paper` 首頁（KPI grid + previews） — 留下一刀
- SSE live-update（`journal_written`、`order_sent`、`risk_off_triggered`） — 留下一刀
- Decision-chain detail drawer — 留下一刀
- 安裝任何新 shadcn primitive（`Drawer` / `Sheet` / `Checkbox` / `Popover` / `Calendar` / `Command`）
- 後端 schema 變更
- 「匯出全部」（>500 列分批拉）— 本刀只匯出當前 page

## Decisions

### D1. Filter state 用 URL query string，不用 React state
**選擇：** Filter 狀態（`kind`、`symbol`、`date_from`、`date_to`、`page`）綁進 `useSearchParams`，不存 React local state。

**Why：**
- 重新整理或分享 URL 即可重現視圖（個人專案最常見「想拿給自己另一台電腦看」）。
- `useSearchParams` 是 react-router v7 既有 API，不增依賴。
- TanStack Query `queryKey` 直接吃 search params 序列化字串，重渲染穩定。

**Alternatives considered:**
- React `useState` + 表單按「套用」才同步 URL — 多一層狀態，每頁都要重複；本刀 KISS 拒絕。
- Zustand store — 跨頁共用反而成負擔（每頁 filter 語意不同）。

### D2. Kind 列舉源頭：spec 定義為單一來源，前端 import 為常數
**選擇：** 前端 `web-admin/src/lib/journal-kinds.ts` 新增常數 `JOURNAL_KIND_ENTRY_LIKE`（`/paper/orders` 用：`['entry', 'fill', 'exit', 'reject']`）與 `JOURNAL_KIND_ALL`（`/audit` 用：完整 11 種，含 `decision_made` / `awaiting_confirm` / `decider_thinking` / `risk_off_triggered` / `breaker_tripped` / `confirm_received` / `confirm_rejected`）。

**Why：**
- Filter checkbox UI 需要硬編碼選項列表，與後端 spec 拆開維護就會 drift。
- 把列舉集中於一個 `journal-kinds.ts`，後端 spec 變更時前端 grep 一下就可定位。
- vitest 測試 assert filter checkbox 渲染數量 = 列舉長度，drift 立即被測出。

**Alternatives considered:**
- 從後端 OpenAPI 自動 codegen — 個人專案沒有 OpenAPI pipeline，YAGNI。

### D3. 分頁採後端 cursor (`limit` + `offset`)，不用 client-side
**選擇：** `<DataTable>` 內建 pagination state → query string `page` → `offset = (page-1) * limit`；`limit` 預設 50（`/paper/orders`、`/audit`）；`/audit` 額外提供 `pageSize` 100（compact density 適合）。

**Why：**
- `journal/rows` 後端 `limit` 上限 500、`has_more` 已在 envelope；client-side 只能拖一兩 page 量級。
- 解決 `/audit` 8000+ 列的真實規模問題。

**Alternatives considered:**
- 抓 500 列再 client-side filter/page — `/audit` 全表幾萬列直接破表。

### D4. 匯出 CSV / JSONL 限「當前 page」
**選擇：** 「匯出 CSV」（`/paper/orders`）、「匯出 JSONL」（`/audit`）只匯當前 page 的 ≤500 列，不背景拉全集。Filter bar 上的按鈕 tooltip 明確標：「匯出當前 N 列」。

**Why：**
- 避免在 single-user 個人專案上做 streaming / progress UI；複雜度 / 收益不值得。
- 真要匯出全部 → 開 sqlite client 直接查 journal 即可（這是 solo dev 個人專案，不是 SaaS）。

**Alternatives considered:**
- 背景分批 fetch + progress bar — 過度工程。
- 直接 disable，讓使用者用 sqlite — 但 happy path 「拿目前看的列導出」是合理需求，所以保留 page-only 版本。

### D5. Row 點擊 → 內聯展開 raw payload（不引 Drawer）
**選擇：** `/paper/orders` 與 `/audit` 點 row → 該 row 下方插一行 colspan-full 的 `<details><summary>` JSON pretty 顯示（`payload`、`decision_id`、原始 `created_at`、`status`）。`<DataTable>` 透過新 prop `expandedRowRender?: (row: T) => ReactNode` 支援。

**Why：**
- 不用裝 `Drawer` / `Sheet` primitive。
- `<details>` 鍵盤可達（Tab + Space）+ 螢幕報讀器原生支援。
- per-page change 第二輪要做 decision chain drawer 時，把 expanded row 換成 button → 開 drawer 即可，介面相容。

**Alternatives considered:**
- 直接裝 shadcn `Drawer` — 新 primitive，本 change 範圍擴散。
- 跳轉到 `/audit/:journalId` 詳細頁 — 增加路由與後端負擔。

### D6. 紅漲綠跌套用範圍：方向 + P&L + P&L%；其餘不套色
**選擇：** 三頁的「方向」欄一律 `--up`/`--down` + `<ArrowUp>`/`<ArrowDown>`；`/paper/positions` 「未實現 P&L」與「P&L%」欄套色；`stop_loss`、`t1_target`、`time_stop_date`、`entry_price`、`mark_price` 不套色（純技術價）。`/audit` 狀態欄純用 `<StatusBadge>`，不套漲跌色（kind 與漲跌語意無關）。

**Why：**
- page-designs.md §0.3「鐵律：任何時候用 color 表達語意，必須同時放 Lucide icon」。
- 「停損 / T1」是技術價非「方向變化」，不套色避免認知干擾。

**Alternatives considered:**
- `stop_loss` 用警告色 — 但 stop_loss 是被動參數不是事件，套色會誤導。

### D7. `<DataTable>` 未變動原則
**選擇：** 不改 `data-table.tsx` 既有 API；本 change 只新增可選 prop `expandedRowRender?: (row: T, isExpanded: boolean) => ReactNode | null` 與 `onRowClick?: (row: T) => void`，且**預設關閉**（既有測試不破）。

**Why：**
- design-system change 已封凍 DataTable 行為；新增 prop 為 backward-compatible 擴充。
- 三頁實作驗證後若有共通需求，下一刀再合併進 DataTable 主 API。

**Alternatives considered:**
- 三頁各自包一層 `<ExpandableTable>` wrapper — 三份重複程式碼。

## Risks / Trade-offs

- **[Risk] Journal kind 列舉 drift**：後端 spec 加新 kind 但前端 `journal-kinds.ts` 沒同步 → 新 kind 落 row 時 `<StatusBadge>` 不認得。
  → **Mitigation**：`<StatusBadge>` 對未知 kind 回退到中性 `outline` variant；vitest 加一筆 unknown-kind row 測試確保不爆。

- **[Risk] `/audit` 8000+ 列 first-paint 慢**：DataTable 一次渲 50 列已 ok，但 compact density 想到 100 列可能感覺到慢。
  → **Mitigation**：`refetchInterval` 設 60_000（read-heavy 頁，30s 太頻），且 `keepPreviousData: true` 讓翻頁不閃白。

- **[Risk] CSV / JSONL「只匯當前 page」誤導**：使用者以為按下去匯出全部。
  → **Mitigation**：按鈕文案直接寫「匯出本頁 N 列 (CSV/JSONL)」；hover tooltip 補「需要全部？查 sqlite journal_entries」。

- **[Trade-off] `<details>` 內聯展開 vs 真 Drawer**：`<details>` 在表格內部 colspan 渲染會破壞 row 高度均勻性。
  → 接受：個人專案桌面寬度足夠，視覺 jitter 可接受；下一刀 drawer 會解。

- **[Trade-off] Filter URL 序列化方案**：用 URL query string 帶 multi-checkbox 需要重複 key (`?kind=entry&kind=fill`)；fetch URL 與 router URL 用同一格式。
  → 接受：FastAPI 預設能解 multi-key；前後端格式對齊不需轉換。

## Migration Plan

1. Branch 直接走 `main`（solo dev 偏好），但每頁一個 commit：
   - commit 1：`feat(web-admin): JournalRow / OpenPosition / PaginatedRows types + journal-kinds constants`
   - commit 2：`feat(web-admin): PaperPositionsPage real implementation + tests`
   - commit 3：`feat(web-admin): PaperOrdersPage real implementation + tests`
   - commit 4：`feat(web-admin): AuditPage real implementation + tests`
   - commit 5：`feat(web-admin): DataTable expandedRowRender / onRowClick opt-in props`
   - commit 6：`docs(openspec): archive web-admin-paper-and-audit-pages and sync delta spec`
2. 每 commit 通過 `pnpm test` + `pnpm tsc --noEmit` 才推；不開 PR（per CLAUDE.md memory「直接 push main」）。
3. Rollback：單 commit `git revert` 即可；無資料層遷移。

## Open Questions

- 無。`docs/web-admin-page-designs.md` §8 / §9 / §17 已把每頁的 layout slots、互動、a11y、紅漲綠跌套用範例寫死，本 change 是該文件 implementation 化的直接落地。
