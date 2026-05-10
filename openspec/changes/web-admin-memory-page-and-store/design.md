## Context

`/memory` ships today as a `ComingSoon` stub (`web-admin/src/pages/stubs.tsx:10`), and `src/ohmystock/memory/` is an empty package (only `__init__.py`). CLAUDE.md §3 commits to "SQLite + FTS5" as the storage layer for memory, and `docs/web-admin-page-designs.md` §14 reserves the page slot, but no schema, no endpoint, no UI exists.

The most recent slice that landed end-to-end with the same shape — store + read endpoint + read-only page, no writers in v0 — is `web-admin-skills-pages` (archived 2026-05-09 as `2026-05-09-web-admin-skills-pages`) sitting on top of `skill-registry-foundation` (archived 2026-05-09). That pair is the template for this change:

- Storage layer ships with a typed read API and an idempotent migration (`init_schema`); writers are deferred until producers exist (e.g. Phase 5 復盤 jobs).
- Two `GET` endpoints under `/api/admin/<capability>/...`, mounted with `Depends(require_admin)`, wrapped in the unified `{ok,data,error}` envelope, per-request `Depends(get_db)` SQLite connection.
- A read-only page replaces the stub; client-side filtering + react-query; the existing `apiFetch<T>` envelope client + Bearer auth lifecycle handles auth/401 transparently.

Trade-journal-schema (`src/ohmystock/journal/schema.py`) is the SSOT for our SQLite + FTS5 trigger pattern: external-content FTS5 over a JSON column, plus AFTER INSERT / UPDATE / DELETE triggers. The memory store follows the same shape, scaled down to a single text column and a `kind` enum.

## Goals / Non-Goals

**Goals:**

- Persist free-form operator/agent notes (notes, lessons, proposals, review summaries) so the autonomy loop has somewhere to write between sessions and Mark can grep them from `/memory`.
- One pure-function read API (`MemoryStore.list` / `MemoryStore.search`) and two GET endpoints, layered exactly like `/skills`.
- FTS5 BM25 ranking on `content`; `kind` and `tag` filters available on list (not on search v0).
- Idempotent `init_schema(conn)` callable from `_lifespan` in `api/app.py`, mirroring how `backtest_storage.init_schema` is bootstrapped today.

**Non-Goals:**

- No POST/PUT/PATCH/DELETE endpoints. v0 is read-only on a brand-new table; the empty UI is acceptable until producers land.
- No `/memory/:id` detail route. Inline expand inside the existing `<DataTable>`'s `expandedRowRender` is enough — adding a route is a routing decision better made when an editor exists.
- No tag autocomplete popover, no free-text tag suggestion. Chip-input only; tag matching is exact equality.
- No `date_from` / `date_to` filter. Recency sorting (`created_at DESC, id DESC`) is enough for v0; range filters add a UI affordance and a query plan to validate.
- No semantic / embedding-based retrieval. FTS5 BM25 only.
- No SSE event type. Memory does not stream at runtime in v0; any future writer (e.g. `memory_row_appended`) will be added in its own change.
- No combined `q + kind/tag` filter on `/search`. The page exposes 「瀏覽」 (list + filters) and 「搜尋」 (FTS5) as two distinct views; one query at a time is enough.

## Decisions

**D1. Single store module (`src/ohmystock/memory/`), three files: `schema.py`, `store.py`, `__init__.py`.** Separating schema (DDL + `init_schema`) from `store` (the typed read API) follows the trade-journal layout (`journal/schema.py` + `journal/repository.py`). `__init__.py` re-exports `MemoryRow`, `MemoryKind`, `MemoryStore`, `init_schema`, `MemoryStoreError`. Alternative considered: dump everything into one file. Rejected — the schema string blob is long and noisy; isolating it keeps the read-API surface scannable.

**D2. `kind` is a closed `Literal` enum, not a free string.** `MemoryKind = Literal["note", "lesson", "proposal", "review_summary"]`. Why: matches the `category` enum decision in `skill-registry-foundation` D3 — closed sets keep the future filter dropdown finite, mismatched typos fail at write time instead of producing phantom kinds. The four values cover what the proposal calls out: operator-authored notes, lessons learned (Phase 5 復盤), strategy-change proposals (`docs/proposals/`), and review summaries (Phase 5 节点 output). Alternative considered: open string. Rejected — every typo becomes a new kind.

