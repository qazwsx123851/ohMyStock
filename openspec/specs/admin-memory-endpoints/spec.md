# admin-memory-endpoints Specification

## Purpose
TBD - created by archiving change web-admin-memory-page-and-store. Update Purpose after archive.
## Requirements
### Requirement: List endpoint shape and source

系統 SHALL 暴露 `GET /api/admin/memory/rows`，回傳分頁的 memory row 列表，資料來源為 `memory_rows` 表，透過 `MemoryStore.list(...)` 讀取。

Endpoint MUST 註冊在 router-level `Depends(require_admin)`，MUST 透過 `Depends(get_db)` 取得 per-request `sqlite3.Connection`。成功 SHALL wrap 在 `to_success(...)`、任何 raised exception SHALL wrap 在 `map_exception_to_envelope(...)`，符合所有 admin endpoint 的統一 `{ok, data, error}` envelope。

Query parameters：

- `kind: str | None`（optional，預設 None）— 必須是合法 `MemoryKind` 之一（`note`、`lesson`、`proposal`、`review_summary`），非法值 SHALL 回 400 `invalid_input`。
- `tag: str | None`（optional，預設 None）— 任何非空字串；空字串視為未提供（仍回 200，等於 None）。
- `limit: int`（optional，預設 50）— 必須 ≥ 1；伺服器端 clamp ≤ 200。`<= 0` SHALL 回 400 `invalid_input`。
- `offset: int`（optional，預設 0）— 必須 ≥ 0。`< 0` SHALL 回 400 `invalid_input`。

Response `data` SHALL 為 JSON 物件 `{items: MemoryRowJSON[], total: int, limit: int, offset: int, has_more: bool}`，其中 `MemoryRowJSON` 為：

```
{
  id: int,
  kind: "note" | "lesson" | "proposal" | "review_summary",
  content: str,
  content_preview: str,    // content[:200]
  content_truncated: bool, // len(content) > 200
  tags: str[],
  source: str | null,
  created_at: str          // ISO-8601 含 +08:00
}
```

`content_preview` SHALL 等於 `content[:200]`（Python codepoint slicing）。`content_truncated` SHALL 等於 `len(content) > 200`。`tags` SHALL 為已從 JSON 字串解碼的陣列。`items` 排序 SHALL 為 `created_at DESC, id DESC`（由 store 保證）。

#### Scenario: 200 with empty table
- **WHEN** authenticated request hits `GET /api/admin/memory/rows` with empty `memory_rows`
- **THEN** response is HTTP 200
- **AND** body equals `{"ok": true, "data": {"items": [], "total": 0, "limit": 50, "offset": 0, "has_more": false}}`

#### Scenario: 200 with rows ordered by created_at DESC
- **GIVEN** rows seeded `(id=1, created_at='2026-05-09T10:00:00+08:00')` 與 `(id=2, created_at='2026-05-09T11:00:00+08:00')`
- **WHEN** authenticated request hits `GET /api/admin/memory/rows`
- **THEN** `data.items[0].id == 2` 與 `data.items[1].id == 1`
- **AND** `data.total == 2`

#### Scenario: content_preview truncation flag
- **GIVEN** 一筆 row `content` 為 250 字元
- **WHEN** request hits `GET /api/admin/memory/rows`
- **THEN** 對應 item 的 `content_preview` 長度 SHALL 為 200
- **AND** `content_truncated` SHALL 為 `true`
- **AND** `content` SHALL 為完整 250 字元（不被截斷）

#### Scenario: short content not truncated
- **GIVEN** 一筆 row `content` 為 50 字元
- **WHEN** request hits 該 endpoint
- **THEN** 對應 item 的 `content_preview` SHALL 等於完整 content
- **AND** `content_truncated` SHALL 為 `false`

#### Scenario: kind filter
- **GIVEN** 表中混合 `note` / `lesson`
- **WHEN** `GET /api/admin/memory/rows?kind=lesson`
- **THEN** `data.items` SHALL 全部 `kind='lesson'`
- **AND** `data.total` SHALL 等於 lesson row 數

#### Scenario: tag filter
- **GIVEN** rows `(id=1, tags=['vcp'])`、`(id=2, tags=['vcp', 'breakout'])`、`(id=3, tags=['breakout'])`
- **WHEN** `GET /api/admin/memory/rows?tag=vcp`
- **THEN** `data.items[*].id` 集合 SHALL 等於 `{1, 2}`

#### Scenario: kind + tag combined
- **GIVEN** rows 中只有 `(id=5, kind='lesson', tags=['vcp'])` 同時符合
- **WHEN** `GET /api/admin/memory/rows?kind=lesson&tag=vcp`
- **THEN** `data.items` SHALL 為長度 1 且 `id=5`

