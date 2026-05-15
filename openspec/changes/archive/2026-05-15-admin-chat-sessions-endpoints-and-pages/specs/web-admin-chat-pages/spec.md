## ADDED Requirements

### Requirement: /chat 頁面 — session 列表 + 「+ 新對話」

系統 SHALL 在 `web-admin/src/pages/ChatSessionsPage.tsx` 提供 `<ChatSessionsPage>` React 元件，掛載於 `/chat` 路由，取代 `pages/stubs.tsx` 的 `ChatPage` stub。

視覺與互動 SHALL 依 `docs/web-admin-page-designs.md` §1 的契約：

- 頁首 action row：「+ 新對話 (Cmd+N)」`<Button variant="default">`
- 5-col `<DataTable>`：Session 標題 / 訊息數 / 最後活動（updated_at 相對時間）/ 模型（badge）/ 狀態（active 用 `text-up` + dot；後續可擴）
- 資料來源：`useQuery(['chat-sessions', limit, offset], () => listChatSessions({limit, offset}))`
- 預設 `limit=20`、`offset=0`；列表底分頁 `Cmd+← / →` 或 click `< 上一頁 / 下一頁 >`
- click row → `navigate('/chat/' + row.id)`
- Cmd/Ctrl+N hotkey → `createChatSession({})` → on success `navigate('/chat/' + session.id)`；on error toast「建立 session 失敗：{error.code}」
- Loading 顯示 3 row Skeleton
- Empty 顯示「尚無對話 — 點右上『+ 新對話』開始」+ `<MessagesSquare className="text-muted-foreground"/>`
- Error 顯示 destructive Card + retry `<Button>`

`stubs.tsx` SHALL 移除 `ChatPage` export（router 不再從 stubs import 此頁）。

#### Scenario: 頁面渲染列表
- **GIVEN** API mock 回 3 筆 session
- **WHEN** mount `<ChatSessionsPage>`
- **THEN** 3 row 被渲染、每 row 含標題與相對時間

#### Scenario: 空狀態 icon 與文案
- **GIVEN** API mock 回空 list
- **WHEN** mount
- **THEN** 渲染 `<MessagesSquare />` 與「尚無對話」字串

#### Scenario: Cmd+N hotkey
- **GIVEN** mount 狀態
- **WHEN** press Cmd+N（macOS）或 Ctrl+N（Windows）
- **THEN** `createChatSession({})` 被呼叫一次
- **AND** on success navigate 到 `/chat/<new_id>`

#### Scenario: click row 導航
- **WHEN** click row id=chat_12345678
- **THEN** navigate 到 `/chat/chat_12345678`

#### Scenario: 加載失敗 retry
- **GIVEN** API mock 第一次回 500、第二次回成功
- **WHEN** click 「重試」`Button`
- **THEN** 第二次 API 被呼叫並渲染資料

---

### Requirement: /chat/:sessionId 頁面 — 訊息流 + streaming 輸入

系統 SHALL 在 `web-admin/src/pages/ChatSessionPage.tsx` 提供 `<ChatSessionPage>` 元件，掛載於 `/chat/:sessionId`。

視覺與互動 SHALL 依 `docs/web-admin-page-designs.md` §2 的契約：

- 頁首：← 返回 `Button` + session.title + ⋮ Popover{「重命名」（v0 顯示 toast「v0 尚未支援，請刪除重建」）、「刪除」（confirm dialog → DELETE → navigate('/chat')）}
- 訊息流：`<Card>` per message，三 variant：
  - `role=user` — 右靠、`bg-muted`
  - `role=assistant` — 左靠、`bg-card`
  - `role=tool_result` 與 assistant 的 tool_calls — 內嵌在 assistant Card 內，click 展開 `<pre>` JSON
- streaming 中：assistant Card 底部 caret `▮` 閃；新 token 從尾 append
- 底部輸入區：`<Textarea rows={3}>` + 「送出 (Cmd+↩)」`Button`
- Cmd/Ctrl+Enter 送出；單 Enter 換行
- streaming 中 textarea disabled、Button 改文字「停止」+ `aria-label="abort streaming"`；click 停止 → AbortController.abort()
- 中斷後 inline 顯示 `<AlertTriangle/>` + 「網路中斷，已保留你輸入的內容」warning
- Loading（初次載入歷史）：3 個 Skeleton 訊息（user 短 / assistant 長 / user 短）
- Empty（新建 session 尚無訊息）：「這是新對話」+ `<MessagesSquare muted/>` + 輸入區 active
- Error（載入歷史 / DELETE 失敗）：頁面頂紅色 banner 重試 `Button`
- 404（session 不存在）：渲染中性 NotFoundView 含「← 回到對話列表」link
- 422 `session_deleted`：destructive Card「此對話已刪除」+「← 回到對話列表」link、輸入區隱藏

