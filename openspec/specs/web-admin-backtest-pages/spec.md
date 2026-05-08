# web-admin-backtest-pages Specification

## Purpose
TBD - created by archiving change web-admin-backtest-pages. Update Purpose after archive.

## Requirements

### Requirement: API client wrappers
系統 SHALL 在 `web-admin/src/lib/api.ts` 匯出函式：
- `runBacktest(input: BacktestRunInput): Promise<{job_id, status, elapsed_ms}>` 對 `POST /api/admin/backtest/run`
- `listBacktestJobs(limit?: number): Promise<{items: BacktestJobSummary[], count: number}>` 對 `GET /api/admin/backtest/jobs`
- `getBacktestJob(jobId: string): Promise<BacktestJobDetail>` 對 `GET /api/admin/backtest/jobs/{jobId}`
- `listStrategies(): Promise<{name, description}[]>` 對 `GET /api/admin/backtest/strategies`

並匯出對應 TypeScript 型別：`BacktestRunInput`、`BacktestJobSummary`、`BacktestJobDetail`、`BacktestTrade`、`BacktestEquityPoint`、`BacktestDrawdownPoint`，欄位對齊 `admin-backtest-endpoints` spec。

#### Scenario: runBacktest path 與 method
- **GIVEN** test 將 `apiFetch` mock
- **WHEN** 程式呼叫 `runBacktest({strategy:"sma_cross", symbols:["2330"], period_from:"2024-01-01", period_to:"2024-12-31"})`
- **THEN** `apiFetch` SHALL 被呼叫一次，path 包含 `/api/admin/backtest/run`、method 為 POST
- **AND** body 為 JSON 字串、解析後 SHALL 包含 `strategy`、`symbols`、`period_from`、`period_to`

#### Scenario: listBacktestJobs limit query
- **WHEN** 程式呼叫 `listBacktestJobs(50)`
- **THEN** `apiFetch` 收到的 path SHALL 包含 `limit=50`

#### Scenario: getBacktestJob path
- **WHEN** 程式呼叫 `getBacktestJob("a1b2c3d4e5f60718293a4b5c6d7e8f90")`
- **THEN** `apiFetch` 收到的 path SHALL 包含 `/api/admin/backtest/jobs/a1b2c3d4e5f60718293a4b5c6d7e8f90`

#### Scenario: 型別包含完整 schema
- **WHEN** 任一 .tsx 檔匯入 `BacktestJobDetail`
- **THEN** 該型別 SHALL 包含 `id`、`strategy`、`period_from`、`period_to`、`status`、`metrics`、`equity_curve`、`drawdown`、`trades`、`error` top-level 欄位

---

### Requirement: `/backtest` 頁面實作
系統 SHALL 提供 `web-admin/src/pages/BacktestPage.tsx`，渲染 filter 表單、上次執行摘要、歷史 job `<DataTable>`。`web-admin/src/router.tsx` 在 path `/backtest` 下 SHALL 引用此元件，且 `web-admin/src/pages/stubs.tsx` SHALL 不再 export `BacktestPage`。

#### Scenario: 路由綁定
- **WHEN** 已登入的 web-admin app 拜訪 `/backtest`
- **THEN** 渲染樹 SHALL 不包含 `<ComingSoon name="回測入口" .../>`
- **AND** SHALL 包含 1 個包住 backtest filter 表單的 `<form>` 或語意等價元素

#### Scenario: filter 表單欄位
- **WHEN** 元件 render 完成（mock `listStrategies` 回傳 `[{name:"sma_cross", description:"..."}]`）
- **THEN** 表單 SHALL 包含一個 strategy `<select>`（至少 1 個選項：`sma_cross`）
- **AND** 包含一個 chip-input 控制元件接受 custom symbols
- **AND** 包含 2 個 date 控制元件（period from / period to）
- **AND** 包含一個 initial capital `<input type="number">`，預設值為 `1000000`
- **AND** 包含 「跑回測」 submit 按鈕與「清空」reset 按鈕

#### Scenario: 點「跑回測」呼叫 runBacktest
- **GIVEN** strategy=`sma_cross`、symbols 內含一個 chip `2330`、period_from=`2024-01-01`、period_to=`2024-12-31`
- **WHEN** 使用者點「跑回測」按鈕
- **THEN** `runBacktest` SHALL 被呼叫一次
- **AND** input 物件 SHALL 等於 `{strategy:"sma_cross", symbols:["2330"], period_from:"2024-01-01", period_to:"2024-12-31", initial_capital:1000000}` 或 superset

