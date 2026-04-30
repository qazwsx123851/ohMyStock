## Why

`get_kline` (just shipped via `market-data-cache`) returns raw daily OHLCV bars, but Phase 1's screener / entry-decider / backtest engine all need **derived signals** to act on — SMA crossovers for trend, RSI for momentum exhaustion, ATR for the stop-loss formula in `docs/workflow-cheatsheet.md` §6.6, Bollinger Bands for volatility squeeze, etc. Without a stable indicator layer every downstream skill will reinvent it (and disagree on warmup conventions, Wilder vs simple smoothing, etc.). This change builds the smallest indicator module that unblocks Phase 1.

## What Changes

- Add `src/ohmystock/indicators/` package with **pure functions** for the six MVP indicators: `sma`, `ema`, `rsi` (Wilder), `macd`, `atr` (Wilder), `bollinger_bands`.
- Each function consumes the same `list[BarRow]` shape returned by `get_kline` (or `list[float]` for close-only inputs) and returns aligned outputs of the same length, with `None` for warmup positions where the indicator is not yet defined.
- Add golden-value tests (small known input series → known output) so we never regret-fix the math later.
- **Scope cut for MVP** — only the six listed indicators. No tool-envelope wrapper (`get_indicator(...)` style), no Minervini-specific derivatives (RS percentile, Stage, Trend Template, VCP), no streaming/incremental computation, no multi-timeframe resampling. Each of those gets its own subsequent change once a real consumer needs it.
- No new third-party dependencies. Hand-roll with stdlib + numpy (already transitive via pandas/yfinance) — these are < 100 lines total, stable forever, and a `pandas-ta` / `talib` dep is heavier than the math itself.

## Capabilities

### New Capabilities

- `technical-indicators`: Pure-function technical indicator primitives over `list[BarRow]` / `list[float]`. Owns warmup convention (return `None` for undefined positions, never NaN), Wilder vs simple smoothing choice per indicator, and the canonical signature shape that all downstream consumers rely on.

### Modified Capabilities

(none — `market-data-cache` keeps owning the bar source layer; this change only consumes it.)

## Impact

- **New code**: `src/ohmystock/indicators/__init__.py`, `src/ohmystock/indicators/core.py` (single module — six small functions don't justify subdirectories). Optionally split later if it grows.
- **New tests**: `tests/test_indicators.py` with golden-value cases per indicator + warmup-`None` cases + property checks (e.g., SMA(period=1, xs) == xs).
- **Reused**: `BarRow` TypedDict from `ohmystock.data.sources.base`.
- **Schema**: none — pure functions, no DB, no env.
- **Dependencies**: none new. numpy (transitive) is enough.
- **Downstream unblocks**: backtest engine (needs SMA/EMA/ATR for entry/exit signals), screener (needs RSI/BB for momentum / volatility filters), Minervini derivative changes (RS percentile / Stage / Trend Template all build on these primitives).
- **Out of scope / future**: tool-envelope wrapper, Minervini derivatives, streaming, multi-timeframe, custom indicators (KDJ / CCI / Ichimoku / etc.) — each its own subsequent change with a real consumer.
