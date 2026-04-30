## Context

Phase 0–1 has shipped daily-bar fetching + cache (`market-data-cache`) and indicator primitives (`technical-indicators`). The next missing layer is a backtester so strategy work can produce verifiable performance numbers. Per `CLAUDE.md` §2 and the project memory ("avoid over-engineering, single-user solo dev, prefer simplest path"), this design picks the smallest engine that lets a strategy be written, indicators be evaluated, and a P&L curve be produced.

The Vibe-Trading reference (`design-zh-TW.md` §4.4) targets multi-engine plumbing, MOPS scrapers, processing-stock liquidity throttles, IPO honeymoon handling, and an `arq`-backed job queue. This MVP **deliberately omits all of that** — those become later changes once the core loop is correct.

## Goals / Non-Goals

**Goals:**
- A single public function `run_backtest(...)` returns a `market-data-cache`-style envelope `{ok, elapsed_ms, data, error}`; no exceptions escape.
- Daily-bar, long-only, whole-share backtest of one or more TW symbols over a date range.
- Strategy is a Protocol (`on_bar(...) -> list[OrderIntent]`) — easy to swap; ships with one reference strategy `sma_cross` only for tests.
- Honest Taiwan cost model: fee 0.1425% × 0.28 with NT$ 20 floor, tax 0.3% / 0.15% (day-trade flag), slippage 0.3% baseline (1.0% on price-limit days).
- ±10% daily price-limit fill gate (no fills cross the limit when the open is at limit-up/limit-down).
- T+2 cash settlement modelled at portfolio level (sell proceeds become "available cash" two trading days later).
- Deterministic: same inputs ⇒ same trades, equity curve, and metrics. No randomness, no wall-clock dependency, no global state.
- Metrics: total return, CAGR, Sharpe, Sortino, max drawdown, MDD duration (days), win rate, profit factor, expectancy, total trades, best/worst trade, equity curve, trade list.