#### Scenario: Cmd/Ctrl+Enter 觸發 runBacktest
- **GIVEN** focus 落在 filter 表單任一 input
- **WHEN** 使用者按下 `Cmd+Enter`（mac）或 `Ctrl+Enter`（win/linux）
- **THEN** `runBacktest` SHALL 被呼叫一次

#### Scenario: 「清空」reset 表單
- **GIVEN** 表單已被填過（symbols 內 1 chip、period from 已改）
- **WHEN** 使用者點「清空」
- **THEN** symbols chip 區 SHALL 為空
- **AND** period from 與 to SHALL 回到預設

#### Scenario: history 表 8 欄
- **GIVEN** `listBacktestJobs` mock 回 2 筆 jobs：（1）completed sma_cross 2024-01-01..2024-12-31 metrics 18.2/1.42/-0.083/0.54；（2）failed sma_cross 2024 H2
- **WHEN** 元件 render 完成
- **THEN** 結果 `<DataTable>` SHALL 顯示 8 個 column header：JobId / 策略 / 期間 / 年化 / Sharpe / MaxDD / 狀態 / 建立時間
- **AND** SHALL 顯示 2 個 data row

#### Scenario: 「年化」「Sharpe」「MaxDD」欄紅漲綠跌雙重編碼
- **GIVEN** 同上 mock，第一筆 annual=+0.182、sharpe=1.42、maxdd=-0.083
- **WHEN** 結果 render 完成
- **THEN** 該 row 的「年化」cell SHALL 同時包含 `class*="text-up"` 與 Lucide `ArrowUp` SVG
- **AND** 該 row 的「Sharpe」cell SHALL 同時包含 `class*="text-up"`（>1）與 SVG
- **AND** 該 row 的「MaxDD」cell SHALL 同時包含 `class*="text-down"` 與 Lucide `ArrowDown` 或 `TrendingDown` SVG

#### Scenario: failed job row 顯示 — 不上色
- **GIVEN** 表內第二筆 status="failed"、衍生欄位為 null
- **WHEN** 元件 render 完成
- **THEN** 該 row 的「年化」、「Sharpe」、「MaxDD」cell SHALL 顯示 `—`
- **AND** SHALL NOT 包含 `class*="text-up"` 或 `class*="text-down"`
- **AND** 「狀態」欄 SHALL 顯示 「失敗」或語意等價字串

#### Scenario: row click 導航到個別 job 頁
- **GIVEN** result 表已 render 一列、id=`a1b2c3...`
- **WHEN** 使用者點擊該列
- **THEN** 瀏覽器 URL SHALL 變成 `/backtest/a1b2c3...`

---

### Requirement: `/backtest` 三態與 run-success 行為
系統 SHALL 在 `/backtest` 頁面提供 loading / empty / error 三態，並在 `runBacktest` 成功後刷新 history list。

#### Scenario: 表單 submit loading
- **WHEN** `runBacktest` Promise 尚未 resolve
- **THEN** 「跑回測」按鈕 SHALL 為 disabled
- **AND** SHALL 顯示「啟動中…」或語意等價字串

#### Scenario: history 載入中 skeleton
- **WHEN** `listBacktestJobs` Promise 尚未 resolve
- **THEN** history 區域 SHALL 顯示至少 3 個 `Skeleton` 元素

#### Scenario: history 空表
- **GIVEN** `listBacktestJobs` 回 `{items: [], count: 0}`
- **WHEN** 元件 render 完成
- **THEN** history 區域 SHALL 顯示「尚未跑過回測」或語意等價字串
- **AND** SHALL 包含一個提示訊息建議「填上方表單後點『跑回測 →』」

#### Scenario: runBacktest 失敗顯示 error banner
- **GIVEN** `runBacktest` 拋出 `ApiError({code:"missing_bars", message:"no bars for 9999 in window"})`
- **WHEN** error 進入 state
- **THEN** 表單下方 SHALL 渲染含 `text-destructive` 的區塊
- **AND** SHALL 包含「重試」按鈕
- **AND** filter 表單值 SHALL NOT 被清空

