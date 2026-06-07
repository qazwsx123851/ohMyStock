# web-admin-memory-page Specification

## Purpose
TBD - created by archiving change web-admin-memory-page-and-store. Update Purpose after archive.
## Requirements
### Requirement: `/memory` 替換 stub，render 兩個切換 view

The web-admin SHALL render `/memory` via a new `MemoryPage` component（取代 `web-admin/src/pages/stubs.tsx` 的現有 `MemoryPage` 匯出）。`MemoryPage` MUST 透過 `web-admin/src/lib/api.ts` 提供的 `listMemory(...)` / `searchMemory(...)` wrapper 呼叫後端，並包在 react-query `useQuery` hook 中。

頁面 MUST 在垂直方向呈現：

1. 頁面 header（`<h1>長期記憶</h1>` + 一行說明）。
2. 一個 segmented control（兩個 tab：「瀏覽」與「搜尋」）。預設選中「瀏覽」。切換 tab 時，前一個 view 的內聯展開狀態（`expandedKey`）SHALL reset。
3. 對應 view（瀏覽或搜尋）的 filter / 輸入區。
4. 一個共用的 5-col `<DataTable>` 顯示結果（時間 / kind / tags / 內容預覽 / 來源），並透過 `expandedRowRender` 顯示完整 `content`。
5. 分頁 / 結果計數列（如：`「共 N 筆，第 X – Y 筆」` + 上一頁 / 下一頁 buttons）。

頁面 MUST NOT 含：新增按鈕、編輯按鈕、刪除按鈕、`<Textarea>`、Save/Cmd+S 提示、dirty-state UI、tag autocomplete popover、日期 range 控制、語意搜尋切換。

#### Scenario: replaces stub
- **WHEN** build 編譯後 `web-admin/src/router.tsx` 使用 `/memory`
- **THEN** 對應 component SHALL 由 `@/pages/MemoryPage` import（不再從 `@/pages/stubs`）
- **AND** `web-admin/src/pages/stubs.tsx` SHALL NOT 再 export `MemoryPage` 符號

#### Scenario: 預設選中「瀏覽」
- **WHEN** 使用者首次進 `/memory`
- **THEN** segmented control SHALL 顯示「瀏覽」為選中（aria-pressed="true" 或同等）
- **AND** SHALL 觸發 `listMemory()` 呼叫
- **AND** SHALL NOT 觸發 `searchMemory()` 呼叫

---

### Requirement: 「瀏覽」view — kind/tag filter + 5-col table

「瀏覽」view SHALL 含：

- 一個 kind `<Select>`，options 為「全部」（預設） + 4 個 `MemoryKind` 值（顯示順序固定為 `note` → `lesson` → `proposal` → `review_summary`）。中文 label 對應 `note=筆記` / `lesson=經驗` / `proposal=提案` / `review_summary=復盤`。
- 一個 tag chip-input：使用者輸入字串後按 Enter 加入；按 ✕ 移除。chip-input 在 v0 SHALL 上限為 1 個 tag（多選 deferred；超過時隱藏 input）。
- 5-col `<DataTable>`：欄位依序為 `時間 / kind / tags / 內容預覽 / 來源`。
  - `時間` SHALL render `created_at`（可加上 toLocaleString 顯示，但保留 ISO 字串於 cell title）。
  - `kind` SHALL render 中文 label，以 shadcn `Badge variant="secondary"` 包覆（**不**用紅漲綠跌語義色）。
  - `tags` SHALL render 為 `<code>` 樣式 chip 列；空 list 時顯示 `—`。
  - `內容預覽` SHALL render `content_preview`，`content_truncated` 為 `true` 時末端附加 `…`。
  - `來源` SHALL render `source ?? '—'`。
- 一個 footer 列顯示 `「共 {total} 筆，第 {offset+1} – {offset+items.length} 筆」` + 上一頁 / 下一頁 buttons。`offset === 0` 時 disable「上一頁」；`has_more === false` 時 disable「下一頁」。

任一 filter 變動（kind select、tag chip 加 / 移）SHALL：

1. reset offset 為 0。
2. 重新觸發 `useQuery`（key 含 kind / tag / limit / offset）。
3. reset `<DataTable>` 的展開列。

#### Scenario: filter triggers refetch
- **GIVEN** 「瀏覽」view 已載入 50 筆預設 row
- **WHEN** 使用者選 kind = `lesson`
- **THEN** SHALL 觸發 `listMemory({kind: 'lesson', tag: undefined, limit: 50, offset: 0})` 呼叫
- **AND** offset reset 為 0

