## Context

Phase 1's screener, entry-decider, and backtest engine all need derived signals from OHLCV. `get_kline` from `market-data-cache` returns a `list[BarRow]` (each `{ts, o, h, l, c, v, amount}`); we now need a thin layer of indicator math sitting between that and any consumer that wants to score / filter / decide. The existing TW-trading codebases the user has looked at either pull `talib` (C lib, painful Windows wheel install) or `pandas-ta` (heavy dep with its own opinions) or hand-roll inconsistently. For a single-user personal project running in `uv` on Windows, neither library pays for itself given the math is < 100 lines.

This change is the **smallest possible** indicator layer — just enough surface area to write a real backtest strategy and a real screener filter on top, with golden-value tests so we never have to second-guess the math during a debugging session.

## Goals / Non-Goals

**Goals:**
- Six indicators — `sma`, `ema`, `rsi`, `macd`, `atr`, `bollinger_bands` — as pure stateless Python functions.
- One canonical input shape: `list[BarRow]` for OHLC-needing indicators, `list[float]` for close-only ones (callers pass `[b["c"] for b in bars]`).
- One canonical output convention: list of the same length as input, with `None` for warmup positions where the indicator is not yet defined.
- Golden-value tests against hand-computed expected values so a future refactor cannot silently regress.
- Zero new third-party dependencies.

**Non-Goals:**
- Tool-envelope wrapper (`get_indicator(symbol, name, period, ...)` returning `{ok, data, error}`) — defer until a real Tool consumer exists.
- Minervini-specific derivatives (RS percentile, Stage classification, Trend Template, VCP detection) — own subsequent change(s) once these primitives exist.
- Pandas DataFrame API surface — `list[BarRow]` only. A 5-line wrapper can be added later if a downstream wants it.
- Streaming / incremental computation. Backtest replays the full series each time; that's fine at single-symbol scale.
- Multi-timeframe resampling (e.g. resample daily → weekly inside the indicator). Caller resamples first.
- Less common indicators (KDJ / CCI / Ichimoku / etc.) — add when a strategy actually wants them.

## Decisions

### D1. Hand-roll over `talib` / `pandas-ta`

Implement six indicators in plain Python + numpy.

**Why:**
- `talib` requires a C library + a wheel that is fragile on Windows; `pandas-ta` is a 500-file dep with strong opinions about column naming.
- The total math here is small. SMA = rolling mean. EMA / Wilder = recursive smoothing. MACD = EMA(12) - EMA(26) + EMA(9). Bollinger = SMA ± k·rolling_std. ATR = Wilder smoothing of true-range. Each is < 20 lines. Total < 100 lines.
- Hand-rolled means we own the warmup convention, the Wilder vs simple choice, and the corner cases (constant input → RSI = 50 by convention, etc.).

**Trade-off:** We don't get 100+ indicators "for free" from a library. Acceptable: we add per-indicator changes when we actually need new ones.

### D2. Output convention: `None` in warmup positions, not `NaN`

Each indicator returns a list of the same length as the input. Positions where the indicator is mathematically undefined (e.g., `sma(period=20)` for the first 19 bars) are `None`, never `float('nan')`.

**Why:** `None` is unambiguous for downstream code (`if value is None: continue`); `NaN` propagates silently through arithmetic and only surfaces during plotting or aggregation. Per `docs/safety-and-simulation.md` philosophy of "fail loud, not silent", `None` forces consumers to handle warmup explicitly.

**Trade-off:** Slightly more annoying for vectorised consumers that want a numpy array — they convert with `np.array([np.nan if v is None else v for v in xs])`. That's fine; vectorised consumers are rare in this codebase (the agent reasons over individual bar positions).

### D3. Wilder smoothing for RSI and ATR

Use Wilder's recursive smoothing (`new = ((n-1)*prev + current) / n`) for RSI and ATR, not simple moving average smoothing.

**Why:** Wilder is the canonical convention for these two — every reference implementation (StockCharts, Investopedia, TradingView default, talib) uses it. If we used simple SMA smoothing our RSI / ATR would not match what the user reads on charts; that's a quiet bug that confuses every later debugging session.

For SMA / EMA / MACD / Bollinger, use the standard textbook definitions (no Wilder variant).

### D4. Single module `core.py` for all six

Put all six functions in `src/ohmystock/indicators/core.py`. `__init__.py` re-exports them so callers can `from ohmystock.indicators import sma, rsi, atr`.

**Why:** Six small functions in one file is easier to read and grep than six 20-line files in three subdirectories. Split into `trend.py` / `momentum.py` / `volatility.py` only when we add a 7th indicator and one file becomes uncomfortably long.

### D5. Input shape: `list[BarRow]` for OHLC, `list[float]` for close-only

- `sma(closes: list[float], period: int) -> list[float | None]`
- `ema(closes: list[float], period: int) -> list[float | None]`
- `rsi(closes: list[float], period: int = 14) -> list[float | None]`
- `macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[list[float | None], list[float | None], list[float | None]]` — returns `(macd_line, signal_line, histogram)`
- `atr(bars: list[BarRow], period: int = 14) -> list[float | None]`
- `bollinger_bands(closes: list[float], period: int = 20, k: float = 2.0) -> tuple[list[float | None], list[float | None], list[float | None]]` — returns `(upper, middle, lower)`

**Why split close-only vs OHLC inputs:** ATR genuinely needs `h` and `l` and prior `c`; making everyone pass `list[BarRow]` would force callers writing `[{"c": x, "h": x, "l": x, "o": x, ...} for x in closes]` boilerplate when they have only closes. Asymmetry is small and explicit.

## Risks / Trade-offs

- **[Risk] Warmup `None` breaks vectorised callers** → Acceptable; the project's primary consumer is the LLM agent reasoning bar-by-bar, not a vectorised pipeline. Document the convention and supply a `to_numpy(values)` helper later if a real consumer needs it.
- **[Risk] Hand-rolled math has subtle bugs versus reference impls** → Mitigated by golden-value tests using hand-computed reference outputs on small series + cross-checked against a published reference (e.g., StockCharts RSI worked example).
- **[Risk] Choosing Wilder for RSI/ATR vs simple smoothing creates surprise** → Stated explicitly in spec scenarios so it's not silent.
- **[Trade-off] No tool wrapper** → If a future Tool wants `get_indicator(...)`, we add a thin envelope layer in a separate change. The pure functions remain the load-bearing API.
- **[Trade-off] Single file `core.py`** → If indicator count grows past ~10, split into `trend / momentum / volatility / volume` submodules. No premature split.
