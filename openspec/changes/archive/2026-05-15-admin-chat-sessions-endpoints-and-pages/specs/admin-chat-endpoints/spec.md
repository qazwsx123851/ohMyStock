## ADDED Requirements

### Requirement: GET /api/admin/chat/sessions 列出 active session 含分頁

系統 SHALL 在 `/api/admin/chat/sessions` 暴露 `GET` 端點，Bearer auth + `{ok,data,error}` envelope + per-request `Depends(get_db)`。

Query params：
- `limit: int = 50` — clamp 1..200；`limit < 1` SHALL 回 400 `invalid_input`
- `offset: int = 0` — `offset < 0` SHALL 回 400 `invalid_input`

回傳 `data` 為 `{items: ChatSessionSummary[], total: int, limit: int, offset: int, has_more: bool}`，每個 `ChatSessionSummary` 含 `id`/`title`/`model`/`status`/`created_at`/`updated_at`/`message_count` 7 個 key（**不**含 `params_json` / 訊息 body）。`has_more = offset + len(items) < total`。

只回 `status="active"` 的 session（已刪除的 session 不出現於此 endpoint 列表）。

#### Scenario: 200 列出 active sessions
- **GIVEN** 5 筆 active session + 1 筆 deleted
- **WHEN** `GET /api/admin/chat/sessions` with valid token
- **THEN** HTTP 200，`data.total == 5`、`data.items` 長度 5

#### Scenario: 分頁 has_more 計算
- **GIVEN** 12 筆 active session
- **WHEN** `GET /api/admin/chat/sessions?limit=5&offset=0`
- **THEN** `data.items` 長度 5，`data.total == 12`，`data.has_more == true`

#### Scenario: 缺 Authorization 401
- **WHEN** request 不帶 Authorization
- **THEN** HTTP 401 with `error.code == "auth_missing"`

#### Scenario: limit < 1 回 400
- **WHEN** `GET /api/admin/chat/sessions?limit=0`
- **THEN** HTTP 400 with `error.code == "invalid_input"`

---

### Requirement: POST /api/admin/chat/sessions 建空 session

系統 SHALL 在 `/api/admin/chat/sessions` 暴露 `POST` 端點，Bearer auth + envelope。

Body schema (`ChatSessionCreateRequest`, pydantic `extra="forbid"`)：
- `title: str | None = None` — 1..120 codepoints；None 預設 `"新對話"`
- `model: str | None = None` — None 預設 `Settings().chat_model_default`

handler：
- 生成 `id = "chat_" + secrets.token_hex(4)`
- `created_at = updated_at = datetime.now(TPE).isoformat()`
- INSERT `chat_sessions` row with status="active"
- 200 with `data` = ChatSessionSummary（含 `message_count: 0`）

#### Scenario: 200 回 ChatSessionSummary
- **WHEN** `POST /api/admin/chat/sessions` body `{}`
- **THEN** HTTP 200，`data.id` matches `^chat_[0-9a-f]{8}$`、`data.title == "新對話"`、`data.message_count == 0`

#### Scenario: model 自訂
- **WHEN** body `{"model": "claude-haiku-4-5-20251001"}`
- **THEN** `data.model == "claude-haiku-4-5-20251001"`

#### Scenario: extra 欄位拒絕
- **WHEN** body `{"title": "x", "extra": "boom"}`
- **THEN** HTTP 422 (FastAPI pydantic validation error)

#### Scenario: title 超長拒絕
- **WHEN** body `{"title": "<121 codepoints>"}`
- **THEN** HTTP 422

---

### Requirement: GET /api/admin/chat/sessions/{id} 回 session + 最新 200 訊息

系統 SHALL 在 `/api/admin/chat/sessions/{id:path}` 暴露 `GET` 端點，Bearer auth + envelope。