#### Scenario: tag chip add filters
- **WHEN** 使用者在 chip-input 鍵入 `vcp` + Enter
- **THEN** chip-input SHALL 顯示 `vcp` chip
- **AND** SHALL 觸發 `listMemory({tag: 'vcp', ...})` 呼叫

#### Scenario: tag chip remove restores
- **GIVEN** 已加 `vcp` chip
- **WHEN** 使用者按 chip 上的 ✕
- **THEN** chip 消失
- **AND** 觸發 `listMemory({tag: undefined, ...})` 呼叫

#### Scenario: pagination next disables on last page
- **GIVEN** server 回 `has_more: false`
- **WHEN** 「瀏覽」view render
- **THEN** 「下一頁」button SHALL `disabled`

#### Scenario: pagination prev disables on first page
- **GIVEN** offset === 0
- **WHEN** 「瀏覽」view render
- **THEN** 「上一頁」button SHALL `disabled`

#### Scenario: kind select 限定四值 + 全部
- **WHEN** 使用者展開 kind `<Select>`
- **THEN** options SHALL 恰為 `['全部', 'note', 'lesson', 'proposal', 'review_summary']`（顯示中文 label，但 value 為 enum 字串或 `'all'`）

---

### Requirement: 「搜尋」view — FTS5 input + Cmd/Ctrl+Enter

「搜尋」view SHALL 含：

- 一個 single-line `<Input>`（placeholder：`「FTS5 查詢，例：VCP AND breakout」`）。
- 一個「搜尋」button。
- 結果區為與「瀏覽」相同的 5-col `<DataTable>`。

按 Cmd+Enter（macOS）或 Ctrl+Enter（Windows / Linux）SHALL 觸發查詢；單純按 Enter SHALL **也**觸發查詢（form-style）。空 / 純空白 input 時，按 button 或 keyboard shortcut SHALL NOT 發 request；改 render inline 提示「請輸入查詢關鍵字」。

每次按下查詢 SHALL：

1. reset offset 為 0。
2. 觸發 `searchMemory({q, limit, offset: 0})` 呼叫。
3. reset `<DataTable>` 展開列。

#### Scenario: Ctrl+Enter triggers search
- **GIVEN** 「搜尋」view，input 為 `'vcp breakout'`
- **WHEN** 使用者按 Ctrl+Enter
- **THEN** SHALL 觸發 `searchMemory({q: 'vcp breakout', limit: 50, offset: 0})` 呼叫

#### Scenario: empty input no fetch
- **GIVEN** input 為空字串
- **WHEN** 使用者按搜尋 button
- **THEN** SHALL NOT 觸發 fetch
- **AND** 頁面 SHALL render 提示「請輸入查詢關鍵字」

#### Scenario: whitespace-only input no fetch
- **GIVEN** input 為 `'   '`
- **WHEN** 使用者按搜尋 button
- **THEN** SHALL NOT 觸發 fetch

#### Scenario: malformed query renders friendly error
- **GIVEN** server 回 400 with `error.code == "invalid_query"`
- **WHEN** 「搜尋」view render
- **THEN** SHALL render 一個 inline message「查詢語法錯誤」（destructive 色 + `AlertCircle` icon）
- **AND** SHALL NOT render 原始 server error message
- **AND** SHALL NOT render 結果 table

---

### Requirement: 5-col DataTable + 內聯展開 full content

兩個 view 共用同一個 5-col `<DataTable>`（`時間 / kind / tags / 內容預覽 / 來源`）。Row click（或 keyboard Enter / Space）SHALL 切換 inline expansion，使用 `<DataTable>` 提供的 `expandedRowRender(row, isExpanded)` slot：

- 展開內容 SHALL 為 shadcn `Card` 含 `<pre className="whitespace-pre-wrap font-mono text-sm">{row.content}</pre>`。
- `<pre>` block SHALL 套用 `max-h-[70vh] overflow-auto`，內容超出 viewport 高度時內滾。
- `<pre>` 上方 SHALL 有一行 char count：`「{row.content.length} 字元」`。
- 展開內容 SHALL NOT 包含編輯 / Save / 刪除 button、Markdown 渲染、語法高亮、preview toggle（同 `SkillDetailPage` D7 決策）。

DataTable 行為：

- 每筆 row 為 keyboard-focusable（`tabIndex=0`，由 `<DataTable>` 提供）。
- Enter 或 Space 切換展開（由 `<DataTable>` 提供）。
- 一次只能展開一筆 row（`expandedKey` 單值）。