#### Scenario: runBacktest 成功 → history 刷新
- **GIVEN** `runBacktest` 回 `{job_id:"new1", status:"completed"}`
- **WHEN** Promise resolve
- **THEN** `listBacktestJobs` SHALL 在 1 秒內被再次呼叫一次
- **AND** 新 job_id SHALL 出現在 history 表第一列（透過 mock 第二次回傳）

---

### Requirement: `/backtest/{jobId}` 頁面實作
系統 SHALL 提供 `web-admin/src/pages/BacktestJobPage.tsx`，渲染頁首（返回連結 + jobId + strategy + period）、4 張 KPI 卡、equity curve placeholder card、drawdown placeholder card、trades `<DataTable>`。`web-admin/src/router.tsx` 在 path `/backtest/:jobId` 下 SHALL 引用此元件，且 `web-admin/src/pages/stubs.tsx` SHALL 不再 export `BacktestJobPage`。

#### Scenario: 路由綁定
- **WHEN** 已登入的 web-admin app 拜訪 `/backtest/a1b2c3d4e5f60718293a4b5c6d7e8f90`
- **THEN** 渲染樹 SHALL 不包含 `<ComingSoon name="回測結果" .../>`
- **AND** SHALL 對 `/api/admin/backtest/jobs/a1b2c3d4e5f60718293a4b5c6d7e8f90` 發出至少一次帶 `Authorization: Bearer ...` 的 GET

#### Scenario: 頁首 顯示
- **GIVEN** `getBacktestJob` mock 回 detail：strategy=sma_cross、period 2024-01-01..2024-12-31
- **WHEN** 元件 render 完成
- **THEN** 頁面 SHALL 顯示「← /backtest」返回連結
- **AND** SHALL 顯示 jobId 縮寫（前 8 字 + …）或完整 id
- **AND** SHALL 顯示「sma_cross · 2024-01-01 ~ 2024-12-31」或語意等價

#### Scenario: 4 張 KPI 卡
- **GIVEN** detail.metrics = `{annual_return_pct:0.182, sharpe:1.42, max_drawdown_pct:-0.083, win_rate_pct:0.542}`
- **WHEN** 元件 render 完成
- **THEN** 頁面 SHALL 包含 4 個並列 `<KpiCard>`
- **AND** 「年化」卡 SHALL 顯示 `+18.2%` 或 `+18.20%` + `class*="text-up"` + ArrowUp SVG
- **AND** 「Sharpe」卡 SHALL 顯示 `1.42` + `class*="text-up"`（>1）
- **AND** 「MaxDD」卡 SHALL 顯示 `-8.3%` 或 `-8.30%` + `class*="text-down"` + ArrowDown SVG
- **AND** 「勝率」卡 SHALL 顯示 `54.2%` 或 `54.20%`、neutral（不上色）

#### Scenario: 兩張圖區為 labelled placeholder
- **GIVEN** detail.equity_curve.length = 200
- **WHEN** 元件 render 完成
- **THEN** 頁面 SHALL 包含一個 `<Card>` 包住「資金曲線（圖庫待定）」字串
- **AND** 另一個 `<Card>` 包住「回撤曲線（圖庫待定）」字串
- **AND** 此版本 SHALL NOT 引入任何 chart library 依賴

#### Scenario: trades 表 7 欄
- **GIVEN** detail.trades = `[{entry_date:"2024-01-15", exit_date:"2024-01-22", symbol:"2330", side:"long", qty:1, entry_price:600, exit_price:612, pnl_twd:12000, hold_days:7, pattern:"SEPA breakout"}, {entry_date:"2024-02-03", exit_date:"2024-02-04", symbol:"2454", side:"long", qty:1, entry_price:1200, exit_price:1180, pnl_twd:-20000, hold_days:1, pattern:"failed entry"}]`
- **WHEN** 元件 render 完成
- **THEN** trades `<DataTable>` SHALL 顯示 7 個 column header：進場日 / 出場日 / Symbol / 方向 / P&L / 持倉 / Pattern
- **AND** SHALL 顯示 2 個 data row
- **AND** P&L=+12,000 row SHALL 包含 `class*="text-up"` 與 ArrowUp SVG
- **AND** P&L=-20,000 row SHALL 包含 `class*="text-down"` 與 ArrowDown SVG

