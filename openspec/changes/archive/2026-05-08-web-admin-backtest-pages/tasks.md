## 1. Backend — `backtest_jobs` storage + strategy registry

- [x] 1.1 Create `src/ohmystock/backtest/storage.py` with `init_schema(conn)` (DDL for `backtest_jobs` + `idx_backtest_jobs_created_at`), `insert_job(conn, row)`, `select_recent(conn, limit)`, `select_by_id(conn, job_id)`
- [x] 1.2 Create `src/ohmystock/backtest/strategy/registry.py` with `available_strategies()` introspecting subclasses of `Strategy` reachable from `ohmystock.backtest.strategy`; each entry `{name: <class.NAME>, description: <class.__doc__ first line>}`; broken classes silently skipped
- [x] 1.3 Add unit tests at `tests/test_backtest_storage.py` covering: idempotent init, insert + select round-trip, ordering by `created_at DESC`, missing-id returns None, JSON round-trip preserves equity_curve/trades shape
- [x] 1.4 Add unit tests at `tests/test_backtest_strategy_registry.py` covering: `sma_cross` is present, malformed class is skipped, return shape `{name, description}`

## 2. Backend — `routes/backtest.py` HTTP layer

- [x] 2.1 Create `src/ohmystock/api/routes/backtest.py` with `APIRouter(dependencies=[Depends(require_admin)])`, modelled on `routes/market.py` (per-request `Depends(get_db)`, `_envelope.to_success` / `map_exception_to_envelope`)
- [x] 2.2 Define Pydantic models: `BacktestRunInput`, `BacktestRunResponse`, `JobSummary`, `JobDetail`, `BacktestTrade`, `EquityPoint`, `DrawdownPoint` (frozen `model_config`)
- [x] 2.3 Implement `GET /api/admin/backtest/strategies` → calls registry, returns `{strategies: [...]}`
- [x] 2.4 Implement `POST /api/admin/backtest/run`: validate input (1–50 symbols, period ≤ 5 years, fee/slippage bounds), hydrate `bars_daily` via `select_bars`, call `run_backtest`, persist row, return `{job_id, status, elapsed_ms}`. 400 `invalid_input` / `input_too_large` / `missing_bars` mapped explicitly
- [x] 2.5 Implement `GET /api/admin/backtest/jobs?limit=N`: clamp [1,100], default 20, ORDER BY created_at DESC; build JobSummary by extracting metrics from result_json (null when status="failed"); never include result_json in payload
- [x] 2.6 Implement `GET /api/admin/backtest/jobs/{job_id}`: SELECT row, decode result_json, derive drawdown series from equity_curve (each point = `equity / running_max - 1`), build full JobDetail; 404 `not_found` when missing
- [x] 2.7 Register the router in `src/ohmystock/api/app.py` (import + `app.include_router(backtest_router)`)
- [x] 2.8 Wire `_lifespan` in `api/app.py` to call `backtest.storage.init_schema(conn)` once at startup so first request after a fresh DB succeeds

## 3. Backend tests

- [x] 3.1 Add `tests/api/test_backtest_endpoint.py` covering: 401 no-token, 401 wrong-token, GET strategies happy, POST run happy with seeded bars, POST run missing_bars 400, POST run invalid_input (period reversed / unknown strategy / oversized symbols / oversized period), engine-fail still 200 with status="failed", GET jobs empty/sorted/limit-clamp/no-result-json-leak/failed-derived-nulls, GET jobs/{id} happy/404/drawdown-correctness/failed-degraded
- [x] 3.2 Add internal-error redaction test: response body strips `/Users/`, `SELECT`, `Traceback`
- [x] 3.3 `python -m pytest tests/api/test_backtest_endpoint.py tests/test_backtest_storage.py tests/test_backtest_strategy_registry.py -v` and confirm all pass
- [x] 3.4 `python -m pytest tests/ -x` (full suite) — confirm no regressions

## 4. Frontend — types + API client

- [x] 4.1 In `web-admin/src/lib/api.ts` add exported types: `BacktestRunInput`, `BacktestJobSummary`, `BacktestJobDetail`, `BacktestTrade`, `BacktestEquityPoint`, `BacktestDrawdownPoint`, `BacktestStrategy` (fields aligned to backend Pydantic models)
- [x] 4.2 Add `runBacktest(input)`, `listBacktestJobs(limit?)`, `getBacktestJob(jobId)`, `listStrategies()` wrappers around `apiFetch`
- [x] 4.3 Extend `web-admin/src/lib/__tests__/api.test.ts` (or add cases) for: `runBacktest` POSTs JSON body to `/api/admin/backtest/run`; `listBacktestJobs(50)` includes `?limit=50`; `listBacktestJobs()` omits `?limit=`; `getBacktestJob("a1b2…")` hits `/jobs/a1b2…`; `listStrategies()` hits `/strategies`

## 5. Frontend — `/backtest` page

