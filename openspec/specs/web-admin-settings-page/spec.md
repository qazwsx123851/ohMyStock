# web-admin-settings-page Specification

## Purpose
TBD - created by archiving change web-admin-settings-page. Update Purpose after archive.

## Requirements

### Requirement: `/settings` route 取代 stub
`web-admin/src/router.tsx` SHALL 將 `/settings` route 指向 `web-admin/src/pages/SettingsPage.tsx`（新檔），並 SHALL 從 `web-admin/src/pages/stubs.tsx` 移除 `SettingsPage` 匯出。SettingsPage 進入時 SHALL 呼叫 `getSettings()`（`web-admin/src/lib/api.ts` 新增），並依 fetch 狀態渲染 `loading` / `error` / `success` 三態。鍵盤 Tab 順序 SHALL 為：API keys 區 → 主題區 → Safety 區 → Breakers 區（與 `docs/web-admin-page-designs.md` §16 一致）。

#### Scenario: 載入中
- **WHEN** 使用者進入 `/settings` 且 `getSettings()` 尚未 resolve
- **THEN** 頁面 SHALL 顯示 4 個 Card 各帶 Skeleton placeholder
- **AND** 頁面 SHALL NOT 顯示「儲存」或「更新」按鈕

#### Scenario: 401 後跳轉登入
- **GIVEN** `getSettings()` 回 401（Bearer token 失效）
- **WHEN** SettingsPage 收到 401
- **THEN** 頁面 SHALL 觸發既有的 401-abort 邏輯（清 localStorage token + 導向 `/login`），與其他 admin 頁面一致

#### Scenario: 後端 5xx
- **GIVEN** `getSettings()` 回 5xx
- **THEN** 頁面 SHALL 顯示「載入失敗」+ 重試按鈕（不可凍結頁面、不可只顯示空白）

---

### Requirement: 4 節版型與只讀控制
頁面 SHALL 在成功 fetch 後渲染 4 個 `Card` 區塊，順序：API keys → 主題 → Safety → Breakers。每個 Card SHALL 有標題（中文）。所有輸入控制 SHALL 為 disabled 狀態，且每區 SHALL 有一行 hint 文案 "編輯 `.env` 並重啟以變更"。頁面 SHALL NOT 出現「儲存」「儲存所有」「更新」「啟用」等寫入按鈕。

API keys 區內 3 列 SHALL 對應 `data.api_keys.{anthropic, finmind, shioaji}`，每列顯示 `[名稱] [Badge]`：`Badge` 文字為「已設定」（綠 `--down` 漲跌語意中性，這裡用 `bg-muted` 表示中性 OK）或「未設定」（`bg-muted-foreground/20`）。無 mask dot，無 raw value。

主題區 SHALL 顯示 `<select disabled>` 內容為 "跟隨系統"，hint 文字為「此版本未提供主題切換 UI」。

Breakers 區 SHALL 顯示 7 個 disabled `<input>`（`type="text"` + `inputMode="numeric"`，因為純展示需要千分位等格式化字串而 `type="number"` 會剔除非數字字元），數值來自 `data.breakers`：`min_confidence`（0–1，2 位小數顯示）、`daily_limit`（整數）、`max_notional_pct`（百分比顯示，例如 0.25 → `25`）、`max_sizing_deviation`（百分比顯示）、`loss_lockout_hours`（整數）、`loss_pct_threshold`（百分比顯示，例如 -0.05 → `-5`）、`account_equity_twd`（整數，加千分位）。

#### Scenario: 渲染預設值
- **GIVEN** 後端回 `{api_keys: {anthropic: false, finmind: false, shioaji: false}, theme: {mode: "system"}, safety: {auto_execute: false, broker: "shioaji-sim"}, breakers: <defaults>}`
- **THEN** API keys 區 3 列 SHALL 各顯示「未設定」 Badge
- **AND** Breakers 區 `min_confidence` input SHALL 顯示 `"0.70"`
- **AND** Breakers 區 `account_equity_twd` input SHALL 顯示 `"1,000,000"`

#### Scenario: 所有 input 不可編輯
- **WHEN** 頁面渲染完成
- **THEN** 每一個 `<input>`、`<select>`、`<button>` 之 `disabled` 屬性 SHALL 為 `true`
- **AND** 嘗試使用者鍵盤輸入任何 input SHALL NOT 改變其值

#### Scenario: 不出現寫入文案
- **WHEN** 頁面渲染完成
- **THEN** DOM 內 SHALL NOT 包含字串 `"儲存"`、`"啟用"`、`"我已了解風險"`、`"PUT"`

---

### Requirement: Safety 區紅漲綠跌雙重編碼
Safety 區 Card 之邊框與 icon SHALL 隨 `data.safety.auto_execute` 切換：

- `auto_execute = false` → Card 套 `border-warning` + 區頂 `<AlertTriangle className="text-warning"/>` + 文字 "AUTO_EXECUTE 關閉（人工 Confirm Gate）" + broker 顯示 `data.safety.broker`。
- `auto_execute = true`  → Card 套 `border-destructive` + 區頂 `<AlertCircle className="text-destructive"/>` + banner 文案 "⚠ AUTO_EXECUTE 已啟用" + broker 顯示 `data.safety.broker`。

色彩 SHALL 永遠搭配 icon — 不依賴顏色為唯一訊號（`docs/web-admin-page-designs.md` §0.3 強制）。

#### Scenario: 預設關閉狀態
- **GIVEN** `data.safety.auto_execute = false`
- **WHEN** 頁面渲染
- **THEN** Safety Card SHALL 帶 class `border-warning` 或等價 token
- **AND** Safety Card 內 SHALL 渲染 `AlertTriangle` icon
- **AND** Safety Card 內 SHALL NOT 渲染 `AlertCircle` icon

#### Scenario: 啟用狀態
- **GIVEN** `data.safety.auto_execute = true`
- **WHEN** 頁面渲染
- **THEN** Safety Card SHALL 帶 class `border-destructive` 或等價 token
- **AND** Safety Card 內 SHALL 渲染 `AlertCircle` icon
- **AND** Safety Card 內 SHALL 包含字串 `"AUTO_EXECUTE 已啟用"`

#### Scenario: 色彩永遠配 icon
- **WHEN** Safety Card 在任一狀態渲染
- **THEN** Card 內 SHALL 至少有一個 Lucide icon 與當前顏色 token 同義（warning 配 AlertTriangle / destructive 配 AlertCircle）

---

### Requirement: `getSettings()` API client 與 envelope 解析
`web-admin/src/lib/api.ts` SHALL 新增 `getSettings(): Promise<SettingsPayload>` 函式，內部呼叫 `apiFetch("/api/admin/settings")`。Response envelope `{ok, data, error}` SHALL 由既有 `apiFetch` 解析；`ok=false` SHALL throw 與其他 endpoint 一致的錯誤型別。`SettingsPayload` 型別 SHALL 與後端 spec `admin-settings-endpoint` 之 `data` schema 對齊。

#### Scenario: 成功路徑
- **GIVEN** 後端回 `{ok: true, data: {api_keys: {...}, theme: {...}, safety: {...}, breakers: {...}}}`
- **WHEN** 呼叫 `getSettings()`
- **THEN** Promise SHALL resolve 為 `data` 物件本身（非整個 envelope）

#### Scenario: 失敗路徑
- **GIVEN** 後端回 `{ok: false, error: {code: "internal_error", message: "..."}}`
- **WHEN** 呼叫 `getSettings()`
- **THEN** Promise SHALL reject，error 物件 SHALL 帶 `code` 屬性等於 `"internal_error"`
