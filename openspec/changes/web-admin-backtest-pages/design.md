## Context

Phase 4 web-admin currently has 8 of 18 pages real (Dashboard, Login, PaperOverview, PaperOrders, PaperPositions, Audit, Market, MarketSymbol). `/backtest` and `/backtest/:jobId` (page-designs §5–§6) are the next stub pair to land. Every backend dependency is already archived — `backtest-engine`, `backtest-fills`, `backtest-portfolio`, `backtest-metrics`, `backtest-costs` — and `backtest-engine` exposes a single pure entry point `run_backtest(strategy, bars_by_symbol, *, period, initial_capital, fee_discount, slippage_bps, day_trade)` that returns a fat envelope `{ok, elapsed_ms, data: {trades, equity_curve, metrics, ...}, error}`. Today this engine is callable only from Python; there is no admin HTTP, no SQLite persistence, no UI.

The web-admin shell, design system (DataTable, KpiCard, StatusBadge), Bearer auth, `apiFetch` helper, and SSE subscriber are all in place. The 紅漲綠跌 invariant (`text-up`/`text-down` paired with Lucide arrow) is locked. The `web-admin-market-pages` change just shipped the precedent of "labelled placeholder Card for charts" (`K 線圖（圖庫待定）`) — we follow that here for equity curve + drawdown.

The page-designs SSOT (`docs/web-admin-page-designs.md` §5–§6) is the layout / interaction / state-machine / a11y authority for both pages.

## Goals / Non-Goals

**Goals:**
- Replace the two `<ComingSoon>` stubs with real implementations driven by one new SQLite table + three thin HTTP endpoints.
- Run backtests synchronously over a small custom-symbols universe (typical: 1–10 symbols, one calendar year). The engine takes a few hundred ms; no async/queue layer needed.
- Persist enough per-run data to make the history list and the detail page round-trip correctly across sessions.
- Match page-designs §5–§6 layout, state-machine, and 紅漲綠跌 rules exactly.
- Keep the change reversible: a single revert restores stubs, removes one router file, and drops one DB table.

**Non-Goals:**
- No chart library. Equity curve & drawdown render as labelled placeholder Cards. Real charts are a separate change once a library is chosen.
- No async / job queue / Celery. Synchronous run. If a future SEPA strategy is too slow, we add async then, not now.
- No `tw50`/`tw100` universe lookup. v0 takes a custom symbols list; universe enumeration is a future change.
- No edits to the archived `backtest-*` specs. The engine's behavior is fixed.
- No new SSE event types. Spec §5/§6 mentions `wfa_started/passed/failed` for live updates — those are a separate Phase 5 capability and not in scope here.
- No CSV export. Spec §6 hints at a "下載 trades CSV" button — out of scope; users can still inspect trades in the table.
- No strategy parameter UI. Strategies use their built-in defaults in v0; advanced parameter forms are a future change.

## Decisions

### D1 — One new SQLite table `backtest_jobs`, no foreign keys

**Decision:** Persist runs in a single new table:

```sql
CREATE TABLE IF NOT EXISTS backtest_jobs (
    id                    TEXT    PRIMARY KEY,           -- uuid4 hex
    strategy              TEXT    NOT NULL,
    period_from           TEXT    NOT NULL,              -- 'YYYY-MM-DD'
    period_to             TEXT    NOT NULL,              -- 'YYYY-MM-DD'
    custom_symbols_json   TEXT    NOT NULL,              -- '["2330","2454"]'
    initial_capital       REAL    NOT NULL,
    status                TEXT    NOT NULL CHECK(status IN ('completed','failed')),
    elapsed_ms            INTEGER NOT NULL,
    result_json           TEXT    NOT NULL,              -- engine envelope.data on success, or error blob on failure
    created_at            TEXT    NOT NULL               -- ISO-8601 +08:00
);
CREATE INDEX IF NOT EXISTS idx_backtest_jobs_created_at
    ON backtest_jobs(created_at);
```

