## Why

`/memory` is currently a `ComingSoon` stub (`web-admin/src/pages/stubs.tsx:14`) and `src/ohmystock/memory/` ships only `__init__.py` — there is no storage, no endpoint, no UI. CLAUDE.md §3 lists "SQLite + FTS5 (trade journal、memory、復盤索引)" as the chosen storage, and `docs/web-admin-page-designs.md` §14 has reserved this slot since v3 design, but the foundation has never been laid.

Mark needs a place to drop notes, lessons, proposals, and Phase-5 復盤 summaries that are fulltext-searchable from the admin UI. Today there is nowhere to put them: trade journal is decision-shaped (entry/exit rows keyed by `decision_id`), not free-form. Without a memory store, the autonomy loop cannot persist anything between sessions, and the operator cannot grep "did I already decide X?" without ad-hoc files. This change ships the smallest end-to-end slice — store + 2 read endpoints + read-only page — mirroring the `/skills` pattern that landed 2026-05-09: storage and inspection first, write paths later when the producer (Phase 5 復盤 / proposal jobs) actually exists.

## What Changes

- New `src/ohmystock/memory/` module: SQLite table `memory_rows` + FTS5 contentless index `memory_rows_fts` with insert/update/delete triggers; `MemoryStore` with `list(...)` and `search(...)` read methods. Schema is closed (`kind` is a `Literal`-typed enum: `note`, `lesson`, `proposal`, `review_summary`). Idempotent `init_schema(conn)` callable from app lifespan.
- New `GET /api/admin/memory/rows`: paginated list with optional `kind` and `tag` filters. Default `limit=50`, max 200; rows ordered `created_at DESC, id DESC`; payload includes `content_preview` (≤200 codepoints + `content_truncated` flag) — full body is NOT shipped over list.
- New `GET /api/admin/memory/search`: FTS5 BM25-ranked search over `content`. Empty / whitespace-only `q` → 400 `invalid_input`. FTS5 syntax errors caught and mapped to 400 (no traceback leak). No `kind`/`tag` filter on search v0 (deferred; the page can pre-filter by switching tabs and re-querying list).
- New `MemoryPage` (`/memory`): replaces the stub. Two-section layout (segmented control: 「瀏覽」/ 「搜尋」). 瀏覽 view = kind `<Select>` + tag chip-input + 5-col `<DataTable>` (時間 / kind / tags / 內容預覽 / 來源) + pagination buttons. 搜尋 view = single search input + Cmd/Ctrl+Enter + same 5-col `<DataTable>` rendering BM25 results. Click-to-expand a row reveals the full `content` inside the existing `expandedRowRender` slot (`<pre className="whitespace-pre-wrap font-mono text-sm">`, char count, `max-h-[70vh] overflow-auto`) — no detail route.
- Extend `web-admin/src/lib/api.ts` with `MemoryRow` / `MemoryRowsResponse` types + `MemoryKind` literal + `listMemory(...)` / `searchMemory(...)` wrappers.
- Update `docs/web-admin-page-designs.md` §14 to mark v0 scope (no insert/edit, no autocomplete, no date range, no semantic search).
- Add CLAUDE.md §5 SSOT row pointing at the new specs, store module, and endpoint paths.

Out of scope (deferred, explicitly):

- POST/PUT/PATCH/DELETE — memory v0 is read-only; future writers (Phase 5 復盤 jobs, proposal generators) will land their own change.
- Per-row detail route `/memory/:id` — inline expand is enough; routing decisions can be made when an editor exists.
- Tag autocomplete popover, free-text tag suggestion — chip-input only.
- Date-range filter (`date_from`/`date_to`) — defer; recency sorting is enough for v0.
- Semantic / embedding-based retrieval — FTS5 BM25 only.
- SSE — memory does not stream at runtime in v0.
- Server-side `q + kind/tag` combined filter on `/search` — defer; list+filter and search are two distinct views in v0.

## Capabilities

### New Capabilities

- `memory-store`: SQLite + FTS5 storage layer for free-form memory rows. Schema, triggers, idempotent migration, and read-only `MemoryStore.list` / `MemoryStore.search` API. No write methods exposed in this capability.
- `admin-memory-endpoints`: `GET /api/admin/memory/rows` (paginated list with `kind` / `tag` filters) and `GET /api/admin/memory/search` (FTS5 BM25), gated by Bearer auth, unified `{ok,data,error}` envelope, per-request SQLite connection.
- `web-admin-memory-page`: `/memory` route — segmented 瀏覽 / 搜尋 view replacing the existing stub.

### Modified Capabilities

- (none — fresh capabilities; no existing requirement changes.)

## Impact

- **Code**: new `src/ohmystock/memory/{__init__,schema,store}.py`; new `src/ohmystock/api/routes/memory.py` + register in `api/app.py`; FTS5 init wired into `_lifespan` (mirrors `disposition_list_cache` startup pattern in `api/app.py`); new `web-admin/src/pages/MemoryPage.tsx`; remove `MemoryPage` from `web-admin/src/pages/stubs.tsx`; update `web-admin/src/router.tsx` import; extend `web-admin/src/lib/api.ts`. Tests for store (`tests/memory/test_store.py`), endpoint (`tests/api/test_memory_endpoint.py`), page (`web-admin/src/pages/__tests__/MemoryPage.test.tsx`).
- **APIs**: 2 new GET endpoints. 1 new SQLite table + 1 FTS5 virtual table + 3 triggers. No SSE event types added. No envelope changes.
- **Dependencies**: none. Reuses already-installed `pydantic`, `react-query`, shadcn primitives, and SQLite FTS5 (already used by trade journal).
- **Security**: query-string sanitisation on FTS5 input strips control chars; `kind` validated against the closed `Literal` set BEFORE SQL; tag filter is parameter-bound (no string concat into SQL); `limit` clamped server-side. No path-traversal surface (no filename in URL). No secret data is ever stored — `content` is always operator-authored text or autonomy-loop output, never API keys.
- **Risk**: low. Read-only on a brand-new table; no broker behaviour change, no breaker change, no migration of existing data. Misuse worst-case is an empty UI on first deploy until a writer lands; the page is built to render the empty state cleanly.