行為：
- `id` 含 `/` / `\` / `..` / `os.sep` 任一 token SHALL BEFORE DB 讀取前回 400 `invalid_input`（與 admin-proposals-endpoints 相同 `_INVALID_NAME_TOKENS` 模式）
- session 不存在 SHALL 回 404 `not_found`、message 含 `<id>` 子字串
- session `status="deleted"` SHALL 回 422 `session_deleted`、message 含 `<id>` 子字串
- 200 回 `data` 為 `{session: ChatSessionSummary, messages: ChatMessage[]}`，messages ORDER BY `created_at ASC, id ASC`、limit 200

#### Scenario: 200 回完整 session + messages
- **GIVEN** active session 含 3 則 message
- **WHEN** `GET /api/admin/chat/sessions/chat_12345678` with valid token
- **THEN** HTTP 200，`data.session.id == "chat_12345678"`、`data.messages` 長度 3、按 created_at ASC

#### Scenario: 404 對未知 id
- **WHEN** `GET /api/admin/chat/sessions/chat_doesnotex`
- **THEN** HTTP 404 with `error.code == "not_found"`

#### Scenario: 422 對已刪除 session
- **GIVEN** session status="deleted"
- **WHEN** `GET /api/admin/chat/sessions/<id>`
- **THEN** HTTP 422 with `error.code == "session_deleted"`

#### Scenario: path-traversal 400
- **WHEN** `GET /api/admin/chat/sessions/..%2Fsecrets`
- **THEN** HTTP 400 with `error.code == "invalid_input"`
- **AND** DB 不被讀取

---

### Requirement: POST /api/admin/chat/sessions/{id}/messages 串流回應

系統 SHALL 在 `/api/admin/chat/sessions/{id:path}/messages` 暴露 `POST` 端點，Bearer auth。

Body schema (`ChatMessageSendRequest`, pydantic `extra="forbid"`)：
- `content: str` — 1..8000 codepoints

行為：

1. path-traversal 防禦同 GET endpoint
2. session 不存在 → 404 `not_found`（envelope JSON，不開 SSE）
3. session deleted → 422 `session_deleted`
4. `Settings().anthropic_api_key` 缺 → 422 `missing_api_key`
5. INSERT user message row（id="msg_<12hex>"、role="user"、content=body.content）
6. 建立 `ChatAgent(model=session.model, ...)`、設 `Content-Type: text/event-stream`、回 `StreamingResponse`
7. 從 `agent.stream(messages)` async iterate，每個 event 序列化成 SSE 格式 `event: <name>\ndata: <json>\n\n` flush 給 client
8. `done` event 後 INSERT assistant message row（含 tool_calls_json）+ `llm_cost_id`
9. 第一個 assistant turn 完成後 `asyncio.create_task(autogen_title(...))` fire-and-forget 更新 session.title
10. 整段用 `try/finally` 包；`request.is_disconnected()` 為 True SHALL：
    - cancel `agent.stream` async iterator
    - 把已累積的 partial assistant content INSERT 進 chat_messages（`tool_calls_json` 為已完成的 tool call list 或 None）
    - content 末尾附「[訊息已中斷]」標記

SSE 事件格式：
- `event: delta\ndata: {"text": "..."}`
- `event: tool_call\ndata: {"id": "...", "name": "...", "args": {...}}`
- `event: tool_result\ndata: {"tool_call_id": "...", "result": {...}}`
- `event: done\ndata: {"message_id": "msg_...", "elapsed_ms": int}`
- `event: error\ndata: {"code": "...", "message": "..."}`

`error` event 後 SHALL 結束 stream（不繼續發 delta）。

#### Scenario: happy path 串流結束寫入兩 row
- **GIVEN** active session、anthropic client mock 回完整 stream
- **WHEN** `POST /messages` body `{"content": "hi"}`
- **THEN** response Content-Type 為 `text/event-stream`
- **AND** event 序列含 1+ `delta` → `done`
- **AND** DB `chat_messages` 新增 2 row（role=user 與 role=assistant）

#### Scenario: 缺 ANTHROPIC_API_KEY 回 envelope
- **GIVEN** `Settings.anthropic_api_key` 為空
- **WHEN** POST 同 body
- **THEN** HTTP 422，`Content-Type` 為 `application/json`、`error.code == "missing_api_key"`
- **AND** DB 不寫 user message

#### Scenario: 已刪除 session 422
- **GIVEN** session deleted
- **WHEN** POST 同 body
- **THEN** HTTP 422 with `error.code == "session_deleted"`

#### Scenario: client 取消 partial commit
- **GIVEN** anthropic client mock 緩慢回 delta
- **WHEN** client abort 連線（streaming 中途）
- **THEN** server SHALL cancel LLM stream
- **AND** DB `chat_messages` 新增 1 row role="assistant" content 結尾含 `"[訊息已中斷]"`

#### Scenario: anthropic exception 轉 error event
- **GIVEN** anthropic client 拋 `RateLimitError`
- **WHEN** POST 同 body
- **THEN** SSE 含一個 `error` event，`code == "rate_limit"`
- **AND** stream 後即關閉
- **AND** assistant message **不**被寫入（或寫入但 content="[訊息已中斷]"）

---

### Requirement: DELETE /api/admin/chat/sessions/{id} soft delete

系統 SHALL 在 `/api/admin/chat/sessions/{id:path}` 暴露 `DELETE` 端點，Bearer auth + envelope。

行為：
- path-traversal 防禦同 GET
- session 不存在 → 404 `not_found`
- 已 active → 設 status="deleted" + 更新 updated_at + 200 `{"deleted": true}`
- 已 deleted → 200 `{"deleted": true}` (idempotent)
- 訊息 row **不**動

#### Scenario: 200 soft delete
- **GIVEN** active session
- **WHEN** `DELETE /api/admin/chat/sessions/<id>`
- **THEN** HTTP 200、`data.deleted == true`
- **AND** DB session.status 變 "deleted"
- **AND** chat_messages 數量不變

#### Scenario: 404 對未知 id
- **WHEN** `DELETE /api/admin/chat/sessions/chat_doesnotex`
- **THEN** HTTP 404

#### Scenario: 已刪除 idempotent 回 200
- **GIVEN** session deleted
- **WHEN** `DELETE` 同 id
- **THEN** HTTP 200、`data.deleted == true`

---

### Requirement: GET /api/admin/chat/search FTS5 跨 session 搜尋

系統 SHALL 在 `/api/admin/chat/search` 暴露 `GET` 端點，Bearer auth + envelope。

Query params：
- `q: str` (必填) — 1..200 codepoints；trim 後為空 → 400 `invalid_input`
- `date_from: str | None` — ISO YYYY-MM-DD；格式錯 → 400 `invalid_input`
- `date_to: str | None` — ISO YYYY-MM-DD；`date_from > date_to` → 400 `invalid_input`
- `limit: int = 20` — clamp 1..100

回傳 `data` 為 `{groups: SearchGroup[], total_hits: int}`，每個 `SearchGroup` 含 `session_id`/`session_title`/`session_status` ("active"/"deleted")/`hits: SnippetHit[]`。`SnippetHit` 含 `message_id`/`snippet` (含 `<mark>...</mark>`)/`created_at`。

ORDER BY BM25 ASC；同 session 多個命中聚合在一個 group 內。

FTS5 syntax error SHALL 回 400 with `error.code == "invalid_query"`、message 含 `"FTS5 query syntax error"` — **不**洩漏 SQLite OperationalError 原文。

#### Scenario: 200 回分組命中
- **GIVEN** session A 含 2 條 message 命中、session B 含 1 條
- **WHEN** `GET /api/admin/chat/search?q=%E5%8F%B0%E7%A9%8D%E9%9B%BB&limit=20`
- **THEN** HTTP 200，`data.groups` 長度 2、`data.total_hits == 3`
- **AND** group A 的 hits 長度 2、group B 的 hits 長度 1

#### Scenario: 空 q 回 400
- **WHEN** `GET /api/admin/chat/search?q=%20%20%20`
- **THEN** HTTP 400 with `error.code == "invalid_input"`

#### Scenario: FTS5 syntax error remap
- **WHEN** `GET /api/admin/chat/search?q=%22unclosed`（未閉合引號）
- **THEN** HTTP 400 with `error.code == "invalid_query"`、message 含 `"FTS5"`
- **AND** **不**含 sqlite3 OperationalError 原文

#### Scenario: 已刪除 session 仍命中但標記
- **GIVEN** session A active 命中、session B deleted 命中
- **WHEN** search 兩者都命中的關鍵字
- **THEN** 兩個 group 都出現
- **AND** group B 的 `session_status == "deleted"`

#### Scenario: date_from > date_to 回 400
- **WHEN** `?date_from=2026-05-15&date_to=2026-05-01`
- **THEN** HTTP 400 with `error.code == "invalid_input"`

#### Scenario: 缺 q 回 422
- **WHEN** `GET /api/admin/chat/search`（缺 q）
- **THEN** HTTP 422 (FastAPI pydantic validation)
