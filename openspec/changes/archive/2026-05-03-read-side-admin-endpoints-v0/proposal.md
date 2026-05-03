## Why

Phase 4 backend currently exposes 6 write endpoints under `/api/admin/*` but **zero read endpoints**, so the planned `web-admin/` frontend (18 pages, scaffolding pending) cannot render journal rows, open positions, or daily stats. Without reads, every page is blocked on backend data — admin shell would be a hollow login screen. Adding 4 narrow read endpoints unblocks parallel frontend work and makes the existing SSE stream useful (UI can hydrate from REST + tail SSE for deltas).

## What Changes

- **Add `GET /api/admin/journal/rows`** — paginated journal list with `kind`, `symbol`, `date_from`, `date_to`, `limit`, `offset` query params; returns rows in canonical journal schema shape with stable ordering (`created_at DESC, id DESC`).
- **Add `GET /api/admin/journal/decisions/{decision_id}`** — full decision detail: all rows sharing the same `decision_id` (`kind` ∈ `entry / exit / reject / expire / auto_execute_audit`), ordered by `created_at ASC, id ASC`. Note: there is no `fill` kind — fill data is folded into the entry row's `payload_json` (`actual_entry_price`, `actual_qty`) after confirm.
- **Add `GET /api/admin/positions/open`** — list of currently-open positions, defined as entry rows whose `payload_json` has a non-null `actual_entry_price` (i.e. confirmed/filled) AND no matching `kind=exit` row exists for the same `decision_id`. Each item includes `decision_id`, `symbol`, `entry_price`, `qty_lots`, `entry_ts`, `hold_days`, `stop_loss`, `t1_target`, `time_stop_date` (the latter three lifted from entry payload when present, else `null`). Reuses the existing `ohmystock.journal.repository.open_positions` helper.
- **Add `GET /api/admin/stats/today`** — counters for today (TPE +08:00 calendar day): `decisions_made` (entry rows), `entries_pending` (entry rows whose payload still has no `actual_entry_price`), `entries_filled` (entry rows with `actual_entry_price` set), `rejects`, `expires`, `auto_execute_audits`. All derived from `journal_entries` row `kind` + `payload_json` filtered by `created_at` prefix `YYYY-MM-DD` of today (TPE). `screener_runs` and breaker counters are not journal-backed in v0 and are explicitly excluded.
- All four endpoints reuse the existing **unified `{ok, data, error}` envelope**, **per-request `sqlite3.Connection`** dependency, **`Depends(require_admin)`** Bearer auth gate, and the same HTTP status mapping (`invalid_input`→400, `internal_error`→500). No SSE emission added (`journal_queried` is deferred to a future change).

## Capabilities

### New Capabilities
- `admin-read-endpoints`: 4 read-only `/api/admin/*` GET endpoints (journal rows list, decision detail, open positions, today stats) with shared envelope/auth/per-request-conn invariants. Disjoint from `server-action-endpoints` which owns write/action routes.

### Modified Capabilities
<!-- none — write endpoints, auth, eventbus, and emitters specs are unchanged. -->

## Impact

- **Code**:
  - `src/ohmystock/api/routes/journal.py` (new) — `journal/rows`, `journal/decisions/{id}` handlers + Pydantic response models
  - `src/ohmystock/api/routes/positions.py` (new) — `positions/open` handler (delegates to `ohmystock.journal.repository.open_positions`)
  - `src/ohmystock/api/routes/stats.py` (new) — `stats/today` handler (single SQL aggregate)
  - `src/ohmystock/api/app.py` — `include_router(...)` 3 additional routers
  - `tests/test_api_journal_endpoints.py`, `tests/test_api_positions_endpoint.py`, `tests/test_api_stats_endpoint.py` (new)
- **Specs**: 1 new `openspec/specs/admin-read-endpoints/spec.md` after archive.
- **Schema/SSOT**: read endpoints query the existing `trade_journal` table only; **no schema migrations**, **no new event_type emissions**.
- **Out of scope (deferred)**:
  - `journal_queried` event emission (would need wiring to bus; not blocking frontend)
  - Read-side caching / ETag headers (premature for solo localhost)
  - FTS5 full-text search endpoint (separate change when reviewer/proposer pages need it)
  - Any write or mutation behaviour
- **Dependencies**: no new pip packages; `web-admin-bearer-auth` and `server-action-endpoints` capabilities already provide the envelope helper, `require_admin` dep, and `get_connection` dep.
