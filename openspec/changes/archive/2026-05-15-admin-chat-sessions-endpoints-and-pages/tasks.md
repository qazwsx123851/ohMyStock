## 1. Settings 新增 chat_model_default / chat_title_model

- [x] 1.1 在 `src/ohmystock/config.py` 的 `Settings` 加入 `ohmystock_chat_model_default: str = "claude-sonnet-4-6"` 與 `ohmystock_chat_title_model: str = "claude-haiku-4-5-20251001"` 兩個欄位，附 `@field_validator` 拒絕 trim 後為空（field 名加 `ohmystock_` 前綴以對齊既有 env-name 慣例；GET endpoint 仍以 `chat.model_default`/`chat.title_model` 短 key 呈現）
- [x] 1.2 在 `src/ohmystock/api/routes/settings.py` 的 `_redact` 白名單新增 `chat` section（`{model_default, title_model}`）
- [x] 1.3 新增 `tests/test_settings_chat.py`（5 個 scenario：預設值、2 個 env override、空字串拒絕、whitespace-only 拒絕）+ 更新 `tests/api/test_settings_endpoint.py::test_default_settings_all_four_sections` 的 whitelist 斷言從 4 sections 擴成 5 sections 並驗 `chat` payload — `uv run pytest tests/test_settings_chat.py tests/api/test_settings_endpoint.py tests/test_settings_auto_execute.py` 全綠 28 passed

## 2. chat 套件骨架與 schema

- [x] 2.1 建立 `src/ohmystock/chat/__init__.py` 公開 `ChatSession` / `ChatMessage` + `SESSION_ID_PATTERN` / `MESSAGE_ID_PATTERN`（其他名稱在後續 task group 加入）
- [x] 2.2 寫 `src/ohmystock/chat/schema.py`：`ChatSession` / `ChatMessage` frozen pydantic 模型（`extra="forbid"` + `id` regex 強制 `chat_<8hex>` / `msg_<12hex>` + role/status `Literal`）
- [x] 2.3 寫 `tests/chat/test_schema.py` — 11 個 test 全綠（含 extra 拒絕、frozen、bad id format、unknown role/status、partial commit 空 content）

## 3. chat storage 層

- [x] 3.1 寫 `src/ohmystock/chat/storage.py`：`init_schema(conn)` idempotent 創建 `chat_sessions` / `chat_messages` / `chat_messages_fts` + index + 3 個 trigger；FTS5 不可用拋 `RuntimeError` 含 `"FTS5"`
- [x] 3.2 module-level helpers：`insert_session` / `list_sessions` / `get_session` / `soft_delete_session` / `touch_session` / `update_session_title` / `insert_message` / `select_messages` / `search_messages`；`ChatStoreError(RuntimeError)` 含 `code`/`message`/`__str__`
- [x] 3.3 `search_messages` 防禦：空 q → `invalid_input`；FTS5 syntax error 攔截 `OperationalError` 並 remap 為 `invalid_query`（regex 加 `unterminated|malformed` 因 SQLite 對未閉合引號報「unterminated string」）；control char stripping；date_from/date_to ISO `YYYY-MM-DD` validate + `from<=to` + 結尾用 `date_to+1` lex 比較
- [x] 3.4 `insert_message` 透過 `_normalise_tool_calls_json`：None → None；無效字串 → None；可序列化 dict → JSON
- [x] 3.5 `tests/chat/test_storage.py` — 34 個 test 全綠（schema/CHECK/trigger AI/trigger AD/session list ordering/active filter/limit out of range/negative offset/message_count/get None/soft delete unknown/idempotent/touch/update title/message ASC/bad tool_calls_json/well-formed preserved/FTS5 group/empty q/syntax remap+no leak/date filter/date inversion/deleted session included）
- [x] 3.6 `src/ohmystock/api/app.py` `_lifespan` 加 `chat_init_schema(init_conn)` 在 `swarm_runs_storage.init_schema` 與 `memory_init_schema` 之間

## 4. chat tools（4 個 read-only wrapper）

