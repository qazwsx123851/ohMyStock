## ADDED Requirements

### Requirement: ChatAgent async generator runtime

系統 SHALL 在 `ohmystock.chat.agent` 提供 `ChatAgent` 類別，建構 `ChatAgent(model: str, tools: list[ToolHandler], anthropic_client, *, system_prompt: str = DEFAULT_SYSTEM_PROMPT, max_history: int = 40)`。

`ChatAgent.stream(messages: list[ChatMessage]) -> AsyncIterator[ChatAgentEvent]` 為 async generator，依序 yield 以下 5 種 `ChatAgentEvent` discriminated union：

- `{"event": "delta", "text": str}` — 逐 token 文字（從 Anthropic content_block_delta 抓 `delta.text`）
- `{"event": "tool_call", "id": str, "name": str, "args": dict}` — 當 LLM 要呼 tool 時 emit；emit 後 ChatAgent SHALL 立即執行 tool 並 emit tool_result
- `{"event": "tool_result", "tool_call_id": str, "result": dict}` — tool 執行完
- `{"event": "done", "message_id": str, "elapsed_ms": int, "cost_usd": float, "input_tokens": int, "output_tokens": int}` — 整輪結束
- `{"event": "error", "code": str, "message": str}` — 任何錯誤

行為細節：

1. 只把最近 `max_history` 則 `messages` 送進 Anthropic（其餘只存資料庫不送 prompt）
2. Anthropic stream 結束後 SHALL 用 `decider._pricing.compute_cost_usd(model, input_tokens, output_tokens)` 計算 cost
3. SHALL 寫一筆 `llm_costs` row，`decision_id=f"chat:{message_id}"`、`model=self.model`、`input_tokens=...`、`output_tokens=...`、`cost_usd=...`、`created_at=ISO TPE`
4. 每個 `tool_call` event 後 SHALL 立即執行對應 `ToolHandler`，將 result（無論成功失敗）作為 Anthropic 的 `tool_result` content 送回繼續 stream
5. Anthropic SDK 任何 exception SHALL 被 catch 並 emit `error` event 後 return（**不**重新 raise）
6. `asyncio.CancelledError` SHALL **不**被 catch；caller (endpoint handler) 負責 cancel 後寫 partial message

`DEFAULT_SYSTEM_PROMPT` SHALL 在 `agent.py` module-level constant 定義，內容包含「你是 ohMyStock 的助手 agent，協助 Mark 查 trade journal / memory / market 資料 / skill 定義；你只能讀資料、不能下單」等指引。

#### Scenario: stream emit 5 種事件並寫 llm_costs
- **GIVEN** anthropic client mock 回傳一段「text → tool_use → text → end」的 stream
- **AND** tool handler `query_journal` mock 回 `{"rows": []}`
- **WHEN** `await collect(agent.stream(messages))`
- **THEN** event 順序包含 `delta`+ → `tool_call` → `tool_result` → `delta`+ → `done`
- **AND** `done` event 的 `cost_usd` > 0
- **AND** `llm_costs` 表新增 1 row，`decision_id` 以 `chat:msg_` 開頭

#### Scenario: max_history 限制送出訊息數
- **GIVEN** `max_history=3`、messages 長度 10
- **WHEN** stream 啟動，inspect anthropic client 收到的 messages 長度
- **THEN** SHALL 只有 3 則（最新的 3 則）

#### Scenario: Anthropic exception emit error 不 raise
- **GIVEN** anthropic client 拋 `anthropic.RateLimitError`
- **WHEN** iterate `agent.stream(messages)`
- **THEN** SHALL emit `{"event": "error", "code": "rate_limit", "message": str}` 後 return
- **AND** generator SHALL 不重新 raise 該 exception

#### Scenario: CancelledError 不被 catch
- **GIVEN** stream 開始後 cancel
- **WHEN** generator 內遇到 `asyncio.CancelledError`
- **THEN** SHALL 讓 exception 傳出（caller 負責 partial commit）

---

### Requirement: 4 個 read-only tool wrapper

系統 SHALL 在 `ohmystock.chat.tools` 暴露 `BUILTIN_TOOLS: list[ToolHandler]`，至少含以下 4 個：

每個 `ToolHandler` 為 dataclass（frozen）含：
- `name: str`
- `description: str`
- `args_model: type[BaseModel]` — pydantic frozen + `extra="forbid"`
- `handler: Callable[[BaseModel, sqlite3.Connection], dict]` — sync function；任何 exception SHALL 被 outer dispatcher catch 並轉成 `{"error": "<code>: <detail>"}` 給 agent，**不**重新 raise

四個 tool：

