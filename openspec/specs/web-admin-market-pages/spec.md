# web-admin-market-pages Specification

## Purpose
TBD - created by archiving change web-admin-market-pages. Update Purpose after archive.

## Requirements

### Requirement: API client wrappers
系統 SHALL 在 `web-admin/src/lib/api.ts`（或既有的 api 模組）匯出兩個函式：`runScreener(input)` 對 `POST /api/admin/screener/run` 發 request 並走既有 `apiFetch` 信封解析、以及 `getMarketSymbol(symbol, options?)` 對 `GET /api/admin/market/symbols/{symbol}` 發 request、`options.days` 為 1..252 整數，未提供則不附 `?days`。系統 SHALL 在 `web-admin/src/lib/api.ts`（或同路徑的 types 模組）匯出對應的 TypeScript 型別 `MarketSymbolDetail`、`MarketBar`、`InstitutionalRow`、`RecentPattern`、`ScreenerHit`，欄位對齊 `admin-market-symbol-endpoint` spec 與既有 screener.run 回應 schema。

#### Scenario: getMarketSymbol path 與 query
- **GIVEN** test 將 `apiFetch` mock
- **WHEN** 程式呼叫 `getMarketSymbol("2330", { days: 90 })`
- **THEN** `apiFetch` SHALL 被呼叫一次，path 包含 `/api/admin/market/symbols/2330`
- **AND** path 包含 query `days=90`

#### Scenario: getMarketSymbol 不帶 days
- **WHEN** 程式呼叫 `getMarketSymbol("2330")`
- **THEN** `apiFetch` 收到的 path SHALL 不包含 `days=` query

#### Scenario: 型別包含完整 schema
- **WHEN** 任一 .tsx 檔匯入 `MarketSymbolDetail`
- **THEN** 該型別 SHALL 包含 `symbol`、`quote`、`bars_daily`、`rs`、`sepa`、`institutional`、`recent_patterns` 七個 top-level 欄位

---

### Requirement: `/market` 頁面實作
系統 SHALL 提供 `web-admin/src/pages/MarketPage.tsx`，渲染 filter 表單、`<DataTable>` 命中列表、上次執行摘要列、live event feed。`web-admin/src/router.tsx`（或 `App.tsx`）在 path `/market` 下 SHALL 引用此元件，且 `web-admin/src/pages/stubs.tsx` SHALL 不再 export `MarketPage`。

#### Scenario: 路由綁定
- **WHEN** 已登入的 web-admin app 拜訪 `/market`
- **THEN** 渲染樹 SHALL 不包含 `<ComingSoon name="市場掃描" .../>`
- **AND** SHALL 包含 1 個包住 filter 表單的 `<form>` 或語意等價元素

#### Scenario: filter 表單欄位
- **WHEN** 元件 render 完成
- **THEN** 表單 SHALL 包含一個 universe `<Select>`（至少 4 個選項：tw50 / tw100 / mid100 / custom）
- **AND** 包含一個 chip-input 控制元件接受 custom symbols
- **AND** 包含 4 個 filter checkbox：SEPA / RS≥80 / 法人連續買超 / 三角收斂
- **AND** 包含一個 asof date 控制元件（`<input type="date">` 或 shadcn DatePicker），預設值為今日 ISO date

#### Scenario: 點「跑 screener」呼叫 runScreener
- **GIVEN** universe 選為 `tw50`、未填 custom symbols、SEPA 與 RS≥80 勾選、其餘未勾、asof 為今日
- **WHEN** 使用者點「跑 screener」按鈕
- **THEN** `runScreener` SHALL 被呼叫一次
- **AND** 傳入 input 物件 SHALL 包含 `universe="tw50"`、`filters` 至少包含 `sepa: true` 與 `rs_min: 80`

#### Scenario: Cmd/Ctrl+Enter 觸發 runScreener
- **GIVEN** focus 落在 filter 表單任一 input
- **WHEN** 使用者按下 `Cmd+Enter`（mac）或 `Ctrl+Enter`（win/linux）
- **THEN** `runScreener` SHALL 被呼叫一次

#### Scenario: result 表 6 欄
- **GIVEN** `runScreener` mock 回傳 2 筆 hits：`{symbol:"2330", name:"台積電", price:1025, change_pct:0.012, pattern:"SEPA breakout", score:0.86}` 與 `{symbol:"6505", name:"台塑化", price:33.5, change_pct:-0.003, pattern:"failed entry", score:0.41}`
- **WHEN** screener 執行完成
- **THEN** 結果 `<DataTable>` SHALL 顯示 6 個 column header：Symbol / 名稱 / 現價 / 漲跌 / Pattern / Score
- **AND** SHALL 顯示 2 個 data row