**D3. `tags` stored as a JSON array string in a single column.** Schema is `tags TEXT NOT NULL DEFAULT '[]'`, written as `json.dumps(list[str])`. Filter-by-tag uses SQLite's `EXISTS (SELECT 1 FROM json_each(tags) WHERE value = ?)` parameter-bound (no string concat). Why: avoids a second `memory_row_tags` table and a join for v0; ≤ a few hundred rows means scan-and-decode is cheap; `json_each` keeps the SQL parameter-bound (no injection surface). Alternative considered: separate `memory_tags(memory_id, tag)` table with a FK. Rejected as YAGNI for v0; can be added later if tag analytics need it.

**D4. FTS5 indexes only `content`, not `tags` or `kind`.** Tag/kind filtering is exact-match on indexed columns; full-text matching across them adds noise (e.g. searching `"note"` would match the kind column on every note row). Why: keeps FTS5 row size small and the BM25 scoring focused. Alternative considered: include `tags` joined with spaces in the FTS5 row. Rejected — tags are short keywords; if you want to filter by them, use the list endpoint with `?tag=`.

**D5. FTS5 is `content='memory_rows'` external-content table, kept in sync via three triggers.** Same pattern as `journal_entries_fts`. Why: avoids storing `content` twice on disk; the triggers (`_ai`, `_au`, `_ad`) are 1:1 mirrored from `journal/schema.py`. Alternative considered: contentless FTS5 (just stores the postings, requires manual rebuild). Rejected — external-content + triggers is what the rest of the codebase already uses; introducing a second pattern is gratuitous.

**D6. `MemoryStore.search` builds the FTS5 `MATCH` query from a sanitised `q`.** Strip ASCII control chars (`\x00-\x1F`, `\x7F`); reject empty / whitespace-only `q` with `MemoryStoreError("invalid_input")`. Pass the cleaned string verbatim into `MATCH ?` (parameter bind, no string concat). FTS5 syntax errors (e.g. trailing `OR`) are caught as `sqlite3.OperationalError` and remapped to `MemoryStoreError("invalid_query")` so the route can return 400 without leaking the raw SQLite error text. Why: gives the operator full FTS5 expression power (Mark wants `"VCP AND breakout"`) without trusting them not to type control chars; the parameter bind keeps SQL injection out, the syntax-error remap keeps the envelope clean. Alternative considered: pre-tokenise and quote each term. Rejected — would silently break advanced queries (`OR`, prefix `*`, `NEAR/2`).

**D7. Two endpoints, not one.** `GET /api/admin/memory/rows` for paginated recency-sorted listing with `kind` / `tag` filters; `GET /api/admin/memory/search` for FTS5 BM25-ranked results. Why split: the response contract differs (recency vs. rank), and the client wrappers stay simpler than a mode-toggling single endpoint. Alternative considered: single `?q=...` parameter on `/rows`. Rejected — the response shape would diverge, making the wrapper bigger and the failure modes ambiguous (is no `q` "list everything" or "missing required filter"?).

**D8. Both endpoints ship the FULL `content` on every row PLUS a `content_preview` (≤200 chars) and a `content_truncated: bool` flag.** Why: memory rows are typically short (notes / one-paragraph lessons) — at v0 scale, total list payload sits well under 200KB even when fully expanded. Shipping `content` lets the inline `expandedRowRender` show the full body without a second round-trip; shipping `content_preview` lets the cell render a stable truncated form without the client doing its own slice. The skills endpoint splits list/detail because skill bodies can be tens of KB; memory rows are not. Alternative considered: detail-only `content`. Rejected — adds a per-row expand round-trip the data size doesn't justify.

**D9. Pagination via `limit` (default 50, server-clamp ≤ 200) + `offset`, with `total` and `has_more` in the envelope.** Same shape as `GET /api/admin/journal/rows`. Why: the journal route is the established pattern; reusing it lets the page reuse the same pagination component. `limit` clamp protects the server even if the client misbehaves.

**D10. `MemoryStore.list` returns rows ordered `created_at DESC, id DESC`. `MemoryStore.search` returns rows ordered by FTS5 BM25 ascending (lower BM25 = better match).** Two different sorts because the two views answer different questions. The spec pins the order so a future client can rely on it.

**D11. `init_schema` is wired from `_lifespan` in `api/app.py`, after `backtest_storage.init_schema`.** Idempotent, in a `try/finally` that closes the bootstrap connection. Why: matches what `backtest_storage` already does; ensures the table exists even on a fresh dev DB without relying on per-handler init checks.

**D12. Defence-in-depth + envelope reuse.** Both endpoints sit on the router-level `Depends(require_admin)`; both wrap success in `to_success(...)` and exceptions in `map_exception_to_envelope(...)`. `kind` query param is validated against the `MemoryKind` `Literal` set BEFORE SQL; `tag` is parameter-bound; `limit` is clamped server-side to 200. No path component carries user input (no `/memory/{id}` route), so no path-traversal surface to mirror.

