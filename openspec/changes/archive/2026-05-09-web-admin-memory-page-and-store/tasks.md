## 1. Backend — `memory/` package skeleton

- [x] 1.1 Replace `src/ohmystock/memory/__init__.py` (currently empty) with re-exports for `MemoryRow`, `MemoryKind`, `MemoryStore`, `MemoryStoreError`, `init_schema`. Set `__all__` to those five names.
- [x] 1.2 Create `src/ohmystock/memory/store.py` with `MemoryKind = Literal["note","lesson","proposal","review_summary"]`, `_ALLOWED_KINDS` tuple, and `MemoryRow` (`pydantic.BaseModel`, `model_config = ConfigDict(frozen=True, extra="forbid")`) holding `id / kind / content / tags / source / created_at`.
- [x] 1.3 Add `ListResult` pydantic model in `store.py` (`frozen`, `extra="forbid"`) with `items / total / limit / offset / has_more`.
- [x] 1.4 Define `class MemoryStoreError(Exception)` with `code: str` + optional `message: str | None`; `__str__` returns `code` or `f"{code}: {message}"`.

## 2. Backend — schema migration

- [x] 2.1 Create `src/ohmystock/memory/schema.py` defining `_DDL_MEMORY_ROWS` (table with `kind` CHECK + `tags TEXT NOT NULL DEFAULT '[]'`), `_DDL_INDEX_KIND_CREATED_AT`, `_DDL_INDEX_CREATED_AT`, `_DDL_FTS` (`memory_rows_fts` external-content over `content`), and `_DDL_TRIGGER_AI / _AU / _AD` mirroring `journal/schema.py`.
- [x] 2.2 Implement `_probe_fts5(conn)` (private helper; can be a copy of `journal.schema._probe_fts5`).
- [x] 2.3 Implement `init_schema(conn: sqlite3.Connection) -> None` that calls `_probe_fts5`, then runs all DDL inside a single `with conn:` block. All statements use `IF NOT EXISTS`.
- [x] 2.4 Re-export `init_schema` from `memory/__init__.py` (already in 1.1).

## 3. Backend — `MemoryStore` read API

- [x] 3.1 Implement `MemoryStore.__init__(self, conn)` storing the connection.
- [x] 3.2 Implement `_clamp_limit(limit) -> int` (≤ 200; raise `MemoryStoreError("invalid_input")` on `<= 0`) and `_validate_offset(offset)` (raise on `< 0`) helpers.
- [x] 3.3 Implement `MemoryStore.list(*, kind=None, tag=None, limit=50, offset=0) -> ListResult`. Validate `kind` against `_ALLOWED_KINDS` (None pass-through, empty string and unknowns raise `invalid_input`). Build SQL with optional `WHERE kind = ?` and `EXISTS (SELECT 1 FROM json_each(tags) WHERE value = ?)` clauses, parameter-bound. `ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?`. Compute `total` via separate `COUNT(*)` over the same WHERE.
- [x] 3.4 In `list`, decode `tags` via `json.loads(row[3])` before constructing `MemoryRow`. If decode fails, let it propagate as `json.JSONDecodeError` (route layer maps to 500).
- [x] 3.5 Implement `_sanitise_q(q: str) -> str`: strip whitespace, then `re.sub(r'[\x00-\x1f\x7f]', '', q)`. Empty result raises `invalid_input`.
- [x] 3.6 Implement `MemoryStore.search(*, q, limit=50, offset=0) -> ListResult`. Use `_sanitise_q`, parameter-bind into `SELECT ... FROM memory_rows_fts JOIN memory_rows ON memory_rows.id = memory_rows_fts.rowid WHERE memory_rows_fts MATCH ? ORDER BY bm25(memory_rows_fts) ASC, memory_rows.id ASC LIMIT ? OFFSET ?`. Compute `total` via separate `SELECT COUNT(*) FROM memory_rows_fts WHERE memory_rows_fts MATCH ?`.
- [x] 3.7 In `search`, wrap `sqlite3.OperationalError` whose `str(exc)` matches `/fts5|syntax error/i` in `MemoryStoreError("invalid_query", "FTS5 query syntax error")`. Other `OperationalError` propagates.