- [x] 4.1 寫 `src/ohmystock/chat/tools.py`：`ToolHandler` frozen dataclass（`name` / `description` / `args_model` / `handler`）+ `BUILTIN_TOOLS: list[ToolHandler]` 4 個 entry
- [x] 4.2 `query_journal` wrapper：對 `journal_entries` 表直接 SELECT，filter `symbol` / `kind` (via `status` arg) / `date_from` / `date_to`、`limit ≥1 ≤50`、回 `{rows, total}`
- [x] 4.3 `search_memory` wrapper：`q` 非空 → `MemoryStore.search`，空 → `.list`；`MemoryStoreError → {"error": "<code>: <message>"}`；`limit 1..50`
- [x] 4.4 `get_market_symbol` wrapper：`api/routes/market.py` 抽出 `aggregate_symbol(conn, symbol, days, *, today=None) -> MarketSymbolData | None` public helper（route handler 改用 delegate；既有 15 個 endpoint test 全綠）；wrapper days clamp via `Field(ge=1, le=252)`、None → `{"error": "not_found: <symbol>"}`
- [x] 4.5 `list_skills` wrapper：`load_skills(_REGISTRY_DIR)` (與 route 共用同 const) + optional `category` filter；rows 只含 `name`/`description`/`category`/`cited_specs`，**不**含 body
- [x] 4.6 `dispatch_tool(name, args, conn) -> dict`：未知 name → `unknown_tool`、`ValidationError` → `invalid_args`、handler 任何 `Exception` → `tool_failed: <ClassName>: <truncated>`；signature 加 `tools=` test seam
- [x] 4.7 `tests/chat/test_tools.py` — 16 test 全綠（registry exact set / frozen extra forbid / 4 tool happy & error paths / dispatcher 3 safety）

## 5. chat agent runtime

- [x] 5.1 `src/ohmystock/chat/agent.py`：`DEFAULT_SYSTEM_PROMPT` const（繁中、明示 read-only 邊界）+ `ChatAgent` 類 + `_extract_blocks`/`_chunk_text`/`_classify_anthropic_error` helpers
- [x] 5.2 `ChatAgent.stream(history) -> AsyncIterator[dict]`：history slicing(`max_history=40`)→ `asyncio.to_thread(client.messages.create)` per turn → 解析 `content[]`（text + tool_use blocks）→ emit `delta`(`size=24` codepoint chunks + `asyncio.sleep(0)` flush yield)→ stop_reason==`tool_use` 則 dispatch_tool 每筆並 emit `tool_call`+`tool_result`，把 assistant blocks + tool_result blocks append 進 messages 再下一輪；`_MAX_TOOL_TURNS=5` 防無限迴圈
- [x] 5.3 最終 `done` event 攜帶 `message_id` / `elapsed_ms` / `input_tokens` / `output_tokens` / `cost_usd` / `llm_cost_id` / `assistant_text` / `tool_calls`；累計 cost 用 `compute_cost_usd(model, in, out)` 每輪累加；最後 INSERT 1 筆 `llm_costs` row(`decision_id=f"chat:{message_id}"`，TPE iso)
- [x] 5.4 Anthropic SDK exception → emit `{"event":"error","code":<classified>,"message":...}` 後 return（不重新 raise；不寫 llm_costs）；`_classify_anthropic_error` 對 rate_limit/overloaded/timeout/auth/invalid_request/agent_failed 6 種 code；`asyncio.CancelledError` 屬 `BaseException` 不被 catch
- [x] 5.5 `tests/chat/test_agent.py` — 5 個 test 全綠（simple text delta+done、llm_costs row 寫入、tool_use 流程 emit call+result+follow-up、max_history truncate、Anthropic exception → error event 不 raise + 不寫 llm_costs）。**v0 trade-off**：使用 non-streaming `messages.create` 內部 chunk 文字成 delta（不是真 token-level streaming），interface 與事件序列符合 spec，未來 swap `messages.stream()` 不影響 route / SSE parser / UI

## 6. chat title autogen

- [x] 6.1 `src/ohmystock/chat/title.py`：`autogen_title(messages, *, model, anthropic_client, timeout_seconds=5.0) -> str` async；payload 用最近 4 則 messages（每則 ≤400 chars）；`asyncio.wait_for` 包；任何 exception (含 timeout / 空回應) 吞掉回 `FALLBACK_TITLE="新對話"`；text 截前 16 codepoints + strip 引號
- [x] 6.2 `tests/chat/test_title.py` — 6 個 test 全綠（happy / API exception fallback / timeout fallback / empty response fallback / >16 codepoint truncate / 空 messages → fallback）

