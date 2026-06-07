## Why

`docs/web-admin-user-testing-spec.md` 盤點後台 operator 動線時，發現 `docs/user-scenarios.md` 寫了、但 web-admin 實際**沒做**的 9 項功能（落差總表 D2–D6、D8–D11）。這些缺口讓多個 operator 情境無法走完（風控判讀、月度熔斷防護、拒絕原因記錄、連線排錯、cold start 寫偏好），也讓對應的測試情境停在 `[BLOCKED]`。本 change 一次補齊，使這些情境從 `[BLOCKED]` 轉為可測。

## What Changes

依優先序（P0 → P1 → P2）：

**P0 — 安全相關**
- **DB-B1**（D4）：Dashboard 新增 risk gate 三色燈（綠/黃/紅 + 觸發哪條）。觸發條件 SSOT 為 `docs/workflow-cheatsheet.md` §0，後端只回狀態、不重抄公式。
- **DB-B2**（D5）：Dashboard 新增月度熔斷 banner（月 PnL ≤ -8% 時紅 banner + 禁新進場提示）。

**P1 — 核心動線缺口**
- **CG-B2**（D3）：Confirm Gate reject 加自訂原因輸入框（後端 `reason` 已支援，移除前端寫死的 `user_reject`）。
- **CG-B1**（D2）：Confirm Gate confirm 加二次輸入張數 ConfirmDialog；confirm endpoint 接受 `qty` 覆寫，**仍受 sizing clamp 防線約束**（`docs/safety-and-simulation.md` §2.9）。
- **ST-B1**（D9）：Settings 加 Shioaji / FinMind 連線測試 endpoint + 前端按鈕與結果呈現。
- **ME-B1**（D11）：Memory 加寫入個人偏好功能（後端 write endpoint + 前端表單）。**解除** 目前刻意的 v0 read-only。

**P2 — 體驗增強**
- **DB-B3**（D6）：Dashboard LLM 成本由單一數字改為進度條（≥80% 橘色），需後端提供本月預算上限。
- **ST-B2**（D10）：Settings 顯示剩餘額度 / 當前模型分布（settings payload 加欄位）。
- **PR-B1**（D8）：Proposal 詳情頁加 Re-validate 按鈕（帶入上次參數重開 ValidationDialog）。純前端。

## Capabilities

### New Capabilities
（無 — 全部落在既有 capability 的 requirement 增修）

### Modified Capabilities
- `admin-read-endpoints`: Dashboard summary 新增 risk gate 狀態、月度熔斷旗標、本月成本/預算（DB-B1/B2/B3 後端）
- `confirm-gate`: confirm endpoint 接受使用者覆寫 `qty`，並套用 sizing clamp（CG-B1 後端）
- `admin-settings-endpoint`: 新增連線測試 endpoint；settings payload 新增剩餘額度 / 模型分布（ST-B1/B2 後端）
- `admin-memory-endpoints`: 新增 memory write endpoint（ME-B1 後端）
- `memory-store`: 解除 read-only，支援 insert（ME-B1 後端）
- `web-admin-shell`: Dashboard 新增 risk gate 三色燈 / 月度熔斷 banner / 成本進度條（DB-B1/B2/B3 前端）
- `web-admin-paper-overview-page`: reject 原因輸入框 + confirm 張數 ConfirmDialog（CG-B1/B2 前端）
- `web-admin-settings-page`: 連線測試 UI + 額度/模型分布顯示（ST-B1/B2 前端）
- `web-admin-memory-page`: 寫入偏好表單（ME-B1 前端）
- `web-admin-proposals-pages`: Re-validate 按鈕（PR-B1 前端）

## Impact

**後端（`src/ohmystock/`）**
- `api/routes/`：`stats`/`positions`（dashboard summary）、`confirm_gate`（qty 覆寫）、`settings`（連線測試 + 額度/模型）、memory write endpoint
- `safety/`：confirm qty 覆寫需接 sizing clamp（防線 9，`auto_execute.py` / confirm_gate service）
- `memory/`：store 新增 insert 路徑
- risk gate / 月度熔斷狀態：讀既有 risk gate 與月度 PnL 來源（不重算公式，引用 `workflow-cheatsheet.md` §0）

**前端（`web-admin/src/`）**
- `pages/`：`DashboardPage`（風險面板/banner/進度條）、`PaperOverviewPage`（reject/confirm dialog）、`SettingsPage`（連線測試/額度）、`MemoryPage`（寫入表單）、`ProposalDetailPage`（Re-validate）
- `components/`：可能新增 ConfirmDialog / 連線測試結果元件
- `lib/api.ts`：對應新 endpoint 型別

**測試**
- 完成後 `docs/web-admin-user-testing-spec.md` 對應 9 個 `[BLOCKED]` 情境改 `[可測]`；建議在 Vitest（前端互動）+ Playwright E2E（碰錢/狀態流）補測。

**文件**
- 同步 `docs/web-admin-user-testing-spec.md` 落差總表、`docs/user-scenarios.md`（D1/D7 仍為「改文件」類，不在本 change 範圍）。

**非目標（避免過度工程）**
- 不做 Settings 全面可寫（仍以 .env 為主，只加連線測試 + 唯讀額度/模型顯示）。
- 不重抄任何 risk-off / sizing / 熔斷公式，一律引用 SSOT。