**Non-Goals:**
- Intraday bars (only `period="1d"`, matching `market-data-cache`'s current scope).
- Shorts, margin, odd lots, IPO honeymoon, halts, MOPS scraper, processing-stock liquidity reduction, calendar-based half-day handling. (Listed in `design-zh-TW.md` §4.4.1 — deferred.)
- Walk-forward analysis (WFA), Monte Carlo, parameter grid expansion, multi-strategy portfolio. WFA is a Phase-5 dependency but not part of this MVP; the engine SHALL be callable in a loop by a future WFA layer.
- `backtest_tool` registration in `tools-contracts.md` §17, the `arq` job queue, the `/api/backtest` FastAPI route, the web-admin Backtest page. Each is its own follow-up.
- Live-broker compatibility shims (`design-zh-TW.md` §4.6 broker-adapter symmetry). MVP only reads bars; it does not pretend to share order types with Shioaji.

## Decisions

### D1. Public entrypoint shape: envelope, not exceptions

`run_backtest(...)` returns `{"ok": bool, "elapsed_ms": int, "data": <payload>|None, "error": {"code": str, "message": str, "retriable": bool}|None}` matching `get_kline`'s convention (`market-data-cache` spec, "Standard envelope"). Internal exceptions are caught at the boundary and translated to `error.code in {INVALID_INPUT, DATA_UNAVAILABLE, CONFIG_ERROR, INTERNAL_ERROR}`.

**Why:** consistency with the only other public data-layer function in the repo today; the future `backtest_tool` (§17) wraps the same shape, so no second translation step.
**Alternative rejected:** raising domain exceptions and letting callers handle them — diverges from the established pattern and forces every UI/CLI layer to re-translate.

### D2. Strategy seam: Protocol with `on_bar`, not subclassing

```python
class Strategy(Protocol):
    name: str
    def warmup_bars(self) -> int: ...
    def on_bar(self, ctx: BarContext) -> list[OrderIntent]: ...
```
`BarContext` carries: `date`, `symbol`, `bars` (closed bars up to and including today), `indicators` (pre-computed dict), `portfolio` (read-only view: cash, available_cash, positions). `OrderIntent` is `{symbol, side: "buy"|"sell", qty: int, order_type: "market"|"limit", limit_price: float|None}`.

**Why:** protocol = no inheritance ceremony for solo dev; matches how the indicators package was designed (pure functions, no base class). Strategies are small and replaceable.
**Alternative rejected:** event-callback style with separate `on_buy_filled`/`on_sell_filled`/`on_signal` — more surface area than this MVP needs; the engine surfaces fill information through the next `on_bar`'s `portfolio` view.

### D3. Order timing: signal at bar t, fill at bar t+1 open

The strategy sees `bars[start..t]` inclusive (today's close is known) and emits orders. Orders fill at the next bar's open with the slippage model in D5. If `t` is the last bar in the range, the order is cancelled (no fill, recorded as `cancelled_eob`).

**Why:** prevents look-ahead bias; matches the convention used in Vibe-Trading's a-shares engine and is the only sane default for end-of-day strategies.
**Alternative rejected:** same-bar fill at close — bakes in look-ahead; impossible to defend during Phase 5 review.

### D4. Cost model is a pure function in `costs.py`

```python
def transaction_cost(side: "buy"|"sell", price: float, qty: int, *, day_trade: bool, fee_discount: float = 0.28) -> CostBreakdown
```
Returns `{fee, tax, total}` where:
- `fee = max(20.0, price * qty * 0.001425 * fee_discount)` (TWSE NT$ 20 minimum).
- `tax = price * qty * (0.0015 if day_trade else 0.003)` on **sell only**; `0.0` on buy.
- `total = fee + tax`.

The day-trade tax floor (0.15%) is only applied if `day_trade=True` AND the date is `<= 2027-12-31` (sunset clause from `design-zh-TW.md` §4.4.1); past that date the tax falls back to 0.3% with a logged warning.

**Why:** a pure function is testable in isolation; date-based sunset is enforced in one place.
**Alternative rejected:** stuffing cost logic inside the engine loop — opaque, hard to verify against the SSOT.

### D5. Slippage and price-limit fill gate

- Default slippage: `slippage_bps = 30` (0.3%); buy fills at `open * (1 + 0.003)`, sell fills at `open * (1 - 0.003)`.
- On a bar whose `open` equals `prev_close * 1.10` (limit-up): BUY orders are **not filled** (recorded as `rejected_limit_up`); SELL orders fill at `open * (1 - 0.010)` (1% slippage proxy for thin sell-side liquidity).
- On a bar whose `open` equals `prev_close * 0.90` (limit-down): SELL orders are **not filled** (recorded as `rejected_limit_down`); BUY orders fill at `open * (1 + 0.010)`.
- Floating-point comparison uses tolerance `abs(open - limit) < 0.005` (sub-tick).

**Why:** deliberately conservative; correctly captures the "you can't get out at limit-down" failure mode that real strategies hit. No volume-weighted fill probability in MVP — that's a deferred enhancement.
**Alternative rejected:** Vibe-Trading's volume-weighted fill probability — needs intraday volume that the daily cache doesn't have; would require a separate data feed and is not on the MVP path.

### D6. T+2 cash settlement modelled at portfolio level

Portfolio tracks two cash counters: `cash` (book) and `available_cash` (settled). On a sell fill at trading-day `d`, the proceeds (`fill_price * qty - cost.total`) are added to `cash` immediately and to a queue `pending_settlements[(d + 2 trading days)]`. Each new bar drains the queue for any settlement date `<= today`.

Trading-day arithmetic uses the actual bar dates in the requested range (so non-trading days are skipped naturally without a separate calendar dependency).

Buys debit `available_cash` immediately; an order is **rejected (`rejected_insufficient_cash`)** if `available_cash < required_cash` at fill time.

**Why:** modelling T+2 at the cash-availability layer (not at the order-validation layer alone) is what catches the "I sold 2330 yesterday, can I buy 2454 today?" failure. MVP does **not** model the same-symbol day-trade exception (covered explicitly in `design-zh-TW.md` §4.4.1 and deferred); strategies that need it must declare `day_trade=True` and accept that the engine treats it as a single-day flat round-trip.
**Alternative rejected:** ignoring T+2 entirely — undercounts a real strategy constraint and produces optimistic backtests.

### D7. Indicator pre-computation

For each symbol, the engine asks the strategy `warmup_bars()` and pre-computes any indicators the strategy declares (via a `required_indicators(): dict[str, callable]` Protocol method) once over the full bar series. On each `on_bar(t)` the strategy receives the indicator series sliced to `[start..t]` (a view, not a copy where possible).

**Why:** indicators are pure and can be vectorised cheaply; recomputing inside the loop is O(N²) for no gain. Slicing-as-view keeps memory flat.
**Alternative rejected:** lazy / on-demand indicator computation — easier to write, but a 5-year daily backtest of a 200-symbol universe would be unworkable.

### D8. Determinism

- Symbol iteration order: sorted ascending.
- No `random`/`numpy.random` calls in the engine, costs, fills, metrics, or the reference strategy.
- No `datetime.now()` / `time.time()` inside the hot path; `elapsed_ms` is the only wall-clock read and lives at the boundary.
- `fee_discount`, `slippage_bps`, day-trade flag, and the day-tax sunset date are all explicit inputs (defaults documented in code, not env-derived).

A determinism test (run twice, byte-identical equity curve and trade list) is part of the spec.

### D9. Storage — none

The engine does not persist anything. Returning the equity curve and trade list as Python data structures is sufficient; persistence (SQLite `backtest_jobs` table from `design-zh-TW.md` §4.6 / web admin) is a follow-up change. This avoids designing a schema that we'd just have to revise once `backtest_tool` lands.

## Risks / Trade-offs

- **[Risk] Cost model drift vs. real broker** → Mitigation: cost is a pure function with literal values matching `workflow-cheatsheet.md` §6.6; a unit test pins the values so a future tweak triggers a visible failure.
- **[Risk] Price-limit fill gate is simpler than reality** (real markets get partial fills near the limit) → Mitigation: documented as MVP simplification in spec; the conservative direction (BUY rejected at limit-up, SELL rejected at limit-down) under-trades rather than over-trades, so backtests err pessimistic.
- **[Risk] Indicator pre-computation forces strategies to declare needs up-front** → Mitigation: the Protocol method is optional with a default of `{}`; strategies that compute on the fly still work, just slower.
- **[Risk] Multi-symbol order arbitration when cash is tight** → Mitigation: orders are processed in `(symbol_sort_order, intent_order)` deterministic sequence; first to consume cash wins; later orders that would push `available_cash` below zero are rejected with `rejected_insufficient_cash`.
- **[Risk] No persistence means re-running a costly backtest is the only way to inspect results** → Acceptable for MVP; the engine's API shape leaves room for a thin caller-side persistence layer.
- **[Trade-off] No WFA built in** → Pushed to a later change; the engine's pure-function entrypoint is friendly to a wrapping WFA loop, so we are not painting ourselves into a corner.