#### Scenario: row click expands full content
- **GIVEN** 結果列表已 render
- **WHEN** 使用者點擊第三筆 row
- **THEN** SHALL render 第三筆 row 下方的展開列
- **AND** 展開列 SHALL 含 `<pre>` 包覆完整 `row.content`
- **AND** 展開列 SHALL 顯示 `「{row.content.length} 字元」`

#### Scenario: keyboard Enter expands
- **GIVEN** 結果列表已 render
- **WHEN** 使用者 Tab focus 到第一筆 row 並按 Enter
- **THEN** 第一筆 row 展開列 SHALL 出現

#### Scenario: switching tab collapses expanded row
- **GIVEN** 「瀏覽」view 中第二筆 row 已展開
- **WHEN** 使用者切換到「搜尋」view，再切回「瀏覽」
- **THEN** 第二筆 row SHALL NOT 仍處於展開狀態

#### Scenario: full content shown without second fetch
- **GIVEN** 列表回 row `content` 為 1500 字元
- **WHEN** 使用者展開該 row
- **THEN** 展開內容 SHALL 顯示完整 1500 字元
- **AND** SHALL NOT 觸發任何額外 HTTP request

---

### Requirement: Loading / empty / error 三態

頁面 SHALL 為兩個 view 各自渲染明確的 loading、empty、error 三態：

- **Loading（瀏覽）**：DataTable 區改 render 6 個 `Skeleton` rows（**不**用 spinner）。Filter / pagination 控制保留可見但 disabled。
- **Loading（搜尋）**：與瀏覽相同；查詢期間 input + 「搜尋」button 保留可見但 disabled。
- **Empty（瀏覽，data.items==[]，filter 為預設）**：置中訊息「尚無 memory；待 Phase 5 復盤 / proposal 任務寫入」。**無**清除 filter button（因為 filter 為預設）。
- **Empty（瀏覽，data.items==[]，filter 非預設）**：置中訊息「無符合條件的 memory」 + `Button variant="outline"` 標籤「清除 filter」（按下重置 kind = `'all'` 與 tag chip 為 empty）。
- **Empty（搜尋，data.items==[] 且 q 非空）**：置中訊息「找不到符合 `「{q}」` 的 memory」。
- **Error**：頁面頂端 destructive `Card`（`border-destructive/50 bg-destructive/5` + `AlertCircle` `size-4 text-destructive` + `role="alert"`）+ error message + 「重試」button（呼叫 query 的 `refetch()`）。404 對 memory 端點不會發生（沒有 `/:id` route），所以不需特化 404 path。

#### Scenario: loading skeletons in table area
- **WHEN** query in flight
- **THEN** DataTable 區 SHALL render 6 個 `Skeleton` rows
- **AND** 不可見任何 `Card` 或 row
- **AND** filter 控制 SHALL 為 `disabled`

#### Scenario: empty after filter shows clear button
- **GIVEN** kind = `lesson` 且 server 回 `data.items == []`
- **WHEN** 「瀏覽」view render
- **THEN** SHALL render 「無符合條件的 memory」訊息
- **AND** 「清除 filter」button SHALL 可見
- **WHEN** 使用者按「清除 filter」
- **THEN** kind 改回 `all`、tag chip 為 empty
- **AND** 重新觸發 `listMemory({...defaults})` 呼叫

#### Scenario: empty default state shows seed hint
- **GIVEN** server 回 `data.items == []` 且 filter 為預設
- **WHEN** 「瀏覽」view render
- **THEN** SHALL render「尚無 memory；待 Phase 5 復盤 / proposal 任務寫入」
- **AND** 「清除 filter」button SHALL NOT 可見

#### Scenario: search empty shows query string
- **GIVEN** 使用者送 `q = 'zzzzzzzz'`，server 回空 list
- **WHEN** 「搜尋」view render
- **THEN** SHALL render「找不到符合 `「zzzzzzzz」` 的 memory」

#### Scenario: error renders retry
- **GIVEN** server 回 HTTP 500
- **WHEN** view render
- **THEN** 頂端 destructive `Card` SHALL render with `role="alert"`
- **AND** error message SHALL 可見
- **AND** 「重試」button 點擊 SHALL 呼叫 query 的 `refetch()`

---

### Requirement: API client wrappers and types

The shared client `web-admin/src/lib/api.ts` SHALL 暴露：

- `MemoryKind` 型別：`'note' | 'lesson' | 'proposal' | 'review_summary'`
- `MemoryRow` 型別：
  ```
  {
    id: number
    kind: MemoryKind
    content: string
    content_preview: string
    content_truncated: boolean
    tags: string[]
    source: string | null
    created_at: string
  }
  ```