#### Scenario: pagination via limit/offset
- **GIVEN** 100 筆 row
- **WHEN** `GET /api/admin/memory/rows?limit=20&offset=40`
- **THEN** `len(data.items)` SHALL 為 20
- **AND** `data.offset == 40`
- **AND** `data.has_more` SHALL 為 `true`（因為 40+20 < 100）

#### Scenario: limit clamp at 200
- **GIVEN** 300 筆 row
- **WHEN** `GET /api/admin/memory/rows?limit=999`
- **THEN** `len(data.items)` SHALL ≤ 200
- **AND** `data.limit == 200`

#### Scenario: invalid kind 回 400
- **WHEN** `GET /api/admin/memory/rows?kind=garbage`
- **THEN** response 為 HTTP 400
- **AND** body `{"ok": false, "error": {"code": "invalid_input", ...}}`
- **AND** error.message 提到允許的 kind 值

#### Scenario: limit 0 回 400
- **WHEN** `GET /api/admin/memory/rows?limit=0`
- **THEN** HTTP 400 `invalid_input`

#### Scenario: offset -1 回 400
- **WHEN** `GET /api/admin/memory/rows?offset=-1`
- **THEN** HTTP 400 `invalid_input`

#### Scenario: empty tag query string treated as absent
- **GIVEN** 表中有任意 row
- **WHEN** `GET /api/admin/memory/rows?tag=`（空字串）
- **THEN** 行為 SHALL 等同未傳 tag（回所有 row、HTTP 200）

---

### Requirement: Search endpoint shape and source

系統 SHALL 暴露 `GET /api/admin/memory/search`，回傳 FTS5 BM25-ranked 結果。資料來源為 `memory_rows_fts` join `memory_rows`，透過 `MemoryStore.search(...)` 呼叫。

Endpoint MUST 註冊在 router-level `Depends(require_admin)`，使用 `Depends(get_db)`，envelope 規則同 list endpoint。

Query parameters：

- `q: str`（**required**）— 搜尋表達式（FTS5 syntax，例如 `'breakout'`、`'VCP AND breakout'`、`'杯柄*'`）。空 / 純空白 / 控制字元剝除後為空 SHALL 回 400 `invalid_input`。
- `limit: int`（optional，預設 50）— 同 list endpoint。
- `offset: int`（optional，預設 0）— 同 list endpoint。

不接受 `kind` 或 `tag` 參數（v0 範圍）；若 client 傳了 `kind` / `tag`，伺服器 SHALL 忽略（不回 400）。

Response `data` 形狀 SHALL 與 list endpoint 完全相同（`MemoryRowJSON[]` + 分頁欄位），唯一差別為排序：`items` SHALL 依 BM25 ASC 排序，相同分數時依 `id ASC` tie-break。`data` 中 SHALL NOT 含 BM25 分數欄位（v0 不暴露）。

`MemoryStoreError("invalid_query")` SHALL 被 endpoint 捕捉並回 HTTP 400 `invalid_query` envelope，message 為 generic 字串（例如 `"FTS5 query syntax error"`），SHALL NOT 包含原始 `sqlite3.OperationalError` 文字。

#### Scenario: 200 with hits ordered by BM25
- **GIVEN** rows `(id=1, content='breakout breakout breakout')`、`(id=2, content='breakout once')`、`(id=3, content='unrelated')`
- **WHEN** `GET /api/admin/memory/search?q=breakout`
- **THEN** HTTP 200
- **AND** `data.items[*].id` 前兩筆 SHALL 為 `[1, 2]`
- **AND** id=3 SHALL NOT 出現
- **AND** `data.total == 2`

#### Scenario: empty q 回 400
- **WHEN** `GET /api/admin/memory/search?q=`
- **THEN** HTTP 400 `invalid_input`

#### Scenario: whitespace-only q 回 400
- **WHEN** `GET /api/admin/memory/search?q=%20%20%20`（URL-decoded 為三個 space）
- **THEN** HTTP 400 `invalid_input`

#### Scenario: missing q 回 422
- **WHEN** `GET /api/admin/memory/search`（沒有 q query parameter）
- **THEN** HTTP 422（FastAPI 預設 missing required query 錯誤）

#### Scenario: malformed FTS5 query 回 400 invalid_query
- **WHEN** `GET /api/admin/memory/search?q=foo%20OR`（trailing operator）
- **THEN** HTTP 400
- **AND** `body.error.code == "invalid_query"`
- **AND** `body.error.message` SHALL NOT 包含 `"fts5: syntax error"`、`"sqlite3"`、或 traceback 字串

#### Scenario: BM25 score not exposed
- **GIVEN** 任意命中 row
- **WHEN** request hits `GET /api/admin/memory/search?q=...`
- **THEN** response `data.items[*]` SHALL NOT 含 `bm25_score` 或 `score` 欄位

#### Scenario: limit clamp / offset 同 list
- **GIVEN** 1000 筆 row 全都命中 `'common'`
- **WHEN** `GET /api/admin/memory/search?q=common&limit=999&offset=50`
- **THEN** `len(data.items)` SHALL ≤ 200
- **AND** `data.limit == 200`
- **AND** `data.offset == 50`
- **AND** `data.total == 1000`

