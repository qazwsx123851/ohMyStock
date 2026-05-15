## ADDED Requirements

### Requirement: ChatSession 與 ChatMessage 模型

系統 SHALL 在 `ohmystock.chat.schema` 提供 `ChatSession` 與 `ChatMessage` 兩個 frozen pydantic 模型（`model_config = ConfigDict(frozen=True, extra="forbid")`）。

`ChatSession` 欄位：
- `id: str` — 必須 match `^chat_[0-9a-f]{8}$`
- `title: str` — 1..120 codepoints
- `model: str` — non-empty
- `status: Literal["active", "deleted"]`
- `created_at: str` — ISO 8601 含 `+08:00`
- `updated_at: str` — ISO 8601 含 `+08:00`

`ChatMessage` 欄位：
- `id: str` — 必須 match `^msg_[0-9a-f]{12}$`
- `session_id: str` — match `^chat_[0-9a-f]{8}$`
- `role: Literal["user", "assistant", "tool_result"]`
- `content: str` — 可為空字串（partial commit 情境）
- `tool_calls_json: str | None` — JSON-encoded list 或 None
- `tool_result_for: str | None` — 對應的 tool_call_id 或 None
- `llm_cost_id: str | None` — 對應 `llm_costs.id` 或 None
- `created_at: str` — ISO 8601 含 `+08:00`

`ohmystock.chat.__init__.py` SHALL 在 `__all__` 公開 `ChatSession` / `ChatMessage` / `ChatStoreError` / `init_schema` 等名稱。

#### Scenario: ChatSession 拒絕額外欄位
- **WHEN** `ChatSession(id="chat_12345678", title="x", model="m", status="active", created_at="2026-05-15T07:00:00+08:00", updated_at="2026-05-15T07:00:00+08:00", extra="boom")`
- **THEN** SHALL 拋 pydantic `ValidationError`

#### Scenario: ChatMessage id 格式驗證
- **WHEN** 建構 `ChatMessage(id="not_a_valid_id", ...)` 其他欄位合法
- **THEN** SHALL 拋 pydantic `ValidationError`

#### Scenario: role 必須是三選一
- **WHEN** 建構 `ChatMessage(role="system", ...)`
- **THEN** SHALL 拋 pydantic `ValidationError`

---

### Requirement: chat_sessions / chat_messages / chat_messages_fts 表 schema

系統 SHALL 在 `ohmystock.chat.storage` 提供 `init_schema(conn: sqlite3.Connection) -> None` idempotent 函式創建以下 schema：

**Table `chat_sessions`**:
- `id TEXT PRIMARY KEY`
- `title TEXT NOT NULL`
- `model TEXT NOT NULL`
- `status TEXT NOT NULL CHECK(status IN ('active','deleted'))`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

**Table `chat_messages`**:
- `id TEXT PRIMARY KEY`
- `session_id TEXT NOT NULL REFERENCES chat_sessions(id)`
- `role TEXT NOT NULL CHECK(role IN ('user','assistant','tool_result'))`
- `content TEXT NOT NULL`
- `tool_calls_json TEXT`
- `tool_result_for TEXT`
- `llm_cost_id TEXT`
- `created_at TEXT NOT NULL`

**Index** `idx_chat_messages_session_created` ON `chat_messages(session_id, created_at)`.

**Virtual table `chat_messages_fts`**: FTS5，external-content `content='chat_messages'`，indexed column = `content`。同時建 3 個 trigger (`chat_messages_ai` / `chat_messages_au` / `chat_messages_ad`) 對應 AFTER INSERT / UPDATE / DELETE 同步 FTS 索引。

`init_schema` SHALL 在 `api/app.py` 的 `_lifespan` 啟動鉤子內被呼叫，順序排在 `swarm_runs.init_schema` 之後。FTS5 不可用 SHALL 拋 `RuntimeError` 含 `"FTS5"` 子字串。

#### Scenario: init_schema 重複呼叫不報錯
- **WHEN** 對同一 connection 連續呼叫 `init_schema(conn)` 兩次
- **THEN** 第二次 SHALL 不拋例外
- **AND** `PRAGMA table_info(chat_sessions)` SHALL 回傳 6 個欄位
- **AND** `PRAGMA table_info(chat_messages)` SHALL 回傳 8 個欄位

#### Scenario: chat_sessions.status CHECK 約束生效
- **WHEN** 嘗試 INSERT 一筆 `status='archived'` 的 row
- **THEN** SHALL 拋 `sqlite3.IntegrityError`

#### Scenario: FTS5 trigger 同步插入
- **GIVEN** init_schema 已執行
- **WHEN** INSERT 一筆 `chat_messages(content='台積電籌碼分析')`
- **AND** 查詢 `SELECT rowid FROM chat_messages_fts WHERE chat_messages_fts MATCH '台積電'`
- **THEN** SHALL 回傳 1 row

#### Scenario: FTS5 trigger 同步刪除
- **GIVEN** 已 INSERT 一筆 message
- **WHEN** DELETE 該 row
- **AND** 查詢 `chat_messages_fts MATCH` 同關鍵字
- **THEN** SHALL 回傳 0 row