#### Scenario: empty trades
- **GIVEN** detail.trades = `[]`
- **WHEN** 元件 render 完成
- **THEN** trades 區域 SHALL 顯示「本 job 區間無交易訊號」或語意等價字串

---

### Requirement: `/backtest/{jobId}` 三態
系統 SHALL 在 `/backtest/{jobId}` 頁面提供 loading / 404 / error / failed-job 四態。

#### Scenario: loading
- **WHEN** `getBacktestJob` Promise 尚未 resolve
- **THEN** 頁首數字、4 張 KPI 卡、兩個圖區、trades 表 SHALL 各顯示 `Skeleton`

#### Scenario: 404 not_found
- **GIVEN** `getBacktestJob` 拋出 `ApiError({status:404, code:"not_found"})`
- **WHEN** error 進入 state
- **THEN** 頁面 SHALL 顯示「該 job 不存在」或語意等價字串
- **AND** SHALL 包含「返回 /backtest」連結

#### Scenario: 一般 error
- **GIVEN** `getBacktestJob` 拋出 `ApiError({status:500, code:"internal_error"})`
- **WHEN** error 進入 state
- **THEN** 頁面 SHALL 顯示含錯誤訊息的 `text-destructive` 區塊
- **AND** SHALL 包含「重試」按鈕

#### Scenario: failed job 視覺降級
- **GIVEN** detail.status="failed"、detail.metrics=null、detail.error={code:"INVALID_INPUT", message:"warmup not satisfied"}
- **WHEN** 元件 render 完成
- **THEN** 4 張 KPI 卡 SHALL 顯示 `—`、neutral
- **AND** 兩張圖區 placeholder Card SHALL 顯示「無資料 — job 失敗」或語意等價字串
- **AND** trades 表 SHALL 顯示「本 job 區間無交易訊號」
- **AND** 頁面 SHALL 顯示一個顯眼的 banner，內容包含 `error.message`

---

### Requirement: 鍵盤可達性
系統 SHALL 確保 `/backtest` 與 `/backtest/{jobId}` 兩頁均符合 SSOT §5–§6 描述的 Tab 順序與鍵盤捷徑。

#### Scenario: `/backtest` Tab 順序
- **WHEN** 元件 render 完成、focus 從頁首進入
- **THEN** Tab 鍵 SHALL 依序聚焦：strategy → period from → period to → custom symbols input → initial capital → 清空 → 跑回測 → result row 1..N

#### Scenario: result row Enter 進個別 job 頁
- **GIVEN** history 表已 render 一列、focus 在該列（透過 Tab）
- **WHEN** 使用者按 Enter
- **THEN** 瀏覽器 URL SHALL 變為對應 `/backtest/{jobId}`

#### Scenario: chip input Enter 加 chip
- **GIVEN** custom symbols chip-input focused、輸入 `2330`
- **WHEN** 使用者按 Enter
- **THEN** chip-input SHALL 顯示一個包含 `2330` 的 chip
- **AND** input 文字框 SHALL 被清空

#### Scenario: chip input Backspace 刪 chip
- **GIVEN** chip-input 已含 `2330` 與 `2454` 兩個 chip、輸入區為空、focused
- **WHEN** 使用者按 Backspace
- **THEN** 最後加入的 chip（`2454`）SHALL 被移除

---

### Requirement: stubs 移除與 router 更新
系統 SHALL 從 `web-admin/src/pages/stubs.tsx` 移除 `BacktestPage` 與 `BacktestJobPage` 兩個 export。`web-admin/src/router.tsx` 的 import 區 SHALL 改從 `./pages/BacktestPage` 與 `./pages/BacktestJobPage` 引入這兩個元件。

#### Scenario: stubs 不再 export
- **WHEN** test 嘗試 `import { BacktestPage, BacktestJobPage } from '@/pages/stubs'`
- **THEN** 該 import SHALL 為 TypeScript 編譯錯誤或 runtime undefined（兩擇一即可）

#### Scenario: route 引用真元件
- **WHEN** 啟動應用程式
- **THEN** path `/backtest` 對應的元件 SHALL 為從 `pages/BacktestPage` 匯入的 `BacktestPage`
- **AND** path `/backtest/:jobId` 對應的元件 SHALL 為從 `pages/BacktestJobPage` 匯入的 `BacktestJobPage`