#### Scenario: no hits returns empty list
- **GIVEN** 表中無 row 含 `'zzzzzzzz'`
- **WHEN** `GET /api/admin/memory/search?q=zzzzzzzz`
- **THEN** HTTP 200 with `data.items == []` 與 `data.total == 0`

#### Scenario: kind / tag query params ignored
- **GIVEN** rows with mixed kinds
- **WHEN** `GET /api/admin/memory/search?q=foo&kind=lesson&tag=vcp`
- **THEN** HTTP 200
- **AND** 結果 SHALL 等同於 `GET /api/admin/memory/search?q=foo`（kind/tag 被忽略，不影響命中集合）

---

### Requirement: Bearer auth enforced on both endpoints

兩個 endpoint SHALL 透過 router-level `Depends(require_admin)` 啟用 Bearer auth。缺 `Authorization` header 或無效 Bearer token 的請求 MUST 回 HTTP 401 with 標準 auth envelope（`auth_missing` / `auth_invalid`）— 與所有其他 `/api/admin/*` route 同行為。

#### Scenario: missing Authorization
- **WHEN** `GET /api/admin/memory/rows` 不帶 `Authorization` header
- **THEN** HTTP 401，`error.code == "auth_missing"`

#### Scenario: invalid token
- **WHEN** `GET /api/admin/memory/search?q=foo` with `Authorization: Bearer wrong`
- **THEN** HTTP 401，`error.code == "auth_invalid"`

---

### Requirement: Internal errors map to 500 envelope without leaking traceback

若 store 拋出非 `MemoryStoreError` 的例外（例如 SQLite I/O 錯誤、`json.JSONDecodeError` 在 tags 欄位上），endpoint MUST NOT leak traceback。它 SHALL 透過 `map_exception_to_envelope(...)` 映射為 HTTP 500 with `ok: false` 與適當的 `error.code`（由 shared mapper 決定，通常為 `"internal_error"`），message SHALL 為 mapper 提供的 safe 字串。

#### Scenario: corrupted tags surfaced as 500
- **GIVEN** 一筆 row 的 `tags` 欄位含非法 JSON（例如 `'not json'`），這在正常流程不會發生（沒有 writer），但若手動 INSERT 觸發
- **WHEN** request hits `GET /api/admin/memory/rows`
- **THEN** HTTP 500 with `ok: false`
- **AND** envelope SHALL NOT 含 stack trace 或 raw `JSONDecodeError` `__str__` 字串

---

### Requirement: No SSE, no write methods

本 capability SHALL NOT 引入任何 SSE event type，SHALL NOT 在 `/api/admin/memory/rows` 或 `/api/admin/memory/search` 註冊除 `GET` 以外的 HTTP method。POST/PUT/PATCH/DELETE 在這兩個 path 上 MUST 回 HTTP 405。

#### Scenario: POST not allowed on rows
- **WHEN** client 送 `POST /api/admin/memory/rows` with any body
- **THEN** HTTP 405

#### Scenario: PUT not allowed on rows
- **WHEN** client 送 `PUT /api/admin/memory/rows`
- **THEN** HTTP 405

#### Scenario: DELETE not allowed on rows
- **WHEN** client 送 `DELETE /api/admin/memory/rows`
- **THEN** HTTP 405

#### Scenario: POST not allowed on search
- **WHEN** client 送 `POST /api/admin/memory/search`
- **THEN** HTTP 405

#### Scenario: no SSE event type registered
- **WHEN** 跑完整 backend test suite
- **THEN** `EventType` enum SHALL NOT 含 `memory_*` 名稱
- **AND** `MaskedEventSerializer` / `AdminEventSerializer` 白名單 SHALL NOT 列出 memory event_type

---

### Requirement: `init_schema` wired from app lifespan

`src/ohmystock/api/app.py` 的 `_lifespan` 函式 MUST 在 startup 期間呼叫 `ohmystock.memory.init_schema(conn)` 一次（順序在 `backtest_storage.init_schema` 之後即可），並在 `try / finally` 中關閉 bootstrap connection。多次 app 重啟（例如 reload）SHALL NOT 因為重複呼叫而失敗（`init_schema` 本身已 idempotent）。

#### Scenario: lifespan creates memory schema
- **WHEN** `create_app()` 被呼叫且 lifespan 進入
- **THEN** 共用 SQLite DB 的 `sqlite_master` SHALL 含 `memory_rows`、`memory_rows_fts` 兩個 table 名稱
- **AND** lifespan 沒有引發例外

#### Scenario: lifespan re-entry idempotent
- **WHEN** 在同一個 process 內二次進入 lifespan（test client teardown + 重啟）
- **THEN** SHALL NOT 拋例外
- **AND** 既有 row 數 SHALL 不變
