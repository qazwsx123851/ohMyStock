## Why

Phase 4 第一刀（`web-admin-shell-and-auth`）已 ship：shell + Bearer auth + Dashboard + 17 頁 stub。下一步是把 17 頁 stub 變真實頁。

如果直接平行 17 個 agents 去寫各自的頁面，會出兩種失敗：
1. **元件重造**：每個 agent 自己寫 `<Table>`、`<FilterBar>`、`<StatusBadge>` → 視覺風格 17 路、欄位排版/狀態語意不一致、merge 後得整批重構。
2. **設計漂移**：CLAUDE.md §5「公式 / Schema 唯一權威表」最怕「solo dev 改一處忘另一處」。沒有 SSOT 文件先把 17 頁版型定下來，per-page agent 會各自詮釋資料密度、空狀態、操作確認流程。

這個 change **不動任何 page stub**，只把「設計語言 + 共用元件 + 17 頁版型契約」一次搞定，當作後續 B/C/D 平行 per-page changes 的合約。

## What Changes

### 1. 17 頁版型契約（用 ui-ux-pro-max skill 一次設計完）
- 落地為 `docs/web-admin-page-designs.md`，列入 CLAUDE.md §5 SSOT
- 在現有 Tailwind v4 zinc base + 紅漲綠跌 semantic tokens 之上做，**不另起爐灶**
- 每頁 wireframe 包含：layout slots、必備互動、loading/empty/error 狀態、SSE 即時更新區塊（如有）、紅漲綠跌套用範例、鍵盤可達性
- 對齊 `web-admin/src/router.tsx` 真實 18 路由（17 stubs + Dashboard）；不規劃 `/decisions`、`/reviews/:id`、`/proposals/:id` 等尚未在 router 的頁面

### 2. shadcn/ui primitives 落地（透過 components.json 直接複製，不跑 CLI）
- `Button`、`Card`、`Skeleton`、`Table`、`Badge`（共 5 個，僅落地後續 composite 真實會用到的）
- 全部存於 `web-admin/src/components/ui/`，**禁止後續修改**（客製化用 wrapper）
- Dialog / Input / Label / Select / Tooltip 等 **延後到實際 per-page change 需要時再加**

### 3. 共用 composite 元件（`web-admin/src/components/`）
- `DataTable`：分頁、column-sort、empty/loading/error 狀態、row-click → detail
- `KpiCard`：up/down/neutral 三態 + 紅漲綠跌 token + Lucide 箭頭（從 `DashboardPage` 內聯抽出共用版）
- `StatusBadge`：pending / approved / rejected / executed / expired / canceled / errored
- 全部加 vitest 單元測試 + 鍵盤 / ARIA 檢查
- **延後**（YAGNI 直到第二次需要才抽）：FilterBar、ConfirmDialog、`useSseStream` 通用化 — 這些等實際 per-page change 真的要用時，順便寫

### 4. SSOT / README 更新
- CLAUDE.md §5 新增一行 `web-admin-design-system` 權威指向
- `web-admin/README.md` 加 component 索引段落

### 不在範圍（deferred）
- 任何 `pages/` stub 內容更動 — 留給後續 per-page changes（B/C/D）
- 後端 API 變更 — 完全不動
- `FilterBar`、`ConfirmDialog`、`useSseStream` 通用化 — 等實際 per-page change 真的需要才寫
- shadcn `Dialog`、`Input`、`Label`、`Select`、`Tooltip`、`Drawer`、`Sheet`、`Tabs`、`Form`、`Toast`、`Popover`、`ScrollArea`、`Command` — 等到實際需要的 page 再加（避免一次裝太多沒用到的）
- KLineCharts / Recharts / Tremor / React Flow / ApexCharts — 圖表函式庫等到 Dashboard / Backtest / Symbol / Swarm 各 page change 再評估

## Capabilities

### New Capabilities
- `web-admin-design-system`：design tokens 完整契約（含 density / spacing / typography scale 補完）、17 頁 layout slots 契約、共用 composite 元件 props/events/a11y 契約、shadcn ui primitives 採用清單

### Modified Capabilities
（無）`web-admin-shell` 既有八項 requirement（scaffold、auth、API client、SSE、Dashboard、17 stubs、tokens、color+glyph）**不修改**。本 change 是**擴充**而非**修改** — 新 capability 引用 `web-admin-shell` 既有 token 約定為 baseline，不重複定義。

## Impact

### Affected code
- `web-admin/src/components/ui/`（**新增**）— 5 個 shadcn primitive
- `web-admin/src/components/` — 新增 3 個 composite (`DataTable`、`KpiCard`、`StatusBadge`)
- `web-admin/src/components/layout.tsx`、`AuthGuard.tsx`、`ComingSoon.tsx` — 不動
- `web-admin/src/pages/` — **不動**（Dashboard 例外：抽 KpiCard 同步遷移；見 design.md D3）
- `web-admin/src/index.css` — 補 density 變數
- `web-admin/src/hooks/useAdminEvents.ts` — **不動**

### Affected docs
- `docs/web-admin-page-designs.md`（**新增**）— 17 頁 wireframes + design system 完整 SSOT
- `CLAUDE.md` §5 — 新增一行
- `web-admin/README.md` — 新增 component 索引

### Dependencies
- 不新增 npm package — `lucide-react`、`@radix-ui/react-slot`、`class-variance-authority`、`clsx`、`tailwind-merge` 已在 `web-admin/package.json`
- shadcn primitives 透過官方 source 直接複製到 `components/ui/`（不跑 `npx shadcn add` CLI，避免污染 lock file）

### Risk
- 17 頁 wireframe 一次產出，ui-ux-pro-max 輸出量大；若風格漂移需多輪迭代 → 在 design.md 列明驗收準則（資料密度、操作為主、紅漲綠跌一致性）
- 個人專案、桌面為主 1366+；行動 / 平板 layout **不在範圍**
- 元件 a11y 遵循已 archive 的 web-admin-shell「color is never the only signal」要求