**Why:** One row per run is the simplest persistent shape that round-trips both the list page and the detail page. `result_json` holds the engine's already-serializable envelope verbatim, so the detail handler is a pure SELECT + json-decode with no schema drift between engine output and storage. No FKs because rows are immutable once written.

**Alternatives considered:**
- *Separate `backtest_jobs` + `backtest_trades` + `backtest_equity_points` tables* — rejected: schema churn for zero reuse benefit. The engine writes everything atomically; we never query trades or equity points outside the context of one job.
- *Files on disk under `~/.ohmystock/backtest/<id>.json`* — rejected: SQLite is already the system-of-record for the journal, the chip cache, and rs ratings. Adding a second persistence mechanism trades simplicity for no benefit.

### D2 — Synchronous run; no queue, no SSE

**Decision:** `POST /api/admin/backtest/run` does the full work in-request: validate input → load `bars_daily` for each symbol over the period → call `run_backtest` → write the row → return `{job_id, status, elapsed_ms}`. The frontend reflects this with a "啟動中…" pending button while the request is open.

**Why:** Daily-bar engine over one symbol × one year is sub-second; even 10 symbols × 4 years is well under 5 seconds. A user is happy to wait synchronously for a backtest they explicitly clicked. Adding a queue + SSE flow would 3× the moving parts for zero UX improvement on a personal-use tool. The page-designs SSOT mentions `wfa_started/passed/failed` SSE for live row updates — those events belong to Phase 5 walk-forward analysis, not this single-run endpoint.

**Alternatives considered:**
- *Async with job_id polling* — rejected: premature for sub-5s runs.
- *SSE progress* — rejected: same reason.

### D3 — Custom-symbols-only universe in v0

**Decision:** The `BacktestRunInput` body has `symbols: string[]` (1..50, validated). The form's "universe" dropdown is hardcoded to `["custom"]` for now (no `tw50`/`tw100` enumeration yet — that requires the universe-snapshot capability that's not in scope here).

**Why:** SSOT §5 mentions `tw50`/`tw100` but those resolve to dynamic symbol lists that need their own capability and freshness invariants. We don't need a universe loader to dogfood the backtest engine — a typed list of symbols is enough. Universe enumeration is a separate future change.

### D4 — Strategy enumeration via a small registry helper

**Decision:** Add `ohmystock.backtest.strategy.registry` exporting `available_strategies() -> list[{name, description}]` that introspects `ohmystock.backtest.strategy` for registered classes. Today this returns just `[{name: "sma_cross", description: "SMA crossover (warmup 200d)"}]`. The frontend calls a new `GET /api/admin/backtest/strategies` to populate the dropdown — this stays in sync as future strategies are added without code changes to the page.

**Why:** Hardcoding the strategy list in the React component would diverge as strategies land. The registry stays in the backend module that already owns the strategy abstraction.

**Alternatives considered:**
- *Hardcode `<option value="sma_cross">` in the page* — rejected: would silently break when SEPA / ATR strategies land.

### D5 — `bars_daily` hydration at request time, not as part of input

**Decision:** The handler receives only symbols + period; it loads `bars_daily` rows from the existing schema (`select_bars(conn, symbol, start, end)`) for each symbol. Bars are not passed by the client.

**Why:** Bars are large (60–1000 rows × 7 cols × N symbols). Round-tripping them through the wire would (a) bloat request size, (b) bypass the system-of-record `bars_daily`, and (c) couple the frontend to the BarRow shape. The handler is the single producer that converts (symbols, period) → `bars_by_symbol`.

**Failure mode:** If `bars_daily` has no rows for some symbol over the period, return 400 with `error.code = "missing_bars"` and the offending symbol — the engine itself returns an INVALID_INPUT envelope in that case anyway.

### D6 — Equity curve + drawdown as labelled placeholder Cards

**Decision:** The detail page renders both as `<Card>` with caption text "資金曲線（圖庫待定）" / "回撤曲線（圖庫待定）". The actual `equity_curve` / drawdown series are returned by `GET /api/admin/backtest/jobs/{id}` in `data.equity_curve` so a future chart-lib change can light them up without endpoint churn.