#### Scenario: 「漲跌」欄紅漲綠跌雙重編碼
- **GIVEN** 同上 mock
- **WHEN** 結果 render 完成
- **THEN** `change_pct = 0.012` 該 row 的「漲跌」欄 cell SHALL 同時包含 `class*="text-up"` 與 Lucide `ArrowUp` SVG（`<svg>` 標籤）
- **AND** `change_pct = -0.003` 該 row 的「漲跌」欄 cell SHALL 同時包含 `class*="text-down"` 與 Lucide `ArrowDown` SVG

#### Scenario: 「Score」欄不上色，≥0.7 加粗
- **GIVEN** 同上 mock
- **WHEN** 結果 render 完成
- **THEN** score=0.86 cell SHALL 包含 `class*="font-medium"` 或等價 bold 樣式
- **AND** score=0.86 cell SHALL NOT 包含 `class*="text-up"` 或 `class*="text-down"`

#### Scenario: row click 導航到個股頁
- **GIVEN** result 表已 render 兩列
- **WHEN** 使用者點擊 symbol = `2330` 那一列
- **THEN** 瀏覽器 URL SHALL 變成 `/market/2330`

---

### Requirement: `/market` 三態與 live update
系統 SHALL 在 `/market` 頁面提供 loading / empty / error 三態，並在收到 SSE 事件時即時更新 result 表與 live event feed。

#### Scenario: loading
- **WHEN** `runScreener` Promise 尚未 resolve
- **THEN** result 表區域 SHALL 顯示至少 3 個 `Skeleton` 元素
- **AND** 「上次執行」摘要 SHALL 顯示「啟動中…」或語意等價字串

#### Scenario: empty
- **GIVEN** `runScreener` 回傳 `{run_id:"r#48", hits:[]}`
- **WHEN** screener 完成
- **THEN** result 表區域 SHALL 顯示「本次掃描無命中」或語意等價字串
- **AND** SHALL 包含一個提示訊息建議放寬 filter

#### Scenario: error
- **GIVEN** `runScreener` 拋出 `ApiError({code:"screener_failed", message:"timeout"})`
- **WHEN** error 進入 state
- **THEN** 表單下方 SHALL 渲染含 `class*="--destructive"` 或 `text-destructive` 的區塊
- **AND** SHALL 包含「重試」按鈕
- **AND** filter 表單值 SHALL NOT 被清空

#### Scenario: pattern_detected SSE 即時插入
- **GIVEN** result 表已含 1 列（symbol=2330）
- **WHEN** SSE 推送 `event_type="pattern_detected"` 事件，payload `{symbol:"2454", name:"聯發科", price:1180, change_pct:0.008, pattern:"SEPA + RS=92", score:0.82}`
- **THEN** result 表 SHALL 在 1 秒內變為 2 列
- **AND** `2454` 那一列 SHALL 出現在 `2330` 之前（prepend）

#### Scenario: live feed 顯示最新 5 列
- **GIVEN** SSE 已推送 8 個事件
- **WHEN** 元件 render 完成
- **THEN** live feed 區域 SHALL 至多顯示 5 個 timeline 條目
- **AND** 條目順序 SHALL 為最新在上

---

### Requirement: `/market/{symbol}` 頁面實作
系統 SHALL 提供 `web-admin/src/pages/MarketSymbolPage.tsx`，渲染頁首 quote、K 線 placeholder card、3 張籌碼 KPI 卡、5 列三大法人 `<DataTable>`、最多 20 列 patterns `<DataTable>`。`web-admin/src/router.tsx`（或 `App.tsx`）在 path `/market/:symbol` 下 SHALL 引用此元件，且 `web-admin/src/pages/stubs.tsx` SHALL 不再 export `MarketSymbolPage`。

#### Scenario: 路由綁定
- **WHEN** 已登入的 web-admin app 拜訪 `/market/2330`
- **THEN** 渲染樹 SHALL 不包含 `<ComingSoon name="個股頁" .../>`
- **AND** SHALL 對 `/api/admin/market/symbols/2330` 發出至少一次帶 `Authorization: Bearer ...` 的 GET

