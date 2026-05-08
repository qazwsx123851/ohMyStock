## 1. ui-ux-pro-max 設計 17 頁版型 SSOT

- [x] 1.1 收集每頁的 admin API endpoint 對應（讀 `openspec/specs/admin-read-endpoints/spec.md` + `openspec/specs/server-action-endpoints/spec.md` + `openspec/specs/eventbus-emitters/spec.md`），整理成「17 頁 × endpoint × event_type」對照表，做為 ui-ux-pro-max 的 input brief — 落地於 `research/endpoint-page-mapping.md`
- [x] 1.2 Invoke `ui-ux-pro-max` skill，brief 含：(a) 17 路由清單與每頁 1-2 行需求摘要，(b) 既有 token（`--up` / `--down` / `--destructive` / `--warning` + Inter / Noto Sans TC / Fira Code），(c) 約束（桌面 1366+、紅漲綠跌、color is never the only signal、shadcn primitive 風格），(d) 驗收準則（每頁含 ASCII wireframe + layout slots 表格 + interactions 條列 + loading/empty/error/SSE state 描述 + 紅漲綠跌示例 + 鍵盤可達性）
- [x] 1.3 把 ui-ux-pro-max 輸出整理為 `docs/web-admin-page-designs.md`：頂部前言（用途、SSOT 角色、與其他 docs 關係），17 個頁面區塊（依 router.tsx 順序），尾部「共用 patterns」（loading skeleton、empty state、error panel、SSE live region）
- [x] 1.4 驗收：對照 `web-admin/src/router.tsx` 17 個非 Dashboard 路由，確認 `docs/web-admin-page-designs.md` 每個都有獨立 section；每頁 section 都包含 `loading` / `empty` / `error` 狀態描述；訂閱 SSE 的頁面額外包含 `live-update` 區塊
- [x] 1.5 在 `CLAUDE.md` §5 SSOT 表格新增一列：`web-admin 18 頁面視覺契約（layout / state / interaction）` → `docs/web-admin-page-designs.md`

## 2. shadcn primitive 元件落地（5 個最小集合）

- [ ] 2.1 從 shadcn/ui 官方 GitHub 複製 `button.tsx` 到 `web-admin/src/components/ui/button.tsx`，檔頂 JSDoc 註明 source URL + commit hash；改 className helper 為 `cn`（from `@/lib/utils`）
- [ ] 2.2 重複 2.1 流程，落地 `card.tsx`、`skeleton.tsx`、`table.tsx`、`badge.tsx`（共 4 檔）
- [ ] 2.3 跑 `corepack pnpm typecheck` 確認 5 個 primitive 全部編譯過；跑 `corepack pnpm build` 確認 production bundle 能成功產生

## 3. Composite 元件 — `StatusBadge`（最簡 → 最先做）

- [ ] 3.1 建立 `web-admin/src/components/status-badge.tsx`：`status: 7 種` → 對應 Lucide icon（Clock / Check / X / CheckCircle / Hourglass / Ban / AlertCircle）+ shadcn `Badge` variant；errored 用 `--destructive` token
- [ ] 3.2 建立 `web-admin/src/components/__tests__/status-badge.test.tsx`：渲染 7 種狀態、檢查每個都有 SVG icon、檢查 errored 對應 `--destructive` token
- [ ] 3.3 跑 `corepack pnpm test status-badge` 確認 pass

## 4. Composite 元件 — `KpiCard`（含 Dashboard 同步遷移）