## 4. Backend — store unit tests

- [x] 4.1 Create `tests/test_memory_schema.py` (flat layout per project convention; not `tests/memory/`). Use `:memory:` `sqlite3.Connection` fixture.
- [x] 4.2 Test `init_schema` on empty DB: `sqlite_master` contains `memory_rows`, `memory_rows_fts`, `memory_rows_ai/au/ad`, `idx_memory_rows_kind_created_at`, `idx_memory_rows_created_at`.
- [x] 4.3 Test `init_schema` idempotency: call twice, no error, row count unchanged.
- [x] 4.4 Test `kind` CHECK rejects `'random'` (`IntegrityError`).
- [x] 4.5 Test `tags` default `'[]'` (insert without column).
- [x] 4.6 Test FTS5 trigger sync on INSERT, UPDATE, DELETE.
- [x] 4.7 Test FTS5 absence: monkey-patch `_probe_fts5` to raise; assert `init_schema` raises `RuntimeError` with `"FTS5"` in message.
- [x] 4.8 Create `tests/test_memory_store.py` with a fixture that runs `init_schema` and inserts a small dataset (~5 rows mixing kinds and tags).
- [x] 4.9 Test `list()` empty DB returns empty `ListResult`.
- [x] 4.10 Test `list()` ordering `created_at DESC, id DESC` with two same-timestamp rows.
- [x] 4.11 Test `list(kind='lesson')` filters; `total` matches.
- [x] 4.12 Test `list(tag='vcp')` filters via `json_each` exact match.
- [x] 4.13 Test `list(kind='lesson', tag='vcp')` combined filter.
- [x] 4.14 Test `list(limit=999)` clamps to 200; `list(limit=0)` raises `invalid_input`; `list(offset=-1)` raises `invalid_input`; `list(kind='garbage')` raises `invalid_input`.
- [x] 4.15 Test `search(q='breakout')` returns BM25-ordered hits, id with higher freq first.
- [x] 4.16 Test `search(q='')`, `search(q='   ')`, and `search(q='\x00\x01')` all raise `invalid_input`.
- [x] 4.17 Test `search(q='hello\x00 world')` strips control char and still hits a row containing "hello world".
- [x] 4.18 Test `search(q='foo OR')` raises `MemoryStoreError("invalid_query")` and `str(error)` does NOT contain `"fts5"` or the raw `OperationalError` message.
- [x] 4.19 Test `search(q='VCP AND breakout')` honours FTS5 boolean expressions.
- [x] 4.20 Test `search(limit=999)` clamps to 200.
- [x] 4.21 Test `MemoryStore` exposes no `add` / `update` / `delete` attrs (`hasattr` returns False).
- [x] 4.22 Test `__init__.py` re-exports exactly the 5 expected names; `__all__` matches.

## 5. Backend — `routes/memory.py`

