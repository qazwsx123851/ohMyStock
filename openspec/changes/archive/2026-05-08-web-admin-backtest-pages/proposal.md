## Why

Phase 4 web-admin still has 9 stubs after the Market pages shipped. `/backtest` and `/backtest/:jobId` (page-designs §5–§6) are the next-best target because every backend dependency is already archived: `backtest-engine`, `backtest-fills`, `backtest-portfolio`, `backtest-metrics`, `backtest-costs`. Today the engine is callable from Python only — there is no admin UI to trigger a run, no way to compare runs visually, no place to drill into a single run's trades. Replacing these two stubs unblocks visual dogfooding of every archived backtest capability.

## What Changes

- Add a tiny **`backtest_jobs`** SQLite table (one row per run) so jobs survive across sessions. No queue, no async — the engine is fast on daily bars.
- Add **`POST /api/admin/backtest/run`** that hydrates `bars_daily` for the requested universe + period, calls `backtest.engine.run_backtest`, persists the result envelope, and returns `{job_id}`. Synchronous; the engine is a few hundred ms for one symbol over one year.
- Add **`GET /api/admin/backtest/jobs?limit=N`** (recent runs, default 20, cap 100) and **`GET /api/admin/backtest/jobs/{job_id}`** (full result + trades + equity curve series).
- Add a registered-strategy enumeration helper so the form's strategy dropdown lists what `ohmystock.backtest.strategy` actually exposes (initially `sma_cross`; SSOT §5 mentions SEPA/ATR but those are future strategies).
- Implement real **`/backtest` page**: filter form (strategy / period / custom symbols chip-input / initial capital) + history `<DataTable>` (8 cols: JobId / 策略 / 期間 / 年化 / Sharpe / MaxDD / 狀態 / 建立時間) + Cmd/Ctrl+Enter shortcut.
- Implement real **`/backtest/:jobId` page**: header (返回 + jobId + strategy + period) + 4 `<KpiCard>` (年化 / Sharpe / MaxDD / 勝率) + 2 labelled placeholder `<Card>` blocks for equity-curve & drawdown (chart lib still TBD per §11 K-line precedent — **NO chart library installed in this change**) + trades `<DataTable>` (7 cols).
- Wire both pages into `App.tsx`/`router.tsx`, remove from `pages/stubs.tsx`.

## Capabilities

### New Capabilities
- `web-admin-backtest-pages`: `/backtest` form + history list + `/backtest/{jobId}` detail real implementations, route-tree wiring, `<ComingSoon>` removal for both routes.
- `admin-backtest-endpoints`: `POST /api/admin/backtest/run` + `GET /api/admin/backtest/jobs` + `GET /api/admin/backtest/jobs/{id}` + `backtest_jobs` schema; same `{ok,data,error}` envelope, same per-request DB conn, same Bearer auth invariants as other admin endpoints.

### Modified Capabilities

(none — all behavior added is new; no archived spec's requirements change)

## Impact

- **Code**:
  - `web-admin/src/pages/BacktestPage.tsx` (new, replaces stub)
  - `web-admin/src/pages/BacktestJobPage.tsx` (new, replaces stub)
  - `web-admin/src/pages/stubs.tsx` (remove `BacktestPage` + `BacktestJobPage` exports)
  - `web-admin/src/router.tsx` (swap stub imports → real components)
  - `web-admin/src/lib/api.ts` (add `BacktestJobSummary`, `BacktestJobDetail`, `BacktestTrade`, `BacktestRunInput` types + `runBacktest` / `listBacktestJobs` / `getBacktestJob` clients)
  - `src/ohmystock/api/routes/backtest.py` (new router, registered in `api/app.py`)
  - `src/ohmystock/backtest/storage.py` (new — `init_schema`, `insert_job`, `select_recent`, `select_by_id`)
  - `src/ohmystock/api/app.py` (mount the new router)
- **Specs**: 2 new spec files; no archived spec mutated.
- **Tests**:
  - Backend: `tests/api/test_backtest_endpoint.py` + `tests/test_backtest_storage.py`
  - Frontend: `web-admin/src/pages/__tests__/BacktestPage.test.tsx`, `BacktestJobPage.test.tsx`, plus `lib/__tests__/api.test.ts` extension
- **Dependencies**: no new packages. Reuses FastAPI router stack, vitest + RTL, msw (already in use).
- **No live trading impact**: read-mostly over already-archived storage; only new write is `backtest_jobs` rows; touches no broker, no journal-write, no auto-execute path.
- **DB schema**: one new table `backtest_jobs (id PK, strategy, period_from, period_to, custom_symbols_json, initial_capital, status, elapsed_ms, result_json, created_at)`. Reads `bars_daily` for hydration.
- **Chart library**: explicitly NOT chosen in this change — equity curve and drawdown render as labelled placeholder Cards (mirrors the K-line decision from `web-admin-market-pages`).
