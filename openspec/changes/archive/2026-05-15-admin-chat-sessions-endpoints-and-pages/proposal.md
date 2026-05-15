## Why

Phase 4 web-admin 18 頁中，最後 3 個 stub（`/chat`、`/chat/:sessionId`、`/sessions`）是 Mark 日常使用 ohMyStock 的「前門」— per `docs/user-scenarios.md` 多個情境（盤前掃描討論、特定 symbol 籌碼分析、復盤事後問答、記憶撈取）都靠這個對話介面進入系統。視覺契約早在 `docs/web-admin-page-designs.md` §1 / §2 / §15 拍板；後端則完全沒做（admin endpoints / chat 儲存 / streaming runtime 全缺）。

更重要的是 — 這個 change 同時建立「**長時間運行 agent session runtime**」substrate：session 持久化、tool call/result 紀錄、SSE token streaming、`llm_costs` per-message 寫入。之後 `trader-loop-scheduler` change 要做「無人值守的排程 session」時，**reuse 同一個 substrate**，只是把「使用者輸入」換成「cron 觸發」。所以這不是裝飾性收尾，是 agent runtime 的第一次落地。

選擇 **單一 agent + 4 個 read-only tool + 同步 SSE streaming** 的最薄路徑（無多代理辯論、無寫入 tool、無背景 task queue），與 admin-swarm-endpoints-and-pages 的「thin wrapper」精神一致。

## What Changes

- **新增** `chat_sessions` + `chat_messages` 兩張 SQLite 表 + 1 個 FTS5 virtual table (`chat_messages_fts`)：
  - `chat_sessions`：`id TEXT PK (chat_<8hex>) / title / model / status (active|deleted) / created_at / updated_at`
  - `chat_messages`：`id TEXT PK (msg_<12hex>) / session_id FK / role (user|assistant|tool_result) / content TEXT / tool_calls_json TEXT \| NULL / tool_result_for TEXT \| NULL / llm_cost_id TEXT \| NULL / created_at` + idx on (`session_id`, `created_at`)
  - `chat_messages_fts`：external-content `content='chat_messages'`，搭 3 個 trigger（INSERT / UPDATE / DELETE 同步），mirror `memory_rows_fts` 的做法
  - schema 在 `_lifespan` 中順序 `... swarm_runs.init_schema → chat_sessions.init_schema → memory_init_schema` 之間 idempotent 建表（其實順序不重要，但靠近 memory 因為 FTS5 用法類似）

- **新增** `src/ohmystock/chat/` 套件：
  - `schema.py` — `ChatSession` / `ChatMessage` frozen pydantic（`extra="forbid"`）
  - `storage.py` — `init_schema(conn)`、`insert_session`、`list_sessions`、`get_session`、`soft_delete_session`、`insert_message`、`select_messages(session_id)`、`search_messages(q, date_from, date_to, limit)`（FTS5 BM25 ASC，控制字元剝除 + 空 `q` → `ChatStoreError("invalid_input")`、`OperationalError` remap 為 `invalid_query`，不洩漏 SQLite 原文）
  - `agent.py` — `ChatAgent` 類別封裝 Anthropic SDK call：input 為 `messages: list[ChatMessage]` + 工具定義列；輸出為 async generator yielding `delta` / `tool_call` / `tool_result` / `done` / `error` 五種事件；每完整 LLM 回合寫一筆 `llm_costs` (`decision_id="chat:<message_id>"`)
  - `tools.py` — 4 個 read-only tool wrapper：`query_journal` / `search_memory` / `get_market_symbol` / `list_skills`，每個 tool 用 pydantic `extra="forbid"` 驗 args，失敗回 `{"error": "<code>: <detail>"}`（不 raise）給 agent 看
  - `title.py` — `autogen_title(messages, settings) -> str` 用 Haiku 4.5 做 ≤16 char TW Mandarin 摘要；任何錯誤吃掉並回 `"新對話"`

