## Why

Phase 1 (target 2026-05-26) requires a working backtest loop so subsequent strategy work has measurable feedback. Today the repo has indicator primitives and a daily-bar cache but no way to feed bars + indicators through a strategy and get out trades, an equity curve, or metrics. Without that, no strategy proposal can be validated and Phase 5's WFA gate has nothing to call.

This MVP delivers the smallest engine that is honest about Taiwan-market mechanics (T+2 cash, ±10% price limits, 0.1425%×0.28 fee, 0.3%/0.15% transaction tax, slippage) and is deterministic enough to be reproducible across runs.

## What Changes

- **New** `ohmystock.backtest.engine.run_backtest(...)` — pure-Python event-loop backtester over daily bars from `market-data-cache`, long-only, whole-share, deterministic.
- **New** `ohmystock.backtest.costs` — Taiwan cost model (fee/tax/slippage) per `workflow-cheatsheet.md` §6.6 / `design-zh-TW.md` §4.4.2.
- **New** `ohmystock.backtest.fills` — limit/market fill model honouring ±10% daily price limit (no cross-limit fills).
- **New** `ohmystock.backtest.metrics` — Sharpe, Sortino, max drawdown, MDD duration, win rate, profit factor, expectancy, total return, equity curve.
- **New** `ohmystock.backtest.strategy.Strategy` Protocol — single seam between bars+indicators and order intents (`BUY/SELL/HOLD`); ships with one reference strategy (`sma_cross`) used only for tests/example.
- **New** envelope-shaped public entrypoint `run_backtest(...) -> {ok, elapsed_ms, data, error}` matching the `market-data-cache` convention (no exceptions escape; errors carried in envelope).
- Out of scope (deferred): intraday bars, shorts, odd lots, IPO honeymoon, halts/MOPS, processing-stock liquidity throttle, walk-forward analysis, FastAPI/`arq` job queue, the `backtest_tool` registration in `tools-contracts.md` §17 (this MVP is the library; tool wiring is a later change).

## Capabilities

### New Capabilities
- `backtest-engine`: deterministic daily-bar backtester with Taiwan cost/fill model, strategy Protocol, and standard performance metrics returned in an envelope payload.

### Modified Capabilities
<!-- None. This change adds a new capability and does not alter requirements of existing specs. -->

## Impact

- **Code**: new package `src/ohmystock/backtest/{engine,costs,fills,metrics,strategy}.py` (the directory exists but is empty); new tests under `tests/test_backtest_*.py`.
- **Dependencies on existing capabilities**: reads bars via `market-data-cache.get_kline` (already shipped); consumes `technical-indicators` pure functions for any strategy that needs them. No reverse import into `ohmystock.api` or FastAPI.
- **Dependencies added**: none beyond the existing stdlib + numpy stance; no pandas, no LangChain, no broker SDK calls.
- **Deferred wiring**: `backtest_tool` (`tools-contracts.md` §17), `arq` job queue, `/api/backtest` FastAPI route, web-admin Backtest page — each is its own follow-up change.
- **Risk**: this is a foundation; Phase 5's WFA proposal gate depends on this engine being reproducible. Determinism is a hard requirement (covered in design.md / spec).