#### Scenario: 頁首 quote 顯示
- **GIVEN** `getMarketSymbol` mock 回傳 `quote = {price:1025, change:12, change_pct:0.012, volume:18432000, asof:"2026-05-08"}`
- **WHEN** 元件 render 完成
- **THEN** 頁首區域 SHALL 顯示文字 `1,025`（含千分位）
- **AND** 頁首區域 SHALL 顯示文字 `+1.2%` 或 `+1.20%`（容許 1 或 2 位小數）
- **AND** 頁首「漲跌」區塊 SHALL 同時包含 `class*="text-up"` 與 Lucide `ArrowUp` SVG
- **AND** 頁首 SHALL 顯示 `asof = 2026-05-08`（或本地化字串如「以 2026-05-08 收盤計」）

#### Scenario: change=0 時 muted + 破折號
- **GIVEN** `quote = {price:1025, change:0, change_pct:0, volume:18432000, asof:"2026-05-08"}`
- **WHEN** 元件 render 完成
- **THEN** 頁首「漲跌」區塊 SHALL 顯示 `—` 或 `0`
- **AND** SHALL NOT 包含 `class*="text-up"` 或 `class*="text-down"`

#### Scenario: K 線區為 labelled placeholder
- **GIVEN** `bars_daily` 回傳 60 筆
- **WHEN** 元件 render 完成
- **THEN** 頁面 SHALL 包含一個 `<Card>` 區塊（K 線占位）
- **AND** 該 Card 內 SHALL 顯示提示文字「K 線圖（圖庫待定）」或語意等價字串
- **AND** 此版本 SHALL NOT 引入任何 chart library 依賴

#### Scenario: 3 張籌碼 KPI 卡
- **GIVEN** `rs = {value:92, asof:"2026-05-08"}`、`sepa = {stage:2, since:"2026-04-15"}`、`institutional` 最近 5 日總和為 `+2,180` 張
- **WHEN** 元件 render 完成
- **THEN** 頁面 SHALL 包含 3 個並列的 `<Card>` 元素，每個內含一個 KPI
- **AND** 第一張卡 SHALL 顯示 `92` 與「RS Rank」標題
- **AND** 第二張卡 SHALL 顯示「Stage 2」與「SEPA」標題
- **AND** 第三張卡 SHALL 顯示「連續買超」相關文字（值由實作決定）

#### Scenario: rs = null 處理
- **GIVEN** `rs = null`
- **WHEN** 元件 render 完成
- **THEN** RS Rank 卡 SHALL 顯示 `—` 或「無資料」
- **AND** SHALL NOT 顯示 `null` 字串

---

### Requirement: 三大法人表 + Patterns 表
系統 SHALL 在 `/market/{symbol}` 頁面渲染兩個 `<DataTable>`：三大法人表（5 欄：日期 / 外資 / 投信 / 自營商 / 合計）以及 Patterns 表（4 欄：日期 / Pattern / Score / 結局）。每個數值欄 SHALL 套用紅漲綠跌雙重編碼（顏色 + 箭頭 icon），且 row-click 在 patterns 表 SHALL 導航到 audit 頁。

#### Scenario: 三大法人表 5 欄 5 列
- **GIVEN** `institutional` 5 列均有資料
- **WHEN** 元件 render 完成
- **THEN** 三大法人 `<DataTable>` SHALL 顯示 5 個 column header：日期 / 外資 / 投信 / 自營商 / 合計
- **AND** SHALL 顯示 5 個 data row

#### Scenario: 法人欄紅漲綠跌
- **GIVEN** 某列 `foreign = 1200`、`dealer = -50`
- **WHEN** 元件 render 完成
- **THEN** 該列「外資」cell SHALL 同時包含 `class*="text-up"` 與 `<svg>`（ArrowUp）
- **AND** 該列「自營商」cell SHALL 同時包含 `class*="text-down"` 與 `<svg>`（ArrowDown）

#### Scenario: institutional = [] empty
- **GIVEN** `institutional = []`
- **WHEN** 元件 render 完成
- **THEN** 三大法人區域 SHALL 顯示「近 5 日無法人資料」或語意等價字串

#### Scenario: Patterns 表 4 欄
- **GIVEN** `recent_patterns = [{ts:"2026-04-22T13:30:00+08:00", pattern:"SEPA breakout", score:0.86, outcome:"+2.5% 持有中"}]`
- **WHEN** 元件 render 完成
- **THEN** Patterns `<DataTable>` SHALL 顯示 4 個 column header：日期 / Pattern / Score / 結局
- **AND** SHALL 顯示 1 個 data row
- **AND** 該列「結局」cell SHALL 同時包含 `class*="text-up"` 與 `<svg>`（ArrowUp）