- [ ] 4.1 建立 `web-admin/src/components/kpi-card.tsx`：props `{ label, value, direction, glyph, loading }`；direction='up' → `--up` color + `<ArrowUp />`；direction='down' → `--down` color + `<ArrowDown />`；direction='neutral' / 未指定 → 無 glyph；loading → shadcn `Skeleton`
- [ ] 4.2 建立 `web-admin/src/components/__tests__/kpi-card.test.tsx`：up / down / neutral / loading 四種 case，斷言顏色 + glyph
- [ ] 4.3 重構 `web-admin/src/pages/DashboardPage.tsx`：把內聯 KPI 卡片改用 `<KpiCard>`；`今日損益` 依 sign 自動推 direction（>0 → up, <0 → down, ===0 → neutral）；其他 3 卡用 neutral
- [ ] 4.4 建立 `web-admin/src/pages/__tests__/dashboard-page.test.tsx`（若不存在）：mock `GET /api/admin/stats/today` 回 `realized_pnl_twd: 12345` → 斷言含 `+12,345` 的元素 computed color match `--up`；mock SSE 推 `confirm_gate.confirmed` → 斷言 LiveFeed 內出現對應 row
- [ ] 4.5 跑 `corepack pnpm test kpi-card dashboard-page` 確認 pass；同時跑全套 `corepack pnpm test` 確認既有 archive web-admin-shell scenario 不退步

## 5. Composite 元件 — `DataTable`

- [ ] 5.1 建立 `web-admin/src/components/data-table.tsx`：泛型 `<T>`，props 依 spec.md「DataTable composite 元件」requirement；底層用 shadcn `Table`，loading 用 `Skeleton`，empty/error 用 `Card` + 文案
- [ ] 5.2 實作分頁：`pageSize`、`page`、`total` → 渲染下一頁 / 上一頁按鈕（用 shadcn `Button`）+ `第 N / M 頁` 顯示；無 `total` 時隱藏分頁列
- [ ] 5.3 實作 column-sort：`sortable: true` 的欄位 header 可 click，state 為 component 內部 (`asc` → `desc` → `unsorted` 三循環)，emit 透過 `onSortChange?` callback（先預留 prop，本 change 不接外部 sort）
- [ ] 5.4 實作鍵盤可達性：每個 row 加 `tabIndex={0}` + Enter 觸發 `onRowClick`；sortable header 加 `aria-sort="ascending|descending|none"`
- [ ] 5.5 實作 density prop：`density="compact"` → row `min-height: var(--density-row-h-compact)`；預設 `comfortable`
- [ ] 5.6 建立 `web-admin/src/components/__tests__/data-table.test.tsx`：loading skeleton、empty message、row click（mouse + Enter）、sort 三循環 + `aria-sort` 值切換、compact density 高度、numeric `align="right"` 欄位有 `tabular-nums`
- [ ] 5.7 跑 `corepack pnpm test data-table` 確認 pass

## 6. Density token + index.css

- [ ] 6.1 在 `web-admin/src/index.css` `:root` 區塊新增：`--density-row-h: 36px;` 和 `--density-row-h-compact: 28px;`（光明 + 暗模式都需要，但值相同 → 只在 `:root` 加一次）

## 7. SSOT / 文件 / README 同步

- [ ] 7.1 更新 `web-admin/README.md`：新增「Components」章節，列出 ui/ 5 個 primitive + 3 個 composite；附「下一個 primitive 怎麼加」3 行流程說明（提到 FilterBar / ConfirmDialog / useSseStream 通用化是 deferred，等實際 per-page change 需要再做）
- [ ] 7.2 在 `docs/web-admin-page-designs.md` 文末加 cross-ref 區塊：指回 `frontend.md`、`backend-eventbus.md`、`auth-and-mask.md`，標明本檔為 SSOT、其他檔為延伸閱讀

## 8. End-to-end 驗收

- [ ] 8.1 跑 `corepack pnpm typecheck` 全綠
- [ ] 8.2 跑 `corepack pnpm test` 全綠（>= 3 個 component test + 1 個 dashboard-page smoke test）
- [ ] 8.3 跑 `corepack pnpm build` 全綠，確認 `web-admin/dist/` 產生
- [ ] 8.4 跑 `corepack pnpm dev` 在 `http://localhost:5173`，手動確認 Dashboard 視覺與 Phase 4 第一刀 ship 時相同（KPI 顏色、Live feed 推送、Sidebar/TopBar/footer 不變）
- [ ] 8.5 `openspec validate web-admin-design-system-and-page-wireframes --strict`，輸出無 error
