## Context

Phase 4 web-admin shell（`9efb544 chore(openspec): archive web-admin-shell-and-auth`）已 archive，現有狀態：
- `web-admin/src/components/`：只有 `AuthGuard.tsx`、`ComingSoon.tsx`、`layout.tsx` — 沒有 `ui/`、沒有 composite
- `web-admin/src/index.css`：Tailwind v4 + shadcn zinc base + 紅漲綠跌 4 個 semantic token + Inter / Noto Sans TC / Fira Code
- `web-admin/src/router.tsx`：18 路由，1 真實（Dashboard）+ 17 stubs
- `web-admin/src/hooks/useAdminEvents.ts`：fetch-based SSE，已實作 1/2/4/8/30s backoff + 401-abort
- `DashboardPage`：KPI row 內聯實作（共 4 卡：今日 P&L / open positions / pending confirms / today LLM cost）
- `components.json`：shadcn 已配置但**沒跑過 CLI**，沒有任何 ui/ 檔案產生

下一階段（Phase 4 後續）要把 17 stub 變真頁。本 change 是「上 17 頁前的最後一道 setup」：把 design 語言、共用元件、頁版型契約定下來，讓後續 per-page changes 可平行不撞。

CLAUDE.md §2 強調：solo dev、避免過度工程、多方案選最簡、SSOT 優先。本 change 必須在「夠用」與「過度設計」之間找平衡。

## Goals / Non-Goals

**Goals:**
- 17 頁版型契約 SSOT 文件（`docs/web-admin-page-designs.md`）足以讓後續 per-page agent 看完就能寫，不用再問人
- 3 個 composite 元件（DataTable / KpiCard / StatusBadge）覆蓋 70%+ 後續 per-page 需求；其餘 composite（FilterBar / ConfirmDialog / useSseStream 通用化）走 YAGNI，等實際 per-page change 真的要用時才寫
- shadcn primitive 落地 5 個（Button / Card / Skeleton / Table / Badge — 上述 3 composite 真實會用到的最小集合）
- 既有 `useAdminEvents` 與 Dashboard 行為**不退步**（Dashboard 抽 KpiCard 後仍能 SSE 即時更新）
- 紅漲綠跌 + 「color is never the only signal」貫徹到所有新元件

**Non-Goals:**
- ❌ 不動任何 `web-admin/src/pages/` 內容（17 stub 留給後續 changes）
- ❌ 不動後端 API、不動 EventBus、不動 schema
- ❌ 不引入 KLineCharts / Recharts / Tremor / React Flow / ApexCharts（圖表函式庫等實際需要的 page change 再評估，避免一次裝太多沒用到的）
- ❌ 不引入 i18next（目前介面只有 zh-TW，純 string literal 夠用）
- ❌ 不引入 TanStack Query 進階 cache 策略改造（目前 `useAdminEvents` + 手寫 fetch 夠用）
- ❌ 不做行動 / 平板 layout（個人本機桌面 1366+ 為主）
- ❌ 不做明 / 暗模式切換 UI（既有 dark class 機制留著，這個 change 不加 toggle）

## Decisions

### D1：shadcn primitive 用「手動複製官方 source」而非 `npx shadcn add` CLI
**選擇：** 從官方 GitHub 複製單檔 source 到 `web-admin/src/components/ui/`，紀錄取用 commit hash 於各檔案頂部註解。

**為什麼不用 CLI：**
- CLI 會動 `package.json`、`pnpm-lock.yaml`、`components.json`、有時動 `tsconfig.json` paths — 這些 side effect 在 solo dev 個人專案會難追，CLAUDE.md §2「改一處忘另一處」風險高
- CLI 會自動加 `@radix-ui/*` deps，但 `package.json` 已經有 `@radix-ui/react-slot`；其餘需要的 Radix package（dialog、select、tooltip、label）我們手動加，可控
- 手動複製可逐檔對版本，需要時可單獨更新單一 primitive