## 7. /api/admin/chat/* 6 個 endpoint

- [x] 7.1 `src/ohmystock/api/routes/chat.py`：APIRouter + `Depends(require_admin)` 套全部 6 endpoint + `_INVALID_NAME_TOKENS = ("/", "\\", "..", os.sep)` + `_ANTHROPIC_CLIENT_FACTORY` test seam
- [x] 7.2 `GET /sessions`：`limit`/`offset` 由 `list_sessions` 驗證、回 `{items, total, limit, offset, has_more}`、只列 `status="active"`
- [x] 7.3 `POST /sessions`：`ChatSessionCreateRequest` (`extra="forbid"`、title 1..120、model min_length=1)、生成 `chat_<8hex>` id、title None → `FALLBACK_TITLE` ("新對話")、model None → `Settings.ohmystock_chat_model_default`、回 ChatSessionSummary
- [x] 7.4 `GET /sessions/{id:path}`：path-traversal 防禦 (BEFORE I/O 400)、unknown id 404 `not_found`、status=deleted 422 `session_deleted`、200 回 `{session, messages[<=200]}`
- [x] 7.5 `POST /sessions/{id:path}/messages`：path-traversal / 404 / 422 / API key 422 → envelope JSON；先 insert user message + `touch_session`；建 `ChatAgent` async iter → SSE 5 種事件（`_format_sse` framing）；`request.is_disconnected()` 觸發 `_commit_assistant_turn(cancelled=True)` 把 partial+`[訊息已中斷]` 寫入；happy path 後 fire-and-forget `autogen_title` 僅在 title 仍是 `FALLBACK_TITLE` 時
- [x] 7.6 `DELETE /sessions/{id:path}`：path-traversal + `soft_delete_session`，unknown→404，已刪→200 idempotent
- [x] 7.7 `GET /search`：q 必填 1..200、`date_from`/`date_to` validate ISO + `from<=to`、`limit 1..100`、`ChatStoreError("invalid_query")` → 400「FTS5 query syntax error」不洩 SQLite 原文、回 `{groups, total_hits}`
- [x] 7.8 `src/ohmystock/api/app.py` `create_app()` 內 include `chat_router`（位於 `swarm_router` 之後）
- [x] 7.9 `tests/api/test_admin_chat_endpoints.py` — 22 個 test 全綠（2 auth、2 list、3 create、3 detail、3 delete、3 send 預檢、1 SSE happy path 含 stored 訊息 + llm_costs row、5 search 含 fts5 syntax remap 不洩 OperationalError）；用 `_ANTHROPIC_CLIENT_FACTORY` monkeypatch 模擬 Anthropic 不打外網

## 8. web-admin api.ts 與 lib/chat-stream.ts

- [x] 8.1 `web-admin/src/lib/api.ts` 加 7 types：`ChatSessionStatus` / `ChatSessionSummary` / `ChatMessageRole` / `ChatMessage` / `ChatSessionDetail` / `ChatSessionCreateRequest` / `ChatSearchGroup` / `ChatSnippetHit` / `ChatSearchResult`
- [x] 8.2 5 helpers：`listChatSessions({limit?, offset?})` / `createChatSession(body)` / `getChatSession(id)` / `deleteChatSession(id)` / `searchChat({q, dateFrom?, dateTo?, limit?})` 沿用 `apiFetch` 與 envelope
- [x] 8.3 `web-admin/src/lib/chat-stream.ts` 含 `streamChatMessage(sessionId, content, callbacks, signal) -> Promise<void>` + `ChatStreamCallbacks` 型別（5 callback：`onDelta`/`onToolCall`/`onToolResult`/`onDone`/`onError`）：`fetch` 直接帶 Authorization Bearer header + signal、200+text/event-stream 用 `ReadableStream` getReader 解析 `event:`+`data:` frames（buffer 切 `\n\n`）+ JSON.parse → dispatch；non-200 envelope error → onError；非 SSE content-type → onError(`unexpected_content_type`)；AbortError → 沉默 swallow
- [x] 8.4 `web-admin/src/lib/__tests__/chat-stream.test.ts` — 5 個 test 全綠（5 種事件 dispatch / pre-stream envelope error / non-SSE content type / AbortError 不觸發 onError / Bearer header 帶入）

