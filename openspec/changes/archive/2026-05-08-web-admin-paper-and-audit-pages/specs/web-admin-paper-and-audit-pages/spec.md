## ADDED Requirements

### Requirement: 共用型別與 journal-kind 常數
系統 SHALL 在 `web-admin/src/lib/api.ts` 新增匯出三個 TypeScript 型別：`OpenPosition`、`JournalRow`、`PaginatedRows<T>`，欄位對齊 `openspec/specs/admin-read-endpoints/spec.md` 內定義的回應 schema。系統 SHALL 在新檔 `web-admin/src/lib/journal-kinds.ts` 匯出兩個 `readonly` 陣列常數 `JOURNAL_KIND_ENTRY_LIKE` 與 `JOURNAL_KIND_ALL`，以及 type alias `type JournalKind = (typeof JOURNAL_KIND_ALL)[number]`，作為前端 filter UI 與型別檢查的單一來源。

#### Scenario: PaginatedRows 型別形狀
- **WHEN** 任一檔案匯入 `PaginatedRows<JournalRow>`
- **THEN** 該型別 SHALL 包含 `items: JournalRow[]`、`total: number`、`limit: number`、`offset: number`、`has_more: boolean` 五個欄位

#### Scenario: JOURNAL_KIND_ENTRY_LIKE 內容
- **WHEN** 任一檔案匯入 `JOURNAL_KIND_ENTRY_LIKE`
- **THEN** 其值 SHALL 等於 `['entry', 'fill', 'exit', 'reject'] as const`（順序敏感，作為 filter checkbox 顯示順序）

#### Scenario: JOURNAL_KIND_ALL 是 ENTRY_LIKE 的超集
- **WHEN** 在 vitest 中比對兩常數
- **THEN** `JOURNAL_KIND_ENTRY_LIKE.every((k) => JOURNAL_KIND_ALL.includes(k))` SHALL 為 `true`

---

### Requirement: `/paper/positions` 頁面實作
系統 SHALL 提供 `web-admin/src/pages/PaperPositionsPage.tsx`，渲染所有開倉部位的 `<DataTable>`、選定列下方的 detail panel，並訂閱 `GET /api/admin/positions/open`。`web-admin/src/router.tsx` 在 path `/paper/positions` 下 SHALL 引用此元件，且 `web-admin/src/pages/stubs.tsx` SHALL 不再 export `PaperPositionsPage`。

#### Scenario: 路由綁定
- **WHEN** 啟動的 web-admin app 拜訪 `/paper/positions`（已登入）
- **THEN** 渲染樹 SHALL 不包含 `<ComingSoon name="持倉明細" .../>` 元件
- **AND** SHALL 對 `/api/admin/positions/open` 發出至少一次帶 `Authorization: Bearer ...` 的 GET

#### Scenario: 表格欄位對齊 page-designs §9
- **GIVEN** `apiFetch` mock 回傳兩筆 `OpenPosition`，其中一筆 `unrealized_pnl_twd > 0`、另一筆 `< 0`
- **WHEN** 元件 render 完成
- **THEN** `<DataTable>` SHALL 顯示 10 欄 header：Symbol / 方向 / Qty / Entry / 現價 / 未實現 P&L / P&L% / 停損 / T1 / 持倉
- **AND** P&L 為正的列 SHALL 在 P&L 欄同時包含 `class*="text-up"` 與 `<svg>` (Lucide ArrowUp)
- **AND** P&L 為負的列 SHALL 在 P&L 欄同時包含 `class*="text-down"` 與 `<svg>` (Lucide ArrowDown)

#### Scenario: 三態
- **WHEN** `apiFetch` 尚未 resolve
- **THEN** 頁面 SHALL 顯示至少 3 個 `Skeleton` 元素於表格列位置
- **WHEN** `apiFetch` resolve 為空陣列 `[]`
- **THEN** 頁面 SHALL 顯示「目前無開倉」訊息與一個 Lucide icon
- **WHEN** `apiFetch` 拋出 `ApiError`
- **THEN** 頁面 SHALL 顯示包含錯誤訊息的 `--destructive` 區塊與 retry 按鈕

#### Scenario: detail panel 切換
- **GIVEN** 表格已渲染兩列、目前無選定列
- **WHEN** 使用者點擊第一列
- **THEN** 表格下方 SHALL 渲染一個 `<Card>` 顯示該 row 的 `entry_at`、`entry_reason`、停損距離百分比、T1 距離百分比、`time_stop_date`
- **WHEN** 使用者再點擊第二列
- **THEN** detail panel SHALL 切換為第二列的對應欄位