- **新增** 6 個 admin endpoints `/api/admin/chat/*`（Bearer auth + `{ok,data,error}` envelope + per-request `Depends(get_db)`，沿用既有慣例）：
  - `GET /api/admin/chat/sessions?limit=N&offset=M` — `created_at DESC, id DESC`、`limit` clamp 1..200、預設 50、回 6-key summary（id / title / model / status / created_at / updated_at + 訊息數 `message_count` 由 LEFT JOIN COUNT）
  - `POST /api/admin/chat/sessions {title?, model?}` — 建空 session，`model` 預設 `Settings().chat_model_default`（新 setting，預設 `claude-sonnet-4-6`），回完整 session row
  - `GET /api/admin/chat/sessions/{id:path}` — path-traversal `_INVALID_NAME_TOKENS` (`/`, `\`, `..`, `os.sep`) BEFORE I/O → 400；回 session + 最新 200 訊息（ASC）；404 `not_found`；422 `session_deleted` if `status="deleted"`
  - `POST /api/admin/chat/sessions/{id:path}/messages {content}` — 同 path-traversal 防禦；先寫使用者 message 進表，再 `text/event-stream` 回應 5 種事件：
    - `event: delta\ndata: {"text": "..."}` （per-token）
    - `event: tool_call\ndata: {"id":"...", "name":"...", "args":{...}}`
    - `event: tool_result\ndata: {"tool_call_id":"...", "result":{...}}`
    - `event: done\ndata: {"message_id":"msg_...", "elapsed_ms": N}`
    - `event: error\ndata: {"code":"...", "message":"..."}`
    Client 關連線 → server 用 `anyio.CancelScope` cancel LLM stream，commit 已收到的 partial assistant content 為一筆 `chat_messages` row（`status` 欄不變，但 `tool_calls_json` 反映實際完成的）
  - `DELETE /api/admin/chat/sessions/{id:path}` — 軟刪除（`status="deleted"`、`updated_at` 更新）；訊息不動（保留復盤可查）；404 `not_found`；已刪則 200 idempotent
  - `GET /api/admin/chat/search?q=&date_from=&date_to=&limit=N` — `q` 必填 1..200 codepoints；`date_from` / `date_to` ISO YYYY-MM-DD 選填且 `from<=to`；FTS5 BM25 ASC；回「按 session 分組」結構 `[{session_id, session_title, hits:[{message_id, snippet, created_at}]}]`，snippet 用 SQLite `snippet(chat_messages_fts, 2, '<mark>', '</mark>', '...', 12)` ≤120 char；invalid query → 400

- **新增** web-admin 3 頁取代 stub：
  - `/chat`（`ChatSessionsPage.tsx`）— 5-col `<DataTable>`（Session 標題 / 訊息數 / 最後活動 / 模型 / 狀態）+ 「+ 新對話 (Cmd+N)」`Button` + `useQuery(['chat-sessions'])` + 3-row Skeleton loading + 中性 EmptyChatSessions + destructive ErrorPanel+retry + click row navigate(`/chat/<id>`) + Cmd/Ctrl+N hotkey → `POST /sessions` → navigate
  - `/chat/:sessionId`（`ChatSessionPage.tsx`）— header (← 返回 + session title + ⋮ Popover{重命名、刪除}) + virtualized message scroll list（user / assistant / tool_use 三 variant `Card`）+ streaming caret `▮` + bottom `<Textarea>` + 「送出 (Cmd+↩)」`Button` + click tool_use block 展開 args/result + Cmd/Ctrl+Enter 送出 + Enter 換行 + 直接 fetch 對 `POST /messages` 拿 `text/event-stream`，用 `ReadableStream` reader 解析 5 種事件並 patch local state + Esc 取消 inline 重命名 + 「網路中斷，已保留你輸入的內容」inline warning
  - `/sessions`（`SessionsPage.tsx`）— 大型 search `<Input>` + 兩個 `<Input type=date>` from/to + 搜尋 `Button` + Enter 觸發 + result 按 session 分組 `<Card>` 列表（每 card 含 session 標題 + 日期 + 高亮 snippets + 「開啟 →」）+ click snippet → `navigate(/chat/<id>?msgId=...)` + 「無命中」/`<History muted/>` empty / destructive ErrorPanel + retry

- **新增** `Settings.chat_model_default` (`str`, 預設 `"claude-sonnet-4-6"`) 與 `Settings.chat_title_model` (`str`, 預設 `"claude-haiku-4-5-20251001"`) — fail-safe 預設值；admin 透過 `GET /api/admin/settings` 即可看（read-only）

- 重用 `Settings.anthropic_api_key` fail-fast 檢查（在 `POST /messages` 進入 streaming 前；缺則 422 `missing_api_key`）
- 重用 `src/ohmystock/journal/repository.py` / `src/ohmystock/memory/store.py` / `src/ohmystock/skills/loader.py` / `src/ohmystock/api/routes/market.py` 的內部函式（不走 HTTP self-call）
- 重用 `ohmystock.decider._pricing.compute_cost_usd` 與 `llm_costs` 表（既有 cost-tracking spec）

**Intentionally deferred**：
- 任何 write tool（screener.run / decider.decide / confirm_gate.confirm / journal 寫入）— v0 chat agent **絕對 read-only**，避免「不小心叫 LLM 下單」的攻擊面
- 多代理辯論（已有 `/swarm` 頁負責）
- 訊息編輯 / 重發 / fork session
- 訊息層級 markdown 渲染（plain text + `whitespace-pre-wrap` 即可，跟 `/skills/:name` 一致）
- session 重命名 inline UI 後端 API（PATCH `/sessions/{id}` 留 v1）— v0 ⋮ 選單裡的「重命名」按下會顯示 toast 「v0 尚未支援，請刪除重建」
- EventBus event_type 新增（chat 流量量太大，token-level 不灌進全域 bus）
- 訊息 attach 圖片 / 檔案上傳
- session export (.md / .json)
- 跨 session 的全文 + semantic 混合搜尋（v0 純 FTS5 BM25）
- 自動 session 結束 / archive 機制
- Cmd+K 全域 quick switcher
- typing indicator broadcast 給其他客戶端（單一使用者本機，毫無必要）

## Capabilities

### New Capabilities

- `chat-store`: `ChatSession` / `ChatMessage` 模型；`chat_sessions` / `chat_messages` / `chat_messages_fts` 三表 schema；`storage.py` CRUD + FTS5 search 行為（含 `ChatStoreError` 的 `invalid_input` / `invalid_query` / `not_found` 三 code）；schema idempotent init 契約。
- `chat-agent-runtime`: `ChatAgent` async generator 對 Anthropic SDK 的封裝行為；4 個 read-only tool 的 I/O schema；`autogen_title` 行為；每 LLM 回合寫一筆 `llm_costs` 的契約；Anthropic stream cancel 對應的 partial-message commit 行為。
- `admin-chat-endpoints`: 6 個 `/api/admin/chat/*` endpoint 契約（method / path / request schema / response schema / error envelope code / path-traversal 防禦 / SSE event 五種類型 / 取消行為）。
- `web-admin-chat-pages`: `/chat`、`/chat/:sessionId`、`/sessions` 三頁的視覺契約、互動、SSE token streaming patch 行為、empty/error/loading/reconnect 五態、鍵盤可達性（依照 `docs/web-admin-page-designs.md` §1 / §2 / §15 補完落地細節）。

### Modified Capabilities

- `cli-and-config`: `Settings` 加 `chat_model_default` 與 `chat_title_model` 兩個欄位（`str`，預設 `"claude-sonnet-4-6"` 與 `"claude-haiku-4-5-20251001"`）；`get_settings_view()` 白名單 redactor 把這 2 個 key 也加入回傳。

## Impact

- **Affected code**:
  - 新檔: `src/ohmystock/chat/{__init__,schema,storage,agent,tools,title}.py`
  - 新檔: `src/ohmystock/api/routes/chat.py`
  - 修改: `src/ohmystock/api/app.py`（include chat router + `chat_storage.init_schema` 進 `_lifespan`）
  - 修改: `src/ohmystock/config.py`（加 2 個 Settings 欄位）
  - 修改: `src/ohmystock/api/routes/settings.py`（白名單擴充）
  - 新檔: `tests/chat/{test_schema,test_storage,test_agent,test_tools,test_title}.py`
  - 新檔: `tests/api/test_admin_chat_endpoints.py`
  - 新檔: `web-admin/src/pages/{ChatSessionsPage,ChatSessionPage,SessionsPage}.tsx`
  - 新檔: `web-admin/src/components/chat-message.tsx`（user / assistant / tool_use 三 variant Card）
  - 新檔: `web-admin/src/lib/chat-stream.ts`（fetch + ReadableStream SSE parser，重用 `apiFetch` 的 auth header 邏輯）
  - 修改: `web-admin/src/lib/api.ts`（加 `listChatSessions` / `createChatSession` / `getChatSession` / `deleteChatSession` / `searchChat` + 對應型別）
  - 修改: `web-admin/src/router.tsx`（3 路由換真檔）、`web-admin/src/pages/stubs.tsx`（移除 `ChatPage` / `ChatSessionPage` / `SessionsPage` 三個 export）
- **APIs**: 6 個新 endpoint 全在 `/api/admin/chat/*`，沿用既有 Bearer auth 與 envelope；其中 `POST /messages` 回 `text/event-stream`（不是 envelope），但失敗仍回 envelope JSON（在 stream 開始前）。
- **DB**: 3 個新表（含 1 個 FTS5 virtual + 3 個 trigger）— idempotent `init_schema` 在 `_lifespan` 中執行。
- **EventBus**: 不新增 event_type — chat token stream 走 dedicated response 而非 global SSE bus。
- **Dependencies**: 無新套件（`anthropic` SDK 已在；FTS5 既有用法 mirror `memory_rows_fts`）。
- **Settings**: 新增 2 個 `OHMYSTOCK_CHAT_MODEL_DEFAULT` / `OHMYSTOCK_CHAT_TITLE_MODEL` env override。
- **安全 / blast radius**: v0 agent **絕對 read-only**（4 個 tool 全是 select-only 查詢）— 即使被 prompt injection 也只能讀資料、無法下單 / 改 confirm-gate / 改 settings。
- **CLAUDE.md §5**: archive 後新增 1 row 記錄 `chat-store` + `chat-agent-runtime` + `admin-chat-endpoints` + `web-admin-chat-pages` SSOT。