- [x] 5.1 Create `src/ohmystock/api/routes/memory.py` with router-level `Depends(require_admin)`. Import `MemoryStore`, `MemoryStoreError`, `MemoryKind`. No SSE, no other HTTP methods.
- [x] 5.2 Implement `_row_to_json(row: MemoryRow) -> dict[str, Any]` that adds `content_preview = row.content[:200]` and `content_truncated = len(row.content) > 200` and serialises `tags` as list (already list).
- [x] 5.3 Implement `GET /api/admin/memory/rows` handler. Accept `kind / tag / limit / offset` via `Query(...)`. Treat empty-string `tag` as `None` (delegated to store). Inside `try`, call `MemoryStore(conn).list(...)`; on `MemoryStoreError("invalid_input")` return 400 envelope; on other `Exception` go through `map_exception_to_envelope`. On success, build `data = {"items": [_row_to_json(r) for r in result.items], "total": result.total, "limit": result.limit, "offset": result.offset, "has_more": result.has_more}` and return `JSONResponse(200, to_success(data))`.
- [x] 5.4 Implement `GET /api/admin/memory/search` handler. `q` is a required `Query(...)` (no default). Accept optional `limit / offset`. Ignore unknown query params (don't 400). Inside `try`, call `MemoryStore(conn).search(q=q, limit=limit, offset=offset)`. On `MemoryStoreError` map `code=invalid_input` to 400 with that code; map `code=invalid_query` to 400 with that code and a generic message. Other `Exception` → `map_exception_to_envelope`. Success path identical to `/rows`.
- [x] 5.5 Add memory router to `src/ohmystock/api/app.py` next to other admin routers (`app.include_router(memory_router)`).

## 6. Backend — wire `init_schema` into app lifespan

- [x] 6.1 In `src/ohmystock/api/app.py::_lifespan`, reuse the existing `init_conn = get_connection()` block, call `ohmystock.memory.init_schema(init_conn)` after `backtest_storage.init_schema(init_conn)` inside the same `try/finally`. Keep idempotency invariant.
- [x] 6.2 Update `_lifespan` docstring to note memory schema bootstrap alongside backtest.

## 7. Backend — endpoint tests

- [x] 7.1 Create `tests/api/test_memory_endpoint.py`. Use `AsyncClient + ASGITransport` (matches existing endpoint tests) with admin token; seed `memory_rows` directly via `init_schema` + raw SQL inside the conftest fixture.
- [x] 7.2 Test 200 list shape on empty DB: `{"ok": true, "data": {"items": [], "total": 0, "limit": 50, "offset": 0, "has_more": false}}`.
- [x] 7.3 Test 200 list ordering: insert two rows with different `created_at`; assert `items[0].id` is the newer row.
- [x] 7.4 Test `content_preview` truncation on a 250-char content row (`content_truncated == true`, preview length 200, full `content` still 250).
- [x] 7.5 Test `kind=lesson` filter; assert `total` matches.
- [x] 7.6 Test `tag=vcp` filter via JSON column; assert ids match.
- [x] 7.7 Test combined `kind` + `tag`.
- [x] 7.8 Test pagination: insert 100 rows, request `limit=20&offset=40`, assert lengths and `has_more=true`; request `offset=80`, assert `has_more=false`.
- [x] 7.9 Test `limit=999` clamped to 200; `data.limit == 200`.
- [x] 7.10 Test invalid params: `kind=garbage` → 400 `invalid_input`; `limit=0` → 400; `offset=-1` → 400; `tag=` (empty) → 200 (treated as absent).
- [x] 7.11 Test 200 search ordering: insert three rows, `q=breakout`, assert id order matches BM25 (highest-freq id first).
- [x] 7.12 Test `q=` and `q=%20%20%20` → 400 `invalid_input`. Test missing `q` → 422.
- [x] 7.13 Test `q=foo+OR` (URL-encoded `'foo OR'`) → 400 `invalid_query`; assert response body does NOT contain `"sqlite3"`, raw `"fts5: syntax error"`, or `"Traceback"`. The canned message `"FTS5 query syntax error"` is permitted.
- [x] 7.14 Test `q=VCP+AND+breakout` returns only rows containing both terms.
- [x] 7.15 Test response shape on search includes the same `MemoryRowJSON` keys as list and does NOT include `bm25_score` or `score`.
- [x] 7.16 Test `q=foo&kind=lesson&tag=vcp` is treated as `q=foo` only (kind/tag ignored on search).
- [x] 7.17 Test 401 `auth_missing` and `auth_invalid` for both `/rows` and `/search`.
- [x] 7.18 Test 405 for `POST` / `PUT` / `DELETE` / `PATCH` on `/rows` and `/search`.
- [x] 7.19 Test 500 `internal_error` path: monkey-patch `MemoryStore.list` to raise `RuntimeError`; assert 500, `ok=false`, no `Traceback` or original message in response body.
- [x] 7.20 Test lifespan side-effect: drive `app.router.lifespan_context(app)` directly with a tmp-file SQLite path; assert `memory_rows` and `memory_rows_fts` tables exist after teardown. (`ASGITransport` does not auto-trigger lifespan, hence the direct context-manager usage.)

## 8. Frontend — API client wrappers

- [x] 8.1 In `web-admin/src/lib/api.ts`, add `MemoryKind` literal type and `MemoryRow` / `MemoryRowsResponse` types matching the spec exactly.
- [x] 8.2 Add `listMemory(params: { kind?: MemoryKind; tag?: string; limit?: number; offset?: number } = {}): Promise<MemoryRowsResponse>`. Build the URL by filtering out `undefined` and empty-string values; encode each value with `encodeURIComponent`; if no params remain, omit the trailing `?`.
- [x] 8.3 Add `searchMemory(params: { q: string; limit?: number; offset?: number }): Promise<MemoryRowsResponse>`. Always include `q` (even when empty/whitespace; let the server reject). Encode params with `encodeURIComponent`.
- [x] 8.4 In `web-admin/src/lib/__tests__/api.test.ts`, stub `fetch` and assert: (a) `listMemory({})` calls `/api/admin/memory/rows` with no query string; (b) `listMemory({ kind: 'lesson', tag: 'vcp', limit: 20, offset: 40 })` builds the expected URL; (c) `searchMemory({ q: 'foo bar 中文' })` encodes `q` correctly. Plus envelope-error pass-through for both wrappers.

## 9. Frontend — `MemoryPage`

- [x] 9.1 Create `web-admin/src/pages/MemoryPage.tsx` with `<h1>長期記憶</h1>` + one-line description.
- [x] 9.2 Implement segmented control with two tabs: `'browse' | 'search'`. Default `'browse'`. Each view is mounted with a stable `key` so switching tabs re-mounts the view (resets DataTable's internal `expandedKey`).
- [x] 9.3 Implement the「瀏覽」view: kind `<select>` (5 options), single-tag chip-input, `<DataTable>` with the 5 columns from the spec, pagination via DataTable's built-in pager. `useQuery({ queryKey: ['memory', 'rows', kind, tag, offset], queryFn: () => listMemory({ kind: kind === 'all' ? undefined : kind, tag, limit: 50, offset }), retry: false })`.
- [x] 9.4 Implement the「搜尋」view: `<input>` with placeholder, `<Button>` "搜尋", same `<DataTable>`. State: `draft` (input value), `submittedQ` (queried value), `offset`. Trigger query via `useQuery({ queryKey: ['memory', 'search', submittedQ, offset], queryFn: () => searchMemory({ q: submittedQ, limit: 50, offset }), enabled: Boolean(submittedQ.trim().length > 0), retry: false })`. Bind Enter / Cmd+Enter / Ctrl+Enter to submit.
- [x] 9.5 Empty / whitespace input does NOT call `searchMemory` (button disabled, `enabled: false` on react-query); pre-submit empty state renders inline "請輸入查詢關鍵字" prompt.
- [x] 9.6 Column renderers implemented (時間 / kind / tags / 內容預覽 / 來源). Kind label map applied; shadcn `Badge variant="secondary"` for kind; `<code>` chips for tags; `—` fallback for empty tags / null source.
- [x] 9.7 `expandedRowRender(row)` returns a Card with `<pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap font-mono text-sm">{row.content}</pre>` and a `{row.content.length} 字元` line above it. (DataTable's expandedRowRender API used as-is — no second fetch.)
- [x] 9.8 Loading state: DataTable renders 6 `Skeleton` rows; filter / search controls set to `disabled` while `q.isLoading`.
- [x] 9.9 Empty states implemented (default-no-rows, filtered-no-rows with 「清除 filter」 button, search-no-hits with `submittedQ` quoted). Pre-submit empty rendered separately.
- [x] 9.10 Error state: top-of-view destructive `Card` + `AlertCircle` + 「重試」 (`q.refetch()`); inline 「查詢語法錯誤」 card when `error.code === 'invalid_query'`.
- [x] 9.11 Pagination footer comes from DataTable's built-in pager (`pageSize` + `total` + `page` + `onPageChange`); `<= 1` disables prev, `>= totalPages` disables next; clicking updates `offset` and react-query re-runs via key change.

## 10. Frontend — wiring + tests

- [x] 10.1 Remove `MemoryPage` from `web-admin/src/pages/stubs.tsx`.
- [x] 10.2 Update `web-admin/src/router.tsx` to import `MemoryPage` from `@/pages/MemoryPage`. Existing router-smoke test still passes.
- [x] 10.3 Add `web-admin/src/pages/__tests__/MemoryPage.test.tsx` (11 cases) covering: (a)「瀏覽」default fires `listMemory` without kind/tag filters; (b) selecting kind triggers refetch with `kind`; (c) adding a tag chip triggers refetch with `tag`; (d) clicking a row expands and shows full content + char count; (e) switching tabs collapses the expanded row; (f) default empty state renders the seed-hint message; (g) filtered empty state renders 「清除 filter」 button + clicking refetches; (h) error state renders retry that calls `refetch`; (i)「搜尋」empty input renders prompt and never fires `searchMemory`; (j) Ctrl+Enter triggers `searchMemory`; (k) `invalid_query` renders the friendly inline error (and 重試 NOT shown).
- [x] 10.4 Run vitest (194 passed across 19 files) and `tsc -b && vite build` (492 KB bundle, 145 KB gzip) inside `web-admin/`; both green.

## 11. Docs / SSOT

- [x] 11.1 In `docs/web-admin-page-designs.md` §14, added a "v0 範圍" callout above the wireframe stating that insert / edit / delete / tag autocomplete / date-range filter / semantic search are deferred, and listing what v0 actually renders (segmented control 「瀏覽」/「搜尋」, kind select + 1-tag chip-input, 5-col DataTable with inline expand). Backend status flipped from ❌ to ✅ with spec links + ship date.
- [x] 11.2 In `CLAUDE.md` §5, added a row pointing at the new spec files (`openspec/specs/memory-store/spec.md`, `openspec/specs/admin-memory-endpoints/spec.md`, `openspec/specs/web-admin-memory-page/spec.md` — paths post-archive), the store module (`src/ohmystock/memory/{__init__,schema,store}.py`), the route module + lifespan wiring (`src/ohmystock/api/routes/memory.py`, `src/ohmystock/api/app.py::_lifespan`), and the page (`web-admin/src/pages/MemoryPage.tsx`). Mirrors the format of the `web-admin Skills pages` row directly above it.

## 12. Smoke + ship

- [x] 12.1 Ran `uv run pytest tests/test_memory_schema.py tests/test_memory_store.py -q` — 33 passed.
- [x] 12.2 Ran `uv run pytest tests/api/test_memory_endpoint.py -q` — 34 passed.
- [x] 12.3 Ran full backend pytest `uv run pytest -q` — **1085 passed**, no regressions.
- [x] 12.4 Inside `web-admin/`, ran `vitest run` (**194 passed across 19 files**) and `tsc -b && vite build` (492 KB / 145 KB gzip) — both green.
- [x] 12.5 Manual smoke — verified by user; also covered by automated tests 7.1–7.20 (envelope shape, auth, 405/422/500 paths, lifespan side-effect) and the page-level vitest cases (browse default, kind/tag refetch, expand, empty/error states, search Cmd+Enter, invalid_query inline error).
- [x] 12.6 Ran `openspec validate web-admin-memory-page-and-store --strict` — `Change 'web-admin-memory-page-and-store' is valid`.
- [x] 12.7 Commit + push to `main` directly (per project memory `feedback_direct_push_main`) — `115c5a9 feat(web-admin): /memory + memory-store + admin-memory-endpoints (read-only v0)` pushed to `origin/main`.