資料流：
- mount 時 `useQuery(['chat-session', sessionId], () => getChatSession(sessionId))` 拿歷史 200 則訊息
- 送出時呼叫 `streamChatMessage(sessionId, content)`（從 `lib/chat-stream.ts`）：
  - 開 `fetch(POST /messages)` 並 read `response.body.getReader()`
  - SSE parser 處理 `event: delta` 等 5 種事件，呼叫 React state setter 同步 patch local message list
  - `done` 事件後將 streamed message 從 transient state 移到 persistent state，並 `queryClient.invalidateQueries(['chat-session', sessionId])` 補對齊
  - AbortError 不算錯誤；其他 fetch exception → 顯示 inline warning
- 重命名 toast 不呼 API（v0 deferred）
- 刪除 confirm → `deleteChatSession(sessionId)` → navigate('/chat')

#### Scenario: 載入歷史 200 + 顯示
- **GIVEN** sessionId=chat_12345678、API mock 回 5 訊息
- **WHEN** mount
- **THEN** 5 個 message Card 渲染、按 created_at ASC

#### Scenario: streaming 串接 delta
- **GIVEN** session 已載入
- **WHEN** 輸入 「hi」+ Cmd+Enter
- **AND** server stream emit `delta {text:"H"}` → `delta {text:"i"}` → `done`
- **THEN** assistant Card 顯示「Hi」+ caret `▮` 在 stream 期間
- **AND** `done` 後 caret 消失

#### Scenario: tool_call event 展開
- **GIVEN** stream 含 tool_call{name="query_journal", args={...}} + tool_result{...}
- **WHEN** assistant Card 渲染
- **THEN** 內嵌一個可 click 展開的 tool 區塊
- **AND** 點開顯示 args 與 result JSON

#### Scenario: stop streaming abort
- **GIVEN** streaming 進行中
- **WHEN** click 「停止」`Button`
- **THEN** AbortController.abort() 被呼叫
- **AND** inline warning 不出現（使用者主動取消）
- **AND** 已串流的部分 message 仍可見

#### Scenario: 404 session 不存在
- **GIVEN** API 回 404 `not_found`
- **WHEN** mount
- **THEN** 渲染中性 NotFoundView 與「← 回到對話列表」link

#### Scenario: 422 session_deleted
- **GIVEN** API 回 422 `session_deleted`
- **WHEN** mount
- **THEN** 渲染 destructive Card「此對話已刪除」
- **AND** 輸入區不渲染

#### Scenario: 刪除 confirm 流程
- **GIVEN** session active
- **WHEN** 開 ⋮ → click 「刪除」 → 在 confirm dialog 按「確認」
- **THEN** `deleteChatSession(sessionId)` 被呼叫
- **AND** on success navigate 到 `/chat`

#### Scenario: Cmd+Enter 送出
- **GIVEN** textarea focus + 「2330 籌碼」
- **WHEN** press Cmd+Enter
- **THEN** stream 啟動、user message 渲染進列表

#### Scenario: 單 Enter 換行不送
- **WHEN** press Enter（單獨）
- **THEN** textarea 內容多一行 `\n`、stream 不啟動

---

### Requirement: /sessions 頁面 — FTS5 搜尋

系統 SHALL 在 `web-admin/src/pages/SessionsPage.tsx` 提供 `<SessionsPage>` 元件，掛載於 `/sessions` 路由，取代 stub。

視覺與互動 SHALL 依 `docs/web-admin-page-designs.md` §15 的契約：

- Header：大型 search `<Input>` + 兩個 `<Input type=date>` (from/to) + 「搜尋 (↩)」`<Button>`
- search input 按 Enter 觸發
- 結果列表：每個命中 session 一張 `<Card>`，內容：
  - 標題 + 日期（最新命中 message 的 created_at）+ session status 標記（deleted 顯示「(已刪除)」灰字）
  - N 個 hit snippet（含 `<mark>...</mark>` 高亮）+ 每個 snippet click 跳 `/chat/<session_id>?msgId=<message_id>`
  - 「開啟 →」`<Button variant="link">` 跳 `/chat/<session_id>`（deleted session 此 button disabled + tooltip「此對話已刪除」）