**取捨：**
- 缺點：升級時需手動 diff 對 upstream，沒有 `shadcn diff` 自動化
- 緩解：在 design.md 列當前取用的 commit hash；解決方案是「需要新功能再升級」，不主動追 upstream

### D2：第一波只落地 5 個 primitive，其他延後
**選擇：** Button（DataTable 分頁）、Card（KpiCard）、Skeleton（KpiCard / DataTable loading）、Table（DataTable）、Badge（StatusBadge）。

**理由：** 這 5 個是 3 composite 真實會用到的最小集合。Dialog / Input / Label / Select / Tooltip 在本 change 縮表後**沒人用**（FilterBar / ConfirmDialog 已剃除）。Drawer/Sheet/Tabs/Form/Toast/Popover/ScrollArea/Command 雖 frontend.md §12 都列，但同理沒人用。先裝太多 = 沒用到的 dead code。後續 per-page change 真要用再各自加。

**取捨：**
- 缺點：後續 per-page change 仍需新增 primitive — 但這正是「per-page 真有需求才落地」的本意
- 緩解：建立「primitive 取用流程」短文件（README 章節），規格化「如何加入下一個 primitive」

### D3：KpiCard 從 DashboardPage 內聯抽出，**Dashboard 同步遷移**
**選擇：** 抽出 `<KpiCard>` 後，在本 change 內把 `DashboardPage` 改用新 component。

**為什麼一起遷移：**
- 留兩份實作 = 設計漂移種子 → CLAUDE.md §2 SSOT 違反
- Dashboard 是已 archive 的 web-admin-shell scenario 驗收對象，遷移時要新增「behavior 不變」回歸測試（`<KpiRow>` 仍能用 SSE 更新今日 P&L 顏色）

**取捨：**
- Dashboard 是「真實頁」，本 change 動到它，**邊界稍超出「不動 pages」**。但 Dashboard 不是 stub，且抽 KpiCard 必然動到它。權衡下可接受。
- 緩解：把這個例外明寫於 proposal「Affected code」章節（已寫）。

### D4：（已移除）`useSseStream` 通用化延後到實際需要時
**原方案：** 把 `useAdminEvents` 重構為 `useSseStream(path)` + thin alias，預先支援多條 SSE。

**為什麼移除：** YAGNI — 目前只有 `/api/admin/events` 一條 SSE。所謂「未來可能會有 `/api/admin/screener/stream`」屬於假設性需求，CLAUDE.md §2「不為 hypothetical 規模設計」直接適用。等到第二條 SSE 真的需要時，再做這個重構（總共 ~30 行 diff，沒有實作風險）。

### D5：Density mode 用「local prop」而非「global theme」
**選擇：** `<DataTable density="compact" />` per-component，而非 `<html data-density="compact">` 全域。

**理由：**
- frontend.md §10 沒提全域 density；本 change 只想滿足「同一頁可一覽更多 row」的局部需求（例：Audit log 想 compact，Positions 想 comfortable）
- 全域 theme 切換要做 toggle UI、要持久化到 settings store —**過度工程**
- token 仍定義在 `:root`，未來真要全域 toggle，加一個 `[data-density="compact"] :root { --density-row-h: ... }` 即可平滑升級

### D6：ui-ux-pro-max 產出形式 = 純 Markdown 文字 wireframe（ASCII + 表格 + 顏色 token 引用）
**選擇：** `docs/web-admin-page-designs.md` 內容為純 Markdown，每頁包含 ASCII wireframe（對齊 frontend.md §17 風格）、layout slots 表格、interactions 條列、states 描述。

**為什麼不用圖片 / Figma 連結：**
- 個人專案沒有 Figma 工作流；圖片難 version control + 難 LLM 讀
- ASCII wireframe 在 frontend.md §17 已經實證可行（Dashboard / Chat / Swarm 等都這樣寫過）
- LLM-friendly：後續 per-page agent 直接讀 Markdown 就能寫頁