---

### Requirement: `/paper/orders` 頁面實作
系統 SHALL 提供 `web-admin/src/pages/PaperOrdersPage.tsx`，含 filter bar、`<DataTable>`、分頁、CSV 匯出，並訂閱 `GET /api/admin/journal/rows`。filter 狀態 SHALL 透過 `useSearchParams` 與 URL query string 雙向同步。`web-admin/src/router.tsx` 在 path `/paper/orders` 下 SHALL 引用此元件。

#### Scenario: 路由綁定
- **WHEN** 啟動的 web-admin app 拜訪 `/paper/orders`（已登入）
- **THEN** 渲染樹 SHALL 不包含 `<ComingSoon name="委託歷史" .../>`

#### Scenario: filter bar checkbox 由 JOURNAL_KIND_ENTRY_LIKE 驅動
- **WHEN** 元件 render 完成
- **THEN** filter bar SHALL 渲染 4 個 checkbox，name 屬性分別為 `entry`、`fill`、`exit`、`reject`，順序與 `JOURNAL_KIND_ENTRY_LIKE` 相同
- **AND** 預設 SHALL 全部勾選

#### Scenario: 改 filter 後按「套用」更新 URL 與 fetch
- **GIVEN** URL 為 `/paper/orders`，apiFetch 已被呼叫一次（無 query 參數）
- **WHEN** 使用者取消 `fill` 與 `reject` 兩 checkbox，再按「套用」
- **THEN** URL search SHALL 變成包含 `kind=entry&kind=exit`（順序與 ENTRY_LIKE 對齊）
- **AND** apiFetch SHALL 再被呼叫一次，傳入的 path SHALL 包含 `kind=entry` 與 `kind=exit` 兩 query key 但不含 `kind=fill` 或 `kind=reject`

#### Scenario: 分頁 offset 計算
- **GIVEN** filter 預設、`limit=50`，使用者目前在 page 3
- **WHEN** 元件對後端發 GET
- **THEN** path query string SHALL 含 `limit=50` 與 `offset=100`

#### Scenario: 「匯出 CSV」匯出當前 page 列
- **GIVEN** 當前 page 顯示 7 列
- **WHEN** 使用者點擊「匯出本頁 7 列 CSV」
- **THEN** 程式 SHALL 呼叫 `URL.createObjectURL` 建立 Blob 一次
- **AND** Blob 內容 SHALL 為以逗號分隔、第一行為 7 個欄位 header、後續 7 行為資料的 CSV 字串

#### Scenario: 方向欄套色
- **GIVEN** 一筆 `payload.side === 'long'` 的 row 與一筆 `'short'` 的 row
- **THEN** 第一列方向欄 SHALL 同時包含 `class*="text-up"` + ArrowUp svg；第二列同時包含 `class*="text-down"` + ArrowDown svg

#### Scenario: 三態
- **WHEN** apiFetch 尚未 resolve
- **THEN** 頁面 SHALL 顯示至少 3 個 Skeleton 元素於表格列位置
- **WHEN** apiFetch resolve 的 `items` 為 `[]`
- **THEN** 頁面 SHALL 顯示「此 filter 無紀錄」訊息與「清空 filter」按鈕
- **WHEN** apiFetch 拋出 ApiError
- **THEN** 頁面 SHALL 顯示包含錯誤訊息的 `--destructive` 區塊與 retry 按鈕

---

### Requirement: `/audit` 頁面實作
系統 SHALL 提供 `web-admin/src/pages/AuditPage.tsx`，含 filter bar（含 decision_id 欄位與 density toggle）、`<DataTable density="compact">`、分頁與 JSONL 匯出，並訂閱 `GET /api/admin/journal/rows`。filter 狀態 SHALL 透過 `useSearchParams` 同步。`web-admin/src/router.tsx` 在 path `/audit` 下 SHALL 引用此元件。

#### Scenario: 路由綁定
- **WHEN** 啟動的 web-admin app 拜訪 `/audit`（已登入）
- **THEN** 渲染樹 SHALL 不包含 `<ComingSoon name="稽核日誌" .../>`