#### Scenario: Patterns row click 導航 audit
- **GIVEN** Patterns 表有一列、symbol="2330"、ts="2026-04-22T13:30:00+08:00"
- **WHEN** 使用者點擊該列
- **THEN** 瀏覽器 URL pathname SHALL 變為 `/audit`
- **AND** URL search SHALL 包含 `symbol=2330`
- **AND** URL search SHALL 包含 `date_from=2026-04-22` 或語意對齊的日期參數

#### Scenario: 結局「未進場」muted
- **GIVEN** `recent_patterns = [{ts:"2026-04-15T13:30:00+08:00", pattern:"pullback", score:0.62, outcome:"未進場"}]`
- **WHEN** 元件 render 完成
- **THEN** 該列「結局」cell SHALL NOT 包含 `class*="text-up"` 或 `class*="text-down"`
- **AND** SHALL 套用 muted-foreground 樣式（`class*="text-muted-foreground"` 或語意等價）

---

### Requirement: `/market/{symbol}` 三態
系統 SHALL 在 `/market/{symbol}` 頁面提供 loading / 404 / error 三態。

#### Scenario: loading
- **WHEN** `getMarketSymbol` Promise 尚未 resolve
- **THEN** 頁首數字、K 線 card、3 張籌碼卡、兩個 DataTable 區域 SHALL 各顯示 `Skeleton`

#### Scenario: 404 symbol 不存在
- **GIVEN** `getMarketSymbol` 拋出 `ApiError({status:404, code:"market_symbol_not_found", message:"..."})`
- **WHEN** error 進入 state
- **THEN** 頁面 SHALL 顯示「該 symbol 無資料」或語意等價字串
- **AND** SHALL 包含「返回 /market」連結

#### Scenario: 一般 error
- **GIVEN** `getMarketSymbol` 拋出 `ApiError({status:500, code:"internal", message:"db down"})`
- **WHEN** error 進入 state
- **THEN** 頁面 SHALL 顯示含錯誤訊息的 `--destructive` 區塊
- **AND** SHALL 包含「重試」按鈕

---

### Requirement: 鍵盤可達性
系統 SHALL 確保 `/market` 與 `/market/{symbol}` 兩頁均符合 SSOT §10–§11 描述的 Tab 順序與鍵盤捷徑。

#### Scenario: `/market` Tab 順序
- **WHEN** 元件 render 完成、focus 從頁首進入
- **THEN** Tab 鍵 SHALL 依序聚焦：universe → custom symbols input → SEPA checkbox → RS≥80 checkbox → 法人連續買超 checkbox → 三角收斂 checkbox → asof date → 「跑 screener」按鈕

#### Scenario: result row Enter 進個股頁
- **GIVEN** result 表已 render 一列、focus 在該列（透過 Tab）
- **WHEN** 使用者按 Enter
- **THEN** 瀏覽器 URL SHALL 變為對應 `/market/{symbol}`

#### Scenario: chip input Enter 加 chip
- **GIVEN** custom symbols chip-input focused、輸入 `1234`
- **WHEN** 使用者按 Enter
- **THEN** chip-input SHALL 顯示一個包含 `1234` 的 chip
- **AND** input 文字框 SHALL 被清空

#### Scenario: chip input Backspace 刪 chip
- **GIVEN** chip-input 已含 `1234` 與 `5678` 兩個 chip、輸入區為空、focused
- **WHEN** 使用者按 Backspace
- **THEN** 最後加入的 chip（`5678`）SHALL 被移除

---

### Requirement: stubs 移除與 router 更新
系統 SHALL 從 `web-admin/src/pages/stubs.tsx` 移除 `MarketPage` 與 `MarketSymbolPage` 兩個 export。`web-admin/src/router.tsx`（或 `App.tsx`）的 import 區 SHALL 改從 `./pages/MarketPage` 與 `./pages/MarketSymbolPage` 引入這兩個元件。

#### Scenario: stubs 不再 export
- **WHEN** test 嘗試 `import { MarketPage, MarketSymbolPage } from '@/pages/stubs'`
- **THEN** 該 import SHALL 為 TypeScript 編譯錯誤或 runtime undefined（兩擇一即可）

#### Scenario: route 引用真元件
- **WHEN** 啟動應用程式
- **THEN** path `/market` 對應的元件 SHALL 為從 `pages/MarketPage` 匯入的 `MarketPage`
- **AND** path `/market/:symbol` 對應的元件 SHALL 為從 `pages/MarketSymbolPage` 匯入的 `MarketSymbolPage`