- [x] 5.1 Create `web-admin/src/pages/BacktestPage.tsx` with filter form (strategy `<select>` populated from `listStrategies`, custom-symbols chip-input, two `<input type="date">`, initial-capital `<input type="number">`), action row「清空」+「跑回測」
- [x] 5.2 Wire form-submit and `Cmd/Ctrl+Enter` to `runBacktest(input)`; manage `submitting | error` state; on success invalidate `['backtest','jobs']` query
- [x] 5.3 Render history `<DataTable>` with 8 columns (JobId / 策略 / 期間 / 年化 / Sharpe / MaxDD / 狀態 / 建立時間); row-click → `useNavigate()(/backtest/{id})`
- [x] 5.4 Apply 紅漲綠跌 to「年化」(>0 up, <0 down)、「Sharpe」(>1 up, <0 down)、「MaxDD」(always down) with Lucide arrow icons; Score-style bold for high-confidence cells where applicable
- [x] 5.5 Failed-job row: 衍生欄位顯示 `—`、no colour, status badge 「失敗」
- [x] 5.6 Implement loading state (≥3 Skeleton rows + button「啟動中…」), empty state (「尚未跑過回測」+ hint), error state (`text-destructive` block + retry button, do not clear form)
- [x] 5.7 Add a11y: tab order matches scenario; `Cmd/Ctrl+Enter` global hotkey (form scope only); chip-input Enter/Backspace behaviour; reset button clears chips + dates only
- [x] 5.8 Add `web-admin/src/pages/__tests__/BacktestPage.test.tsx` covering each scenario from `specs/web-admin-backtest-pages/spec.md` § "/backtest 頁面實作" + § "三態與 run-success 行為"

## 6. Frontend — `/backtest/{jobId}` page

- [x] 6.1 Create `web-admin/src/pages/BacktestJobPage.tsx`; read `:jobId` from `useParams()`; call `getBacktestJob(jobId)` on mount
- [x] 6.2 Render header (返回連結 `← /backtest` + jobId truncated + strategy + period)
- [x] 6.3 Render 4 `<KpiCard>`: 年化 / Sharpe / MaxDD / 勝率 with proper `direction` mapping (annual sign / Sharpe>1 / MaxDD always down / 勝率 neutral); failed-job → all show `—`
- [x] 6.4 Render equity curve placeholder `<Card>` with caption「資金曲線（圖庫待定）」 + drawdown placeholder `<Card>` with caption「回撤曲線（圖庫待定）」 — do NOT install any chart library
- [x] 6.5 Render trades `<DataTable>` (7 cols: 進場日 / 出場日 / Symbol / 方向 / P&L / 持倉 / Pattern) with 紅漲綠跌 on P&L column; empty → 「本 job 區間無交易訊號」
- [x] 6.6 Implement loading (Skeletons across header / KPIs / chart blocks / trades table), 404 (「該 job 不存在」+ back link), generic error (`text-destructive` + retry), failed-job degraded view (KPIs `—` + image-area "無資料 — job 失敗" + banner with `error.message`) states
- [x] 6.7 Add `web-admin/src/pages/__tests__/BacktestJobPage.test.tsx` covering each scenario from `specs/web-admin-backtest-pages/spec.md` § "/backtest/{jobId} 頁面實作" + § "三態"

## 7. Wire into router; remove stubs

- [x] 7.1 In `web-admin/src/router.tsx` replace stub imports `BacktestPage`/`BacktestJobPage` with real imports from `./pages/BacktestPage` and `./pages/BacktestJobPage`
- [x] 7.2 Remove `BacktestPage` and `BacktestJobPage` exports from `web-admin/src/pages/stubs.tsx`
- [x] 7.3 Add a smoke test that mounts the router and asserts `/backtest` and `/backtest/<id>` do not render `<ComingSoon>`

## 8. Verification

- [x] 8.1 `cd web-admin; pnpm typecheck` → 0 errors
- [x] 8.2 `cd web-admin; pnpm test --run` → all green (142 / 142)
- [x] 8.3 `cd web-admin; pnpm build` → exits 0
- [x] 8.4 `python -m pytest tests/ -x` → all green (962 / 962)
- [x] 8.5 Manual smoke on `localhost:5173`: log in, navigate `/backtest`, run sma_cross over 2024 H1 with `2330` (assumes `bars_daily` has 2330 backfilled), verify history row appears, click into detail, verify KPIs + trades render, equity-curve placeholder visible
- [x] 8.6 `openspec validate web-admin-backtest-pages --strict` → passes
- [x] 8.7 Update `CLAUDE.md` §5 SSOT table (post-archive entry pointing to `openspec/specs/web-admin-backtest-pages/spec.md`, `openspec/specs/admin-backtest-endpoints/spec.md`, `src/ohmystock/api/routes/backtest.py`, `src/ohmystock/backtest/storage.py`, `src/ohmystock/backtest/strategy/registry.py`, `web-admin/src/pages/BacktestPage.tsx`, `web-admin/src/pages/BacktestJobPage.tsx`)

## 9. Archive

- [x] 9.1 `git add` + commit per CLAUDE.md style; push to `main` directly
- [x] 9.2 Run `/opsx:archive web-admin-backtest-pages` to move change → `openspec/changes/archive/<date>-web-admin-backtest-pages/` and sync delta into `openspec/specs/`