- Loading：3 張 Card Skeleton
- Empty：「無命中」+ `<History className="text-muted-foreground"/>` + 「試試其他關鍵字」
- Error：retry banner + `<Button>`
- 400 `invalid_input` / `invalid_query`：red banner 顯示 message
- 高亮使用 `bg-warning/20` 黃底（搜尋慣例 — 不套紅綠語意）

URL query string：`?q=&from=&to=` 持久化搜尋輸入；reload 後復原。

`stubs.tsx` SHALL 移除 `SessionsPage` export。

#### Scenario: 搜尋觸發
- **GIVEN** search input focus + 「2330」
- **WHEN** press Enter
- **THEN** `searchChat({q:"2330"})` 被呼叫
- **AND** URL 變 `/sessions?q=2330`

#### Scenario: 結果分組渲染
- **GIVEN** API 回 2 group（A 含 2 hit、B 含 1 hit）
- **WHEN** 渲染
- **THEN** 2 張 Card、A Card 含 2 個 snippet block、B Card 含 1 個

#### Scenario: snippet click 帶 msgId 跳轉
- **WHEN** click snippet 內文 (message_id=msg_abc123def456)
- **THEN** navigate 到 `/chat/<session_id>?msgId=msg_abc123def456`

#### Scenario: 已刪除 session 標記與 disabled button
- **GIVEN** group session_status="deleted"
- **WHEN** 渲染
- **THEN** Card 標題旁顯示 「(已刪除)」灰字
- **AND** 「開啟 →」`Button` disabled
- **AND** `aria-label` 含「此對話已刪除」

#### Scenario: 空命中 empty 狀態
- **GIVEN** API 回 `{groups: [], total_hits: 0}`
- **WHEN** 渲染
- **THEN** 「無命中」字串與 `<History/>` icon 出現

#### Scenario: invalid_query 顯示 inline banner
- **GIVEN** API 回 400 `invalid_query`
- **WHEN** 渲染
- **THEN** red banner 顯示 error.message

#### Scenario: URL query 復原
- **GIVEN** URL 為 `/sessions?q=2330&from=2026-05-01&to=2026-05-15`
- **WHEN** mount
- **THEN** search input value="2330"、from input value="2026-05-01"、to input value="2026-05-15"
- **AND** 搜尋自動觸發

---

### Requirement: lib/chat-stream.ts SSE parser

系統 SHALL 在 `web-admin/src/lib/chat-stream.ts` 提供 `streamChatMessage(sessionId: string, content: string, callbacks: ChatStreamCallbacks, signal: AbortSignal) -> Promise<void>` 函式。

`ChatStreamCallbacks`：
- `onDelta(text: string): void`
- `onToolCall(call: {id, name, args}): void`
- `onToolResult(result: {tool_call_id, result}): void`
- `onDone(meta: {message_id, elapsed_ms}): void`
- `onError(err: {code, message}): void`

行為：
- 用 `fetch(POST /api/admin/chat/sessions/<id>/messages, {body: JSON.stringify({content}), headers: { Authorization: Bearer..., 'Content-Type': 'application/json' }, signal})`
- 若 response.status !== 200（pre-stream envelope error）→ parse JSON → call `onError({code, message})` 後 return
- 若 response.headers['content-type'] !== 'text/event-stream' → call `onError({code:'unexpected_content_type', message: ...})` 後 return
- 用 `response.body.getReader()` + `TextDecoder` 解析 SSE 格式 (`event: <name>\ndata: <json>\n\n`)
- 每完整 event call 對應 callback
- AbortError → 不呼叫 onError（caller 主動 abort）
- 其他 fetch / parse exception → onError({code:'stream_failed', message: str})

#### Scenario: 解析 happy path 5 種事件
- **GIVEN** mock fetch 回 SSE response 含 `delta` + `tool_call` + `tool_result` + `delta` + `done`
- **WHEN** call streamChatMessage
- **THEN** onDelta 被呼叫 ≥2 次、onToolCall 1 次、onToolResult 1 次、onDone 1 次

#### Scenario: pre-stream envelope error
- **GIVEN** fetch 回 422 JSON `{ok:false, error:{code:"missing_api_key", message:"..."}}`
- **WHEN** call
- **THEN** onError({code:"missing_api_key", ...}) 被呼叫
- **AND** onDelta 不被呼叫

#### Scenario: AbortError 不觸發 onError
- **GIVEN** streaming 中 signal.abort()
- **WHEN** fetch reject AbortError
- **THEN** onError SHALL **不**被呼叫

#### Scenario: 非 SSE content-type
- **GIVEN** fetch 回 200 但 content-type=text/html
- **WHEN** call
- **THEN** onError({code:"unexpected_content_type", ...}) 被呼叫