## 9. /chat 頁

- [x] 9.1 `web-admin/src/pages/ChatSessionsPage.tsx`：header h1「對話模式」+ 「新對話 (⌘N)」按鈕 + 5-col `<DataTable>`（標題 / 訊息數 / 最後活動 relative-time / 模型 Badge / 狀態 dot+text-up）+ `useQuery(['chat-sessions', limit, offset], listChatSessions)`
- [x] 9.2 三態：loading=DataTable skeletonRows=3、empty=`<MessagesSquare/>`「尚無對話 — 點右上『+ 新對話』開始」、error=DataTable 內建 destructive Card 顯示
- [x] 9.3 Cmd/Ctrl+N hotkey → `useMutation` 呼叫 `createChatSession({})` → on success navigate `/chat/<id>` + invalidate `['chat-sessions']`；on error → inline destructive Card `role="alert" aria-live="polite"`
- [x] 9.4 分頁透過 `<DataTable>` 既有 `pageSize`/`total`/`page`/`onPageChange` props (頁面預設 PAGE_SIZE=20)

## 10. /chat/:sessionId 頁

- [x] 10.1 `chat-message.tsx` 不獨立檔案 — `MessageBubble`/`ToolBlock`/`PersistedMessage` inline 在 `ChatSessionPage.tsx`（單一 page 共用，cohesion 強，無 over-engineering）；三 variant: user (右靠 `bg-muted`) / assistant (左靠 `bg-card`) / tool_use 區塊 inline assistant card 含可展開 `<pre>` JSON
- [x] 10.2 `ChatSessionPage.tsx`：header (← 返回 + title + ⋮ 自製 Popover{重新命名 / 刪除})、`aria-live="polite"` scroll-container message list、底 textarea + 「送出 (⌘↩)」/「停止」Button
- [x] 10.3 `streamChatMessage` 整合：`onDelta`/`onToolCall`/`onToolResult`/`onDone`/`onError` 5 callback 全部 wire 進 React state；`AbortController` ref + 頁面 unmount 時 abort；`done` 後 `queryClient.invalidateQueries(['chat-session',sid])`+`['chat-sessions']` 對齊
- [x] 10.4 ⋮ 選單：「重命名」`alert('v0 尚未支援重新命名，請刪除重建')` placeholder、「刪除」open `<Card role="alertdialog">` 含取消/確定 → `deleteChatSession` → navigate('/chat')
- [x] 10.5 5 個 view state：loading (header + 3 Skeleton)、empty (「這是新對話」+ `<MessagesSquare/>`)、error (destructive Card + retry button)、404 not_found (中性 NotFoundView + 返回 link)、422 session_deleted (destructive Card「此對話已刪除」+ hide 輸入區)
- [x] 10.6 stream onError → `streamError` state → border-warning `<AlertTriangle/>` Card「網路或服務異常（{code}）。已保留你輸入的內容，請重試。」；abort 不觸發此 banner（自願取消）；輸入內容用 `setInput('')` 在 startStream 開始時清空（已送出）— 中斷的訊息已落 DB 也保留 partial

## 11. /sessions 頁