**取捨：**
- 缺點：精細視覺細節靠口語描述
- 緩解：搭配 design system tokens（已存在）+ 元件 props（已 spec）+ shadcn primitive 樣式（已固定）→ 視覺一致性靠系統而非 wireframe 細節

### D7：ui-ux-pro-max skill 的調用方式 — 一次 batch 17 頁
**選擇：** `tasks.md` 第 1 步直接 invoke ui-ux-pro-max，brief 內含全 17 頁清單與每頁 1-2 行需求摘要 + 對應 admin API endpoint，要求一次輸出全套。

**為什麼不分 17 次：**
- 風格漂移：分次調用每次 context 不同，跨頁一致性差
- 效率：一次 invoke = 一次 token spend
- ui-ux-pro-max 設計就是處理多頁設計系統，正是這類任務的最佳場景

**取捨：**
- 缺點：單次 invoke output 量大，可能需要分章節串接
- 緩解：tasks.md 規範驗收準則 — 缺任何一頁、缺任何 state（loading/empty/error）、漏紅漲綠跌示例 → 退回 ui-ux-pro-max 補

### D8：測試框架 = vitest + React Testing Library + jsdom（既有，不換）
**選擇：** `web-admin/package.json` 已有 vitest@4、@testing-library/react@16、jsdom@29，直接用。

**理由：** archived web-admin-shell-and-auth 已配好，無理由重評估。每個 composite 元件 1 測試檔，覆蓋：
1. happy path render
2. loading state
3. empty / error state
4. 鍵盤可達性（Tab / Enter / Escape）
5. ARIA 屬性（依元件而異：`role="dialog"`、`aria-disabled`、`aria-sort`、`aria-live`）

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| ui-ux-pro-max 輸出風格漂移、跨頁不一致 | tasks.md 列驗收準則：必含 17 路由、必含 4 種 state、必引用既有 token、不另建色票 |
| shadcn upstream 變更導致手動複製版本落後 | 各 ui/ 檔頂部 JSDoc 註明 source URL + commit hash；升級流程留給未來 change，本次不處理 |
| `DashboardPage` 改用 `KpiCard` 後 SSE 行為退步 | 新增 `dashboard-page.test.tsx` smoke test：mock SSE event → 斷言 KpiCard 顏色變動 |
| 17 wireframes 一次寫太多 → tasks 跑一半發現需求不對 | 把 ui-ux-pro-max 結果先 commit 為單獨檔，**先 review 再開始寫元件**（tasks.md 順序保證）|
| 元件 API 與後續 per-page 真實需求脫節 | composite props 設計遵循「YAGNI」：先做最小集合（DataTable 不含 row selection / column resize；FilterBar / ConfirmDialog / useSseStream 通用化整批延後）；per-page change 真的需要再擴 |

## Migration Plan

本 change 沒有資料遷移，但有「Dashboard 微調」需要小心：

1. **新增為主**：先把 5 個 primitive + 3 個 composite 落地，原始檔不動
2. **Dashboard 切換**：DashboardPage 改用 `KpiCard`（diff 預期 < 30 行）→ 跑 vitest，確認 archive 的 web-admin-shell scenario「Stats render with semantic colors」「Live feed updates from SSE」仍通過
3. **SSOT 文件 + CLAUDE.md / README 同步**最後做（避免文件先行、實作對不上）

**Rollback：** 任何步驟出問題，git revert 該 commit 即可（純前端、無 schema、無外部副作用）。

## Open Questions

1. ~~是否需要把 KpiCard 抽出？~~ → 已決定（D3：抽出且 Dashboard 同步遷移）
2. **lucide-react 版本是否需固定？** 現在 `^1.14.0`，本 change 用到的圖示（ArrowUp / ArrowDown / Check / X / Clock / Loader 等）都在這版有 → 不動。後續若要升級另開 change。
3. **是否需要 storybook？** 個人專案、桌面為主、6 個 composite — storybook 過度工程。元件 demo 用 vitest 測試 + 後續 per-page 真實使用驗證即可。