**Why:** We just locked the same precedent for K-line in `web-admin-market-pages` (chart lib TBD). Repeating that decision here keeps the project consistent and avoids a premature lock-in to one of recharts / visx / chart.js / observable-plot.

### D7 — `/backtest` filter form mirrors `/market`'s shape

**Decision:**
- Strategy `<select>` (registry-populated)
- Period: two `<input type="date">` (from / to), default last 365 days
- Symbols chip-input identical to `/market` MarketPage.tsx's chip behavior (Enter / Backspace) — copy-paste a shared `<ChipInput>` is out of scope; this change inlines the pattern.
- Initial capital `<input type="number">`, default 1,000,000
- Submit button "跑回測" + Cmd/Ctrl+Enter shortcut
- Reset button "清空"

**Why:** Stays consistent with the just-shipped MarketPage so users get one mental model. Inline chip code now; if a third page also needs chips later, we extract the component then.

### D8 — Job list refresh: invalidate on run success, no polling

**Decision:** After `POST /api/admin/backtest/run` resolves, the page invalidates the `['backtest', 'jobs']` query so the history table refetches. No background polling; no SSE. List is otherwise static.

**Why:** Solo-dev tool; user always knows when they triggered a run. Polling is wasted bandwidth when the only writer is the same browser.

## Risks / Trade-offs

[**Sync request can hit gateway timeouts on heavy strategies**] As future SEPA / ATR strategies arrive, the run might exceed 30 s. → **Mitigation:** v0 ships only `sma_cross` which is fast; we revisit async when a strategy actually trips this threshold. Gateway in dev is uvicorn directly with no proxy timeout.

[**`result_json` blob can grow large**] One year × 10 symbols ≈ 2500 equity points × 80 bytes ≈ 200 KB; trades cap is in the low hundreds. SQLite handles this fine, but the row size grows monotonically with universe × period. → **Mitigation:** Cap the run input: `len(symbols) ≤ 50`, period ≤ 5 years. The endpoint validates and rejects oversize inputs with `error.code = "input_too_large"`.

[**Strategy registry coupling**] `available_strategies()` introspects an internal module. If a future strategy adds args that break the no-arg constructor, the registry call could throw. → **Mitigation:** Wrap each registry entry in a try/except that omits broken strategies and logs a warning; missing strategies degrade the dropdown rather than 500 the endpoint.

[**Cross-page back-nav from detail to list re-fires the list query**] Acceptable; the query is fast. → No mitigation needed.

[**`backtest_jobs.id` collision**] uuid4 collision is astronomically improbable; treat any `INSERT OR ABORT` failure as a 500 internal error. → No mitigation needed.

## Migration Plan

This is additive, no data migrations.

**Deploy order (single commit chain on `main`):**
1. Backend: add `backtest/storage.py` (`init_schema` + insert/select), add registry helper, add `routes/backtest.py`, register in `app.py`, add unit tests.
2. Frontend: add types + `runBacktest` / `listBacktestJobs` / `getBacktestJob` / `listStrategies` clients.
3. Frontend: implement `BacktestPage.tsx`, then `BacktestJobPage.tsx`, with vitest tests.
4. Frontend: swap stub imports in `router.tsx`; remove from `pages/stubs.tsx`.
5. Run typecheck + tests + build for both backend and `web-admin`.
6. Manual smoke: open `/backtest`, fill form for `sma_cross` over 2024 H1 with `2330`, click run, confirm row appears in history with metrics, click row, confirm detail page renders KPIs + trades.

**Rollback:** revert the single feature commit; both pages return to `<ComingSoon>`, the new routes disappear, the new table is left in place (orphan; no harm — fresh DBs won't create it after revert because `init_schema` is gone). Optional follow-up: drop the table.

## Open Questions

- None blocking. The chart-library decision is intentionally deferred per §11 / §6 ("圖庫待定").
