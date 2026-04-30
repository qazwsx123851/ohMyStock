## Why

Phase 0 only ships a raw `FinMindClient.get_taiwan_stock_price` — no caching, no fallback, no standard return envelope. Every Phase 1+ skill (technical indicators, screener, backtest engine) needs **historical daily OHLCV** as its foundational input, and they need it to be cheap (no repeat hits on FinMind's quota), reliable (one provider failing must not break the whole pipeline), and contract-stable (one return shape, one error vocabulary). This change builds that single layer so downstream skills stop reinventing it.

## What Changes

- Add `src/ohmystock/data/market_data.py` exposing `get_kline(symbol, period="1d", bars=250, end_date=None)` returning the standard `{ok, elapsed_ms, data, error}` envelope from `docs/tools-contracts.md` §0.1, with `data.bars: list[{ts, o, h, l, c, v, amount}]`.
- Add SQLite cache `bars_daily(symbol, date, o, h, l, c, v, amount, source, fetched_at)` with PRIMARY KEY `(symbol, date)`. Cache reads happen first; only the missing date gaps are fetched from upstream and written back.
- Add fallback chain `FinMind → twstock → yfinance`. Each upstream is wrapped in a typed adapter (`DataSource` Protocol) returning normalized rows. First adapter that returns a non-empty range wins; failures cascade to the next.
- Add error mapping per `tools-contracts.md` §0.2: `INVALID_INPUT`, `DATA_UNAVAILABLE`, `RATE_LIMIT`, `UPSTREAM_ERROR`, `AUTH_FAILED`. All upstream exceptions get translated into this envelope; raw `httpx`/SDK exceptions never escape `get_kline`.
- **Scope cut for MVP** — only `period="1d"` is supported in this change. Intraday (`1m/5m/15m/60m`) and `period="1w"/"1M"` raise `INVALID_INPUT` for now and are tracked as follow-up. `get_quote`, `get_index`, `get_rs_percentile`, `get_stage`, `get_trend_template`, `get_post_exit_returns` are NOT in scope — they are derivative metrics that belong in their own later changes once the bar source is solid.
- Add new dependencies: `twstock>=1.3`, `yfinance>=0.2`. Both fallback-only; main path stays FinMind.

## Capabilities

### New Capabilities

- `market-data-cache`: Historical daily OHLCV fetch with multi-provider fallback and SQLite cache. Owns the `get_kline` contract, the `bars_daily` table, the `DataSource` Protocol, and the standard error envelope for market-data calls.

### Modified Capabilities

(none — `external-connectors` spec keeps owning the raw FinMind connection layer; this change layers above it)

## Impact

- **New code**: `src/ohmystock/data/market_data.py`, `src/ohmystock/data/sources/{base,finmind,twstock,yfinance}.py`, `src/ohmystock/data/cache.py` (SQLite cache helpers).
- **Reused**: `FinMindClient` from `external-connectors` becomes the FinMind adapter implementation behind `DataSource`.
- **Schema**: `bars_daily` table added via the same `init_schema` path as `journal_entries` (or sibling init); migration is idempotent `CREATE TABLE IF NOT EXISTS`.
- **Dependencies**: `twstock`, `yfinance` added to `pyproject.toml`; `uv.lock` regenerated.
- **Config**: no new env vars (twstock/yfinance need no auth; reuse existing `FINMIND_TOKEN`).
- **Downstream unblocks**: technical-indicators skill, screener, backtest engine — all consume `get_kline` from this layer.
- **Out of scope / future**: Parquet partitioning (currently a single SQLite table is plenty for MVP), intraday bars, real-time quote, computed metrics (RS percentile / Stage / Trend Template), `universe` table, MOPS / TWSE OpenAPI.
