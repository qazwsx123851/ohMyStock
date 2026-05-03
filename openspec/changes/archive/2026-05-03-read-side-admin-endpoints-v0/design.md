## Context

`server-action-endpoints-v0` shipped 6 write endpoints that proxy screener / confirm-gate / exit-engine actions; `web-admin-bearer-auth-v0` then layered Bearer auth on every `/api/admin/*` route. The next blocker for Phase 4 is the absence of read endpoints — the `web-admin/` Vite app (not yet scaffolded) needs to render journal rows, open positions, and a today-summary KPI strip on its dashboard. There is also reusable prior art in `src/ohmystock/journal/repository.py` (`open_positions`, `closed_trades_desc`, `monthly_realized_pnl_pct`) that already encodes the entry-without-matching-exit join logic.

The shared infra is mature:

- `src/ohmystock/api/routes/_envelope.py` provides `to_success`, `to_error`, `map_exception_to_envelope`.
- `src/ohmystock/api/routes/_deps.py` provides `get_db` (per-request `sqlite3.Connection`) and `get_settings_dep`.
- `src/ohmystock/api/auth.py` provides `require_admin` (Bearer gate).
- `app.py` already maps `AuthError` → 401 envelope at the FastAPI exception-handler layer.

So this change is mostly route plumbing + SQL — no new helpers, no schema migrations, no new env vars.

The journal `kind` enum is `entry / exit / reject / expire / auto_execute_audit` — there is no `fill` kind. Fill data is folded into the entry row's `payload_json` (`actual_entry_price`, `actual_qty`) at confirm time. This shapes Decisions 4–6 below.

## Goals / Non-Goals

**Goals:**
- Ship 4 GET endpoints that the frontend can hit immediately to populate a dashboard, journal page, and positions list.
- Reuse `journal/repository.open_positions` instead of duplicating the entry∖exit join.
- Stay strictly within the existing envelope / auth / per-request-conn invariants — no new patterns introduced.
- Keep query latency low at expected solo-localhost scale (≤ a few thousand journal rows for ~6 months of paper trading) without indexes beyond what the schema already provides.
- Pagination on journal rows is mandatory so the frontend never accidentally fetches 10k+ rows.
- Test coverage parity with the write endpoints (one happy path + at least one error path per endpoint).

**Non-Goals:**
- Emitting `journal_queried` events (deferred — documented in proposal Out-of-scope).
- FTS5 search endpoint (deferred until reviewer/proposer pages need it).
- Caching, ETag, conditional requests.
- WebSocket / GraphQL alternatives.
- Read endpoints under `/api/public/*` (Phase 4.5).
- Schema migrations or new indexes (existing `idx_journal_entries_decision_id` and `idx_journal_entries_kind_created_at` cover query plans).

## Decisions

### Decision 1 — Separate router file per resource (not one mega-router)
Three new modules: `routes/journal.py`, `routes/positions.py`, `routes/stats.py`. Mirrors the existing one-resource-per-file convention (`screener.py`, `confirm_gate.py`, `exit_engine.py`).

**Why**: Discoverability + smaller diffs in future changes. Adding a new endpoint to the same resource becomes localised.

**Alternatives considered**: a single `routes/reads.py` mega-router. Rejected — would diverge from the existing layout and force a `prefix=""` router that mixes 4 unrelated resources.

### Decision 2 — Use Pydantic response models for stable JSON shape
Each endpoint defines a Pydantic v2 `BaseModel` for its `data` payload (e.g., `JournalRowsData`, `PositionsOpenData`, `StatsTodayData`). The model is **not** declared in `response_model=` on the route (because we wrap in the `to_success(...)` envelope), but is used for `.model_dump(mode="json")` inside the handler so the JSON shape is unit-testable.

**Why**: Forces an explicit contract; renaming a SQL column won't silently leak to JSON. Mirrors how `confirm_gate.py` already returns hand-built dicts but with stricter typing.

**Alternatives considered**:
- `TypedDict` only — rejected (no runtime validation, and Pydantic is already a dep).
- Use `response_model=` with a custom envelope wrapper — rejected (would require subclassing FastAPI's response handling, doesn't pay off for 4 endpoints).

### Decision 3 — Pagination contract for `journal/rows`
Query string: `limit` (default 100, max 500) + `offset` (default 0, min 0). Response body includes:
- `items: list[JournalRowItem]`
- `total: int` — total matching rows (separate `COUNT(*)` query on the same connection)
- `limit: int`, `offset: int` (echoed; **effective** values after clamp)
- `has_more: bool` — `offset + len(items) < total`

`limit > 500` SHALL clamp to 500 silently (not raise 400). `limit ≤ 0` or `offset < 0` SHALL raise 400 `invalid_input`. The 500-row cap is a defensive ceiling — frontend's TanStack Query infinite-list will paginate 100 at a time.

**Why clamp instead of reject for `limit > 500`**: matches safety-first defaults and avoids breaking a frontend that fat-fingers the URL. Negative / zero limits *are* rejected because they signal a real bug (no useful behaviour to clamp to).

**Alternatives considered**: cursor pagination (overkill for SQLite at this scale); page-number style (`?page=2&size=100`) — rejected because offset/limit is the universal SQL primitive and easy to test deterministically.

### Decision 4 — `journal/rows` filter semantics
- `kind`: optional, exact match against the `kind` column. Invalid kind (not in the 5-value enum) → 400 `invalid_input`.
- `symbol`: optional, exact match (case-sensitive — TWSE codes are numeric/uppercase by convention). No wildcard, no LIKE.
- `date_from`, `date_to`: optional, ISO date `YYYY-MM-DD`. Compared against `substr(created_at, 1, 10)`. `date_from > date_to` → 400 `invalid_input`. Both inclusive on the day boundary.