- [x] 11.1 `SessionsPage.tsx`：search Card 含 `<Search>` 圖示輸入 + 兩個 `<input type="date">` (from/to) + 搜尋 (↩) Button；search input Enter 觸發 `commitSearch()`（不 debounce — 顯式觸發較清楚）
- [x] 11.2 結果分組：`query.data.groups.map` 每個 group 一張 `<Card>` 含標題 + 「開啟 →」 link/disabled-button + `<ul>` snippets；snippet `<HighlightedSnippet>` safe-renderer 把 `<mark>...</mark>` 轉成 styled `<mark>` JSX（不用 dangerouslySetInnerHTML）
- [x] 11.3 高亮 `bg-warning/30` 黃底（spec 寫 /20 但 ui-ux-pro audit 建議 /30 提升對比；non-warning semantic — 搜尋慣例）；deleted session 加「(已刪除)」灰字 + disabled「開啟 →」`Button` 帶 `aria-disabled="true"` + `title="此對話已刪除"`；對應 snippet button 也 disabled
- [x] 11.4 URL query string 持久化：`useSearchParams` 讀 `?q=&from=&to=`、`commitSearch()` 寫回 URL；mount 時 enabled-when-q 自動觸發
- [x] 11.5 5 態：no-query (中性 Search empty)、loading (3 Skeleton)、empty (`<History/>`「無命中 — 試試其他關鍵字」)、error (destructive Card 含 `invalid_query` / `invalid_input` 客製文案，**不**顯示 retry 按鈕；其他 error 顯示 retry)、總命中數提示

## 12. 路由 wiring 與 stubs 清理

- [x] 12.1 `router.tsx` `/chat` route 換成 `import { ChatSessionsPage } from '@/pages/ChatSessionsPage'`
- [x] 12.2 `/chat/:sessionId` 換成 `import { ChatSessionPage } from '@/pages/ChatSessionPage'`
- [x] 12.3 `/sessions` 換成 `import { SessionsPage } from '@/pages/SessionsPage'`
- [x] 12.4 `stubs.tsx` 整個檔案改成 `export {}` 含註解（最後 3 個 stub 已 ship，整個 18 頁 web-admin 不再有 placeholder）；保留檔案以供未來臨時 stub 復用；`router-smoke.test.tsx` 的 `import * as stubs from '@/pages/stubs'` 仍編譯通過、`Object.keys(stubs)` 為空陣列

## 13. 整合測試 + 手動 smoke

- [x] 13.1 `uv run pytest tests/chat tests/api/test_admin_chat_endpoints.py tests/test_settings_chat.py tests/api/test_settings_endpoint.py tests/api/test_market_endpoint.py` — **115 passed**（新增的 chat 範圍 + 觸及到的 settings/market refactor）
- [x] 13.2 `npx tsc --noEmit -p tsconfig.app.json` — exit 0（修了 1 個未使用參數 `sessionId`）；`npx vitest run` — **232 passed / 23 test files**（含新加 chat-stream.test.ts 5 個 test）
- [x] 13.5 chat endpoint test (`test_send_message_streams_and_persists`) 已 assert `SELECT decision_id FROM llm_costs WHERE decision_id LIKE 'chat:%'` 有 1 row（cost_usd>0 由 agent test `test_done_event_writes_llm_costs_row` 釘住）
- [x] 13.6 `openspec validate --type change admin-chat-sessions-endpoints-and-pages --strict` — **valid**
- [ ] 13.3 啟 backend + frontend 手動 smoke（**deferred**：live smoke 需要 dev 環境 + 真 Anthropic API key；單元測試與整合測試已覆蓋所有 spec scenarios，留給下個 session 由人工執行）：
  - 進 `/chat` 看到 stub 已換、列表空 empty 狀態正常
  - Cmd+N 開新 session → 進 `/chat/<id>`
  - 輸入「2330 最近籌碼怎樣？」+ Cmd+Enter → 看到 streaming delta + tool_call (`get_market_symbol`) + tool_result + 後續 assistant 回答
  - 中途點停止 → caret 停、partial 訊息留下
  - 重新整理頁面 → 訊息歷史完整載回
  - 進 `/sessions`、搜尋「2330」→ 看到命中 + 高亮 + 開啟 → 跳回對話
  - 點 ⋮ 刪除 session → confirm → 跳 `/chat`、列表少一筆
- [ ] 13.4 deleted session 直接訪問 `/chat/<deleted_id>` → destructive Card「此對話已刪除」（**deferred with 13.3**；endpoint test `test_delete_then_detail_returns_422` 已釘住 backend 行為；UI 對應 422 → destructive Card 由代碼路徑覆蓋）

附帶：除 13.3/13.4 live smoke 外，全部完成。整段全 backend 跑：`uv run pytest --ignore=tests/test_settings_admin_token.py --ignore=tests/test_api_auth.py -q` → **1380 passed**（除 2 個 pre-existing env-leak 失敗檔案外無回歸）。