#### Scenario: filter bar 包含全部 11 種 kind checkbox
- **WHEN** 元件 render 完成
- **THEN** filter bar SHALL 渲染 N 個 checkbox，N 等於 `JOURNAL_KIND_ALL.length`
- **AND** 每個 checkbox 的 name 屬性 SHALL 等於 `JOURNAL_KIND_ALL[i]`

#### Scenario: decision_id filter 對應到後端 query 參數
- **GIVEN** 使用者在 decision id 輸入框輸入 `d-129`，按「套用」
- **THEN** apiFetch SHALL 被以含 `decision_id=d-129` 的 path 呼叫一次

#### Scenario: density toggle 切換
- **GIVEN** 預設 density 為 `compact`
- **WHEN** 使用者點擊 density toggle
- **THEN** `<DataTable>` SHALL 收到 `density="comfortable"` prop
- **AND** URL search SHALL 含 `density=comfortable`

#### Scenario: 「共 N 列」總數顯示
- **GIVEN** apiFetch resolve 的 envelope `total = 8432`、`items.length = 50`
- **WHEN** 元件 render 完成
- **THEN** 分頁列附近 SHALL 顯示文字「共 8,432 列」（依 `Intl.NumberFormat('zh-TW')` 格式化）

#### Scenario: 「匯出 JSONL」匯出當前 page 列
- **GIVEN** 當前 page 顯示 50 列
- **WHEN** 使用者點擊「匯出本頁 50 列 JSONL」
- **THEN** 程式 SHALL 建立一個 Blob，內容 SHALL 為以 `\n` 分隔、共 50 行的字串，每行 SHALL 為單筆 row 的 `JSON.stringify(row)`

#### Scenario: 三態
- **WHEN** apiFetch 尚未 resolve
- **THEN** 頁面 SHALL 顯示至少 3 個 Skeleton 元素
- **WHEN** apiFetch resolve `items: []`
- **THEN** 頁面 SHALL 顯示「此 filter 無紀錄」訊息與「清空 filter」按鈕
- **WHEN** apiFetch 拋出 ApiError
- **THEN** 頁面 SHALL 顯示錯誤訊息與 retry 按鈕

---

### Requirement: `<DataTable>` 新增 `expandedRowRender` 與 `onRowClick` opt-in props
系統 SHALL 在 `web-admin/src/components/data-table.tsx` 新增兩個可選 props：`onRowClick?: (row: T) => void` 與 `expandedRowRender?: (row: T, isExpanded: boolean) => ReactNode | null`。當兩者皆未提供時，`<DataTable>` 行為與本 change 之前 SHALL 完全相同（既有所有 vitest 測試 SHALL 不修改即通過）。

#### Scenario: 不提供 props 時行為不變
- **GIVEN** `<DataTable>` 既有的 `data-table.test.tsx` 測試集合
- **WHEN** 在本 change 之後執行該測試集合
- **THEN** 全部測試 SHALL 通過且不需要修改測試碼

#### Scenario: 提供 onRowClick 時點 row 觸發 callback
- **GIVEN** 將 `onRowClick={spy}` 傳入 DataTable，資料有 3 列
- **WHEN** 使用者點第二列
- **THEN** spy SHALL 以該 row 物件為參數被呼叫一次

#### Scenario: 提供 expandedRowRender 時展開列為 colspan-full
- **GIVEN** 將 `expandedRowRender={(row) => <div data-testid="exp">{row.id}</div>}` 與 `onRowClick` 同時傳入，資料有 2 列
- **WHEN** 使用者點第一列
- **THEN** 表格下一列 SHALL 渲染一個 `colSpan` 等於 column 數量的 `<td>`，內含 `data-testid="exp"` 元素

---

### Requirement: vitest 覆蓋每頁三態與紅漲綠跌
系統 SHALL 在 `web-admin/src/pages/__tests__/` 下新增三份測試檔：`paper-positions-page.test.tsx`、`paper-orders-page.test.tsx`、`audit-page.test.tsx`。每份檔案 SHALL 至少包含 4 個 `test()`：loading 狀態、resolved（含紅漲綠跌雙重編碼 assert）、empty 狀態、error 狀態。`paper-orders-page.test.tsx` 與 `audit-page.test.tsx` SHALL 額外包含 1 個 test 驗證 filter→fetch query 對齊。

#### Scenario: 測試覆蓋
- **WHEN** 執行 `pnpm test`
- **THEN** 三份新測試檔的 test count 加總 SHALL ≥ 14
- **AND** 全部 SHALL 通過