---

### Requirement: ChatStore CRUD 與 FTS5 search

系統 SHALL 在 `ohmystock.chat.storage` 提供以下 module-level helper 函式：

- `insert_session(conn, session: ChatSession) -> None`
- `list_sessions(conn, *, limit: int, offset: int, status: str | None = "active") -> tuple[list[dict], int]` — 回 `(items, total)`；items 含 `id`/`title`/`model`/`status`/`created_at`/`updated_at`/`message_count`（LEFT JOIN COUNT）；ORDER BY `updated_at DESC, id DESC`；`limit` 不在 1..200 → `ChatStoreError("invalid_input")`
- `get_session(conn, session_id: str) -> ChatSession | None` — 回 None 表示不存在
- `soft_delete_session(conn, session_id: str, now: str) -> bool` — 已是 active → 改 deleted、更新 updated_at、回 True；已 deleted → 不動、回 True（idempotent）；不存在 → 回 False
- `insert_message(conn, msg: ChatMessage) -> None` — tool_calls_json 若給的 dict 無法 `json.dumps` SHALL 寫 `None` 而不拋例外
- `select_messages(conn, session_id: str, *, limit: int = 200) -> list[ChatMessage]` — ORDER BY `created_at ASC, id ASC`
- `search_messages(conn, *, q: str, date_from: str | None = None, date_to: str | None = None, limit: int = 20) -> list[dict]` — 回 `[{session_id, session_title, hits: [{message_id, snippet, created_at}]}]`；snippet 用 `snippet(chat_messages_fts, 2, '<mark>', '</mark>', '...', 12)`；ORDER BY BM25 ASC；同 session 多個命中聚合在同一 group

`search_messages` 行為：
- 空 `q`（trim 後）SHALL 拋 `ChatStoreError("invalid_input", "query cannot be empty")`
- `q` 含控制字元（U+0000..U+001F 除 `\t`/`\n` 外）SHALL 被剝除
- FTS5 query syntax error 從 `sqlite3.OperationalError` 攔截 SHALL remap 為 `ChatStoreError("invalid_query", "FTS5 query syntax error")` — **不**洩漏原始 SQLite 錯誤文字
- `date_from`/`date_to` 提供時 SHALL filter `created_at` 落在 `[date_from 00:00, date_to+1 00:00)` 區間（含 from、不含 to+1）

`ChatStoreError` SHALL 是 `RuntimeError` 子類，建構為 `ChatStoreError(code: str, message: str = "")`，`__str__` 形式 `"<code>: <message>"`。

#### Scenario: list_sessions 按 updated_at DESC 排序
- **GIVEN** 3 筆 session A(updated 09:00) / B(updated 10:00) / C(updated 11:00) 都 active
- **WHEN** `list_sessions(conn, limit=10, offset=0)`
- **THEN** items 順序為 [C, B, A]
- **AND** total == 3

#### Scenario: list_sessions 只列 active
- **GIVEN** session A active、B deleted
- **WHEN** `list_sessions(conn, limit=10, offset=0)`
- **THEN** items 只含 A
- **AND** total == 1

#### Scenario: list_sessions limit 超界
- **WHEN** `list_sessions(conn, limit=201, offset=0)`
- **THEN** SHALL 拋 `ChatStoreError("invalid_input", ...)`

#### Scenario: soft_delete 不存在的 session
- **WHEN** `soft_delete_session(conn, "chat_doesnotexist", now)`
- **THEN** SHALL 回 False

#### Scenario: soft_delete 已刪除的 session 是 idempotent
- **GIVEN** session A status="deleted"
- **WHEN** `soft_delete_session(conn, "chat_<A_id>", now)`
- **THEN** SHALL 回 True
- **AND** updated_at 不變（已是 deleted 不再更新）

#### Scenario: search_messages 命中分組
- **GIVEN** session A 含 2 條 message 命中關鍵字、session B 含 1 條
- **WHEN** `search_messages(conn, q="台積電", limit=10)`
- **THEN** 結果按 BM25 排序，session_id 相同的 hits 合併在同一 dict 內
- **AND** 每個 hit 含 `snippet` 字串，且 snippet 含 `<mark>...</mark>` 標記

#### Scenario: search_messages 空 q 拋 invalid_input
- **WHEN** `search_messages(conn, q="   ", limit=10)`
- **THEN** SHALL 拋 `ChatStoreError`，`code == "invalid_input"`

#### Scenario: FTS5 syntax error 被 remap
- **WHEN** `search_messages(conn, q='"unclosed', limit=10)`
- **THEN** SHALL 拋 `ChatStoreError`，`code == "invalid_query"`，message 含 `"FTS5"` 子字串
- **AND** **不**包含 sqlite3 OperationalError 原文

#### Scenario: tool_calls_json 無法序列化時寫 None
- **GIVEN** ChatMessage 的 tool_calls_json 直接傳入無效 JSON 字串 `"{broken"`
- **WHEN** `insert_message(conn, msg)`
- **THEN** SHALL 不拋例外
- **AND** DB 中該 row 的 `tool_calls_json` 欄位為 NULL