**D13. The page replaces the stub with `MemoryPage`; no detail route, no router-tree change beyond the import swap.** Two views toggled by a segmented control: 「瀏覽」 (kind select + tag chip-input + 5-col table + pagination) and 「搜尋」 (single search input with Cmd/Ctrl+Enter + 5-col table). Inline `expandedRowRender` reveals the full `content` in a `<pre className="whitespace-pre-wrap font-mono text-sm">` block with a char-count line and `max-h-[70vh] overflow-auto`, mirroring the body block in `SkillDetailPage`. Why: lets the user read full notes without a second route.

## Risks / Trade-offs

- **[Risk] Storing tags as a JSON array means tag-only analytics are O(rows) full scans.** → Mitigation: at v0 scale the table is small and the list endpoint always paginates. If tag analytics ever need to be fast, a separate `memory_row_tags(memory_id, tag)` table can be added without breaking the read API (the existing column stays the SSOT). Documented in Open Questions.
- **[Risk] FTS5 BM25 ordering can surprise users used to recency.** → Mitigation: the page's segmented control makes the difference explicit (「瀏覽」 = recent, 「搜尋」 = ranked); the spec pins the order so a future client can show "BM25 score" if needed. We don't expose BM25 score in the API today (cosmetic; can add later).
- **[Risk] Allowing raw FTS5 expressions through `q` means a malformed query like `"foo OR"` returns 400.** → Mitigation: the route remaps the SQLite operational error to `invalid_query` with a generic message; the message does NOT include the original `sqlite3.OperationalError` text (would leak parser internals). The page renders a friendly "查詢語法錯誤" string; the developer can read the actual error from server logs.
- **[Risk] `content` is operator-authored free text and could in principle hold accidentally-pasted secrets.** → Mitigation: the proposal calls this out explicitly; the autonomy-loop writers (Phase 5 復盤, proposal jobs) will land in their own changes and can choose to sanitise on write. v0 has no writer at all, so the surface is operator's own behaviour. The store does not mask anything on read.
- **[Trade-off] Shipping full `content` on list responses (D8) makes payloads larger than `/skills` (which split list/detail).** → Acceptable trade: memory rows are short, and the saved round-trip is worth it for the inline-expand UX. If a future writer pushes multi-KB summaries that bloat the list, splitting into a detail endpoint stays open.
- **[Trade-off] No tag autocomplete means the operator must remember tag names (or grep prior rows).** → Acceptable for v0; defer until tag count grows past ~20 and the friction shows up.
- **[Trade-off] No `/memory/:id` detail route means deep-linking to a specific row is not possible.** → Acceptable; until an editor exists, deep-linking adds no value.

## Migration Plan

Purely additive; no data migration. Deployment steps:

1. Backend: add `src/ohmystock/memory/{__init__,schema,store}.py`; wire `init_schema` into `_lifespan` in `api/app.py`; add `routes/memory.py`; register the router. Run `pytest`.
2. Frontend: add `MemoryPage`, drop `MemoryPage` from `stubs.tsx`, swap the import in `router.tsx`. Extend `lib/api.ts` with `MemoryRow` / `MemoryRowsResponse` / `MemoryKind` / `listMemory` / `searchMemory`. Run `pnpm test` + `pnpm build`.
3. Smoke (manual, deferred under a checkbox): hit `GET /api/admin/memory/rows` with a real Bearer token (expect empty list, `total: 0`); hit `GET /api/admin/memory/search?q=anything` (expect empty list); load `/memory` in the browser and verify both empty states render.
4. Update `docs/web-admin-page-designs.md` §14 to mark v0 scope (no insert/edit, no autocomplete, no date range, no semantic search).
5. Add a CLAUDE.md §5 SSOT row pointing at the new spec files, store module paths, and endpoint module path.
6. Push to `main` directly (per project memory `feedback_direct_push_main`); message follows `feat(web-admin): /<page>` convention.

Rollback: revert the commit; the stub comes back automatically and the new SQLite tables become dead weight (no rows are ever written until a producer change lands).

## Open Questions

- **Should tags get their own indexed table now or later?** Tentatively later. v0 has zero tag analytics demand; postpone until a feature actually needs `SELECT tag, COUNT(*) ... GROUP BY tag`.
- **Should the search endpoint expose the BM25 score so the UI can show match strength?** Tentatively no for v0 — the rank IS the score, and rendering it as "0.42" is more confusing than helpful. Revisit if operators ask.
- **Should we cap `content` length on write?** No write path exists yet, so the question is moot until a producer lands. The producer change can pick its own cap (proposal generators may need ~10KB summaries; quick notes will be ≤ 1KB).