- `MemoryRowsResponse` 型別：`{ items: MemoryRow[]; total: number; limit: number; offset: number; has_more: boolean }`
- `listMemory(params: { kind?: MemoryKind; tag?: string; limit?: number; offset?: number }): Promise<MemoryRowsResponse>` — 將提供的 params 編入 URL query string（empty / undefined value 不送），呼叫 `apiFetch<MemoryRowsResponse>('/api/admin/memory/rows?...')`。
- `searchMemory(params: { q: string; limit?: number; offset?: number }): Promise<MemoryRowsResponse>` — 將 `q` 經 `encodeURIComponent` 編入 query string，呼叫 `apiFetch<MemoryRowsResponse>('/api/admin/memory/search?...')`。

兩個 wrapper SHALL NOT 自行加 retry / 401 處理 / cache（由 `apiFetch` 與 react-query 統一處理）。`q` 為空字串 / 純空白時，wrapper 仍照原樣送出（讓 server 回 400 `invalid_input` 由 react-query error path 接住），SHALL NOT 在 client-side throw — 否則 react-query state machine 會讀不到 server 的錯誤 envelope。

#### Scenario: listMemory builds URL correctly
- **WHEN** `listMemory({ kind: 'lesson', tag: 'vcp', limit: 20, offset: 40 })` 被呼叫
- **THEN** 底層 `fetch` URL SHALL 為 `/api/admin/memory/rows?kind=lesson&tag=vcp&limit=20&offset=40`（query 參數順序不限）

#### Scenario: listMemory 略過 undefined params
- **WHEN** `listMemory({})` 被呼叫
- **THEN** 底層 `fetch` URL SHALL 為 `/api/admin/memory/rows`（**無** trailing `?` 或空值參數）

#### Scenario: searchMemory encodes q
- **WHEN** `searchMemory({ q: 'foo bar 中文' })` 被呼叫
- **THEN** 底層 `fetch` URL SHALL 含 `q=foo%20bar%20%E4%B8%AD%E6%96%87`

---

### Requirement: Routing and stub removal

`web-admin/src/router.tsx` SHALL 從 `@/pages/MemoryPage` import `MemoryPage`（**不**從 `@/pages/stubs`）。`MemoryPage` 符號 MUST 從 `web-admin/src/pages/stubs.tsx` 移除。Router-smoke test SHALL 在新 component 掛載 `/memory` 後仍 pass。

#### Scenario: router uses real component
- **WHEN** build 編譯
- **THEN** `router.tsx` SHALL 從 `@/pages/MemoryPage` import `MemoryPage`
- **AND** `stubs.tsx` SHALL NOT 再 export `MemoryPage`

#### Scenario: smoke test still passes
- **WHEN** existing router smoke test 掛載每條 route
- **THEN** `/memory` SHALL render 而不 throw

---

### Requirement: 紅漲綠跌 not applied; status-icon pairing only on errors

Memory 列無價格 / 漲跌語意。頁面 SHALL NOT 對 kind badge、tag chip、`內容預覽` cell 套用 `--up` / `--down` / `text-up` / `text-down` 顏色 class。唯一允許 destructive 色的位置為 error `Card`，且 SHALL pair 一個 `AlertCircle` icon（per `docs/web-admin-page-designs.md` §0.3 「color-is-never-the-only-signal」）；inline「查詢語法錯誤」訊息亦同。

#### Scenario: kind badges 用中性色
- **WHEN** 任一 view render kind badge
- **THEN** badge SHALL 套 shadcn `secondary`（或同等中性）variant
- **AND** SHALL NOT 含 `text-up` / `text-down` / `bg-destructive` class

#### Scenario: error Card 配 icon
- **WHEN** error 狀態 render
- **THEN** destructive border 色 SHALL 伴隨 `AlertCircle` from `lucide-react`
- **AND** error 元件 SHALL 含 `role="alert"`

---

### Requirement: 寫入個人偏好表單

Memory 頁 SHALL 提供寫入表單（kind / content / tags / source），提交呼叫 memory write endpoint。成功後 MUST 刷新列表使新筆可見。必填欄位（kind、content）未填 MUST 於前端擋下。

#### Scenario: 成功寫入並刷新

- **WHEN** 填妥 kind + content 並提交
- **THEN** 呼叫 write endpoint，成功後列表刷新並可見新筆

#### Scenario: 必填驗證

- **WHEN** content 為空即提交
- **THEN** 前端擋下、不送出