**Why exact symbol match in v0**: solo-dev frontend always knows the symbol (clicked from a list). LIKE `%2330%` invites accidental scans of all symbols; deferred to a future search endpoint if needed.

### Decision 5 — `positions/open` reuses `journal.repository.open_positions(conn, asof=now_iso)`
Instead of re-implementing the entry∖exit anti-join, import `ohmystock.journal.repository.open_positions` and pass `asof = datetime.now(TPE).isoformat()`. The handler then enriches each `OpenPosition` with `hold_days` (`(asof_date - entry_date).days` from the date prefix of `entry_ts`), and lifts `stop_loss` / `t1_target` / `time_stop_date` from `payload_json` via a single bulk fetch.

To avoid N+1 queries: one extra `SELECT decision_id, payload_json FROM journal_entries WHERE kind='entry' AND decision_id IN (?, ?, ...)` after `open_positions` returns the candidate list. Result is keyed into a `dict[str, dict]` and looked up per row.

**Why not extend `OpenPosition` dataclass**: would change a shared module's API. Keeping the enrichment local to the route handler keeps blast radius contained. If a future change wants enrichment shared, it can promote it to `repository.py`.

**Alternatives considered**: inline a fresh SQL query in the handler. Rejected — duplicates the entry∖exit anti-join; risk of drift with `closed_trades_desc` semantics.

### Decision 6 — `stats/today` is a single SQL aggregate, no Python loop
One query of the form:

```sql
SELECT
    SUM(CASE WHEN kind='entry' THEN 1 ELSE 0 END) AS decisions_made,
    SUM(CASE WHEN kind='entry' AND json_extract(payload_json,'$.actual_entry_price') IS NULL THEN 1 ELSE 0 END) AS entries_pending,
    SUM(CASE WHEN kind='entry' AND json_extract(payload_json,'$.actual_entry_price') IS NOT NULL THEN 1 ELSE 0 END) AS entries_filled,
    SUM(CASE WHEN kind='reject' THEN 1 ELSE 0 END) AS rejects,
    SUM(CASE WHEN kind='expire' THEN 1 ELSE 0 END) AS expires,
    SUM(CASE WHEN kind='auto_execute_audit' THEN 1 ELSE 0 END) AS auto_execute_audits
FROM journal_entries
WHERE substr(created_at, 1, 10) = ?
```

Today's date is computed as `datetime.now(TPE).date().isoformat()` (TPE = `zoneinfo.ZoneInfo("Asia/Taipei")`). Empty table → all six counters are `0`, not `NULL` (`COALESCE(SUM(...), 0)` wraps each).

**Why a single query**: 6 small `SUM(CASE)` aggregates over an indexed table for one day's rows — milliseconds. Trivially testable.

**Why TPE not UTC**: journal `created_at` already stores ISO-8601 with `+08:00` offset; substr-prefix match must use the same calendar.

### Decision 7 — Error mapping uses existing `map_exception_to_envelope`
Every route wraps its body in the canonical try/except pattern from `confirm_gate.py` and `exit_engine.py`:
```python
try:
    ...
    return JSONResponse(status_code=200, content=to_success(data))
except Exception as exc:
    status, body = map_exception_to_envelope(exc)
    return JSONResponse(status_code=status, content=body)
```
`ValueError` from query-string validation maps to 400 `invalid_input`; everything else falls back to 500 `internal_error` with a generic message (no SQL/path leakage). `AuthError` is caught at the app-level handler in `app.py` (already wired); no per-route change needed for 401.

### Decision 8 — Test fixtures: reuse `tests/conftest.py`
The existing conftest already provides a fresh in-memory SQLite + `init_schema` fixture and a `TestClient` factory with valid Bearer token. New tests bolt onto that — no new conftest fixtures.

## Risks / Trade-offs

- **[Risk] N+1 risk on `positions/open` payload fetch** → Mitigation: single bulk `IN (...)` query for payloads after `open_positions` returns. Capped by the natural concurrency limit of "currently-open positions" (typically <20 for a single retail account) so even N+1 would be acceptable; bulk fetch is belt-and-suspenders.
- **[Risk] `stats/today` substr-prefix scan** → Mitigation: `idx_journal_entries_kind_created_at` indexes `(kind, created_at)` so SQLite can range-scan today's rows efficiently for each `CASE`. At a few thousand rows total this is sub-millisecond.
- **[Risk] `journal/rows` 500-row clamp surprises a frontend that asked for 1000** → Mitigation: response echoes the *effective* `limit` so the frontend can detect the clamp and adjust. Alternative (raising 400) was rejected per Decision 3 rationale.
- **[Risk] `OpenPosition` dataclass currently lacks `stop_loss / t1_target / time_stop_date`** → Mitigation: enrich at the route layer (Decision 5) without touching the dataclass; documented as a future consolidation candidate.
- **[Risk] Two separate `COUNT(*)` + `SELECT ... LIMIT` queries inside one transaction could disagree if a writer commits between them** → In v0 SQLite is single-writer + per-request connection, so the connection's snapshot is stable for the duration of one HTTP request. Acceptable; revisit if WAL + concurrent writers become a thing.
- **[Trade-off] No `/journal/search` FTS endpoint yet** → Future change can add `GET /api/admin/journal/search?q=...` once the reviewer/proposer pages need full-text. Today's frontend pages don't.
- **[Trade-off] No `journal_queried` event emission** → Saves ~1 line per handler + an emitter requirement; can be added in a follow-up change without touching the read endpoints' externally observable contract.