1. `query_journal(symbol: str | None, date_from: str | None, date_to: str | None, status: str | None, limit: int = 20)` — 走 `ohmystock.journal.repository.select_rows`，回 `{"rows": [...], "total": int}`；`limit` clamp 1..50
2. `search_memory(q: str, kind: str | None, tag: str | None, limit: int = 20)` — 走 `ohmystock.memory.store.MemoryStore.search` 或 `list` (q 為空 → list)；`limit` clamp 1..50；ChatStoreError → `{"error": "..."}`
3. `get_market_symbol(symbol: str, days: int = 60)` — 走 `ohmystock.api.routes.market._aggregate_symbol` (helper SHALL 被抽出來成可 import 的 public 函式)；`days` clamp 1..252；不存在 symbol → `{"error": "not_found: <symbol>"}`
4. `list_skills(category: str | None = None)` — 走 `ohmystock.skills.loader.load_skills`，每筆只回 `{name, description, category, cited_specs}`（**不**回 body 因為太長）

Tool dispatcher 行為：
- 收到 `tool_call` event 後 `name not in {t.name for t in BUILTIN_TOOLS}` SHALL 回 `{"error": "unknown_tool: <name>"}` 不嘗試執行
- args 不通過 `args_model` 驗證 SHALL 回 `{"error": "invalid_args: <pydantic detail>"}` 不執行 handler
- handler 拋任何 exception SHALL 被 catch 回 `{"error": "tool_failed: <exc class>: <str(exc)[:200]>"}`

#### Scenario: 4 個 tool 都在 BUILTIN_TOOLS
- **WHEN** `from ohmystock.chat.tools import BUILTIN_TOOLS`
- **THEN** `{t.name for t in BUILTIN_TOOLS} == {"query_journal", "search_memory", "get_market_symbol", "list_skills"}`

#### Scenario: query_journal limit clamp
- **WHEN** dispatch `query_journal` with `args.limit=999`
- **THEN** handler 收到的 effective limit ≤ 50

#### Scenario: 未知 tool name 回 error
- **WHEN** dispatch tool name `screener_run`（不在 BUILTIN_TOOLS）
- **THEN** SHALL 回 `{"error": "unknown_tool: screener_run"}`
- **AND** 不會嘗試 import `screener` 模組

#### Scenario: 無效 args 回 invalid_args
- **WHEN** dispatch `query_journal` with `{"limit": "not_an_int"}`
- **THEN** SHALL 回 `{"error": "invalid_args: ..."}` 且 message 含 `int_parsing` 子字串

#### Scenario: handler exception 被 catch 回 tool_failed
- **GIVEN** `select_rows` mock 拋 `sqlite3.OperationalError("db locked")`
- **WHEN** dispatch `query_journal`
- **THEN** SHALL 回 `{"error": "tool_failed: OperationalError: db locked"}`
- **AND** outer caller 不見到該 exception

---

### Requirement: autogen_title 用 Haiku 4.5 失敗吞掉

系統 SHALL 在 `ohmystock.chat.title` 提供 `autogen_title(messages: list[ChatMessage], *, model: str, anthropic_client, timeout_seconds: float = 5.0) -> str` async 函式。

行為：
1. 取最近 4 則 messages 組成 prompt
2. 呼叫 anthropic client 用 Haiku 4.5 model，system_prompt `"以 16 個 TW Mandarin 字以內摘要這段對話的主題。只回標題本文，不加引號、不加說明。"`
3. `asyncio.timeout(timeout_seconds)` 包住整段
4. 取得回應後 strip + 取前 16 codepoints
5. 任何 exception（包含 `TimeoutError` / `anthropic.*Error` / 空字串回應）SHALL 回 `"新對話"`

`autogen_title` 不可 raise；invariant 由 test 釘住。

#### Scenario: 成功生成標題
- **GIVEN** anthropic client mock 回「2330 籌碼分析」
- **WHEN** `await autogen_title(messages)`
- **THEN** 回 `"2330 籌碼分析"`

#### Scenario: API 失敗回 fallback
- **GIVEN** anthropic client 拋 `anthropic.APIError`
- **WHEN** `await autogen_title(messages)`
- **THEN** 回 `"新對話"`，不重新 raise

#### Scenario: 超時回 fallback
- **GIVEN** anthropic client 永遠 sleep
- **WHEN** `await autogen_title(messages, timeout_seconds=0.1)`
- **THEN** 回 `"新對話"`

#### Scenario: 截斷到 16 codepoints
- **GIVEN** anthropic client 回 17 字以上字串
- **WHEN** `await autogen_title(messages)`
- **THEN** 回傳長度 ≤ 16 codepoints
