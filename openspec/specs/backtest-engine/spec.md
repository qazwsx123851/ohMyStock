# backtest-engine Specification

## Purpose
TBD - created by archiving change backtest-engine-mvp. Update Purpose after archive.

## Requirements

### Requirement: Public entrypoint `run_backtest` returns standard envelope

The system SHALL expose `ohmystock.backtest.run_backtest(strategy, bars_by_symbol, *, period, initial_capital, fee_discount=0.28, slippage_bps=30, day_trade=False)` that returns a dict matching the standard tool envelope: `{"ok": bool, "elapsed_ms": int, "data": <payload> | None, "error": {"code": str, "message": str, "retriable": bool} | None}`. On success `error` SHALL be `None`; on failure `data` SHALL be `None` and `error.code` SHALL be one of `INVALID_INPUT`, `DATA_UNAVAILABLE`, `CONFIG_ERROR`, `INTERNAL_ERROR`. The function MUST NOT raise to its caller for any expected failure mode (bad input, empty bars, strategy exception).

`bars_by_symbol` is a `dict[str, list[BarRow]]` where each value matches the `BarRow` shape from `market-data-cache` (`ts, o, h, l, c, v, amount`, ISO date `YYYY-MM-DD`). `period` is `{from: "YYYY-MM-DD", to: "YYYY-MM-DD"}`.

The engine SHALL treat `period` as a hard boundary: bars outside `[period.from, period.to]` MUST NOT be visible to strategies, included in the equity curve, or produce trades. If clipping leaves any symbol with no bars inside the period, the call SHALL fail with `INVALID_INPUT`.

#### Scenario: Successful run returns envelope with metrics and equity curve

- **WHEN** `run_backtest(strategy=BuyAndHold("2330"), bars_by_symbol={"2330": <20 daily bars>}, period={"from": "2026-04-01", "to": "2026-04-28"}, initial_capital=1_000_000)` is called with non-empty bars covering the period
- **THEN** the return value SHALL satisfy `result["ok"] is True`, `result["error"] is None`, `isinstance(result["elapsed_ms"], int)`, `"metrics" in result["data"]`, `"trades" in result["data"]`, `"equity_curve" in result["data"]`, and `len(result["data"]["equity_curve"]) >= 1`

#### Scenario: Strategy raising mid-run is caught and surfaced

- **GIVEN** a strategy whose `on_bar` raises `RuntimeError("boom")` on the third bar
- **WHEN** `run_backtest(...)` is called
- **THEN** the return value SHALL satisfy `result["ok"] is False`, `result["data"] is None`, `result["error"]["code"] == "INTERNAL_ERROR"`, and no exception SHALL escape the call

#### Scenario: Period clips out-of-range bars

- **GIVEN** `bars_by_symbol["2330"]` contains rows before `period.from` and after `period.to`
- **WHEN** `run_backtest(...)` is called
- **THEN** `data["equity_curve"]` SHALL contain only dates inside the period, and every trade's `signal_date` / `fill_date` SHALL be inside the period or `fill_date is None` for `cancelled_eob`

---

### Requirement: Input validation

The system SHALL validate inputs before any computation. `period.from` and `period.to` MUST match `YYYY-MM-DD`. `period.from` MUST be ≤ `period.to`. `initial_capital` MUST be a positive int. `bars_by_symbol` MUST be non-empty and every symbol's bars list MUST be non-empty and sorted strictly ascending by `ts`. `fee_discount` MUST be in `(0, 1]`. `slippage_bps` MUST be a non-negative int. Validation failures SHALL produce `error.code == "INVALID_INPUT"` with `retriable=False`.

#### Scenario: Empty bars rejected

- **WHEN** `run_backtest(strategy=..., bars_by_symbol={"2330": []}, period={"from":"2026-04-01","to":"2026-04-28"}, initial_capital=1_000_000)` is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

#### Scenario: Inverted period rejected

- **WHEN** `run_backtest(...)` is called with `period={"from":"2026-04-28","to":"2026-04-01"}`
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

#### Scenario: Non-monotonic bars rejected

- **WHEN** `bars_by_symbol["2330"]` contains two consecutive bars whose `ts` is equal or descending
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

---

### Requirement: Determinism

`run_backtest` SHALL produce byte-identical `data["equity_curve"]` and `data["trades"]` across two consecutive invocations with the same inputs in the same process and across two runs from a fresh interpreter. The engine, cost model, fill model, metrics, and the reference `sma_cross` strategy SHALL NOT call `random`, `numpy.random`, `time.time`, `datetime.now`, or any other non-deterministic source. The only wall-clock read SHALL be at the envelope boundary, used to populate `elapsed_ms`.

#### Scenario: Two consecutive runs match byte-for-byte

- **GIVEN** the same `strategy`, `bars_by_symbol`, `period`, `initial_capital`, and other parameters
- **WHEN** `run_backtest(...)` is called twice in succession and both return `ok=True`
- **THEN** `result1["data"]["equity_curve"] == result2["data"]["equity_curve"]` and `result1["data"]["trades"] == result2["data"]["trades"]` SHALL both hold

---

### Requirement: Order timing — signal at bar t, fill at bar t+1 open

The strategy's `on_bar(ctx)` for date `t` SHALL receive `ctx.bars` covering bars whose `ts` is in `[period.from, t]` inclusive (today's close included). Orders emitted on bar `t` SHALL be filled at the open of bar `t+1` (next trading day in the input bars). If `t` is the last bar in the input range, emitted orders SHALL be recorded with `status="cancelled_eob"` and SHALL NOT be filled.

#### Scenario: Order placed on last bar is cancelled

- **GIVEN** a strategy that emits a BUY on every bar
- **WHEN** `run_backtest(...)` is called over a 5-bar input range
- **THEN** the trade list SHALL contain at least one order with `status == "cancelled_eob"` corresponding to the order emitted on the final bar

#### Scenario: Same-bar fill is impossible

- **WHEN** the trade list is inspected after a successful run
- **THEN** for every filled order `f`, `f["fill_date"]` SHALL be strictly greater than `f["signal_date"]`

---

### Requirement: Taiwan cost model — `transaction_cost`

The system SHALL expose `ohmystock.backtest.costs.transaction_cost(side, price, qty, *, day_trade, fee_discount=0.28, trade_date=None) -> CostBreakdown` where `CostBreakdown` is `{"fee": float, "tax": float, "total": float}`.

- `fee = max(20.0, price * qty * 0.001425 * fee_discount)` for both buy and sell.
- `tax = 0.0` on `side="buy"`.
- `tax = price * qty * 0.0030` on `side="sell"` when `day_trade is False`.
- `tax = price * qty * 0.0015` on `side="sell"` when `day_trade is True` AND `trade_date <= "2027-12-31"`.
- `tax = price * qty * 0.0030` on `side="sell"` when `day_trade is True` AND `trade_date > "2027-12-31"` (sunset; the function MAY emit a one-time warning via stdlib `warnings`).
- `total = fee + tax`.

#### Scenario: Buy-side fee with discount, no tax

- **WHEN** `transaction_cost("buy", price=400.0, qty=1000, day_trade=False, fee_discount=0.28)` is called
- **THEN** `result["fee"] == 159.6` (i.e. `400 * 1000 * 0.001425 * 0.28`), `result["tax"] == 0.0`, `result["total"] == 159.6`

#### Scenario: NT$ 20 fee floor for tiny order

- **WHEN** `transaction_cost("buy", price=10.0, qty=10, day_trade=False, fee_discount=0.28)` is called (raw fee = 0.04)
- **THEN** `result["fee"] == 20.0` and `result["total"] == 20.0`

#### Scenario: Day-trade tax half-rate before sunset

- **WHEN** `transaction_cost("sell", price=400.0, qty=1000, day_trade=True, fee_discount=0.28, trade_date="2027-12-31")` is called
- **THEN** `result["tax"] == 600.0` (i.e. `400 * 1000 * 0.0015`)

#### Scenario: Day-trade tax falls back after sunset

- **WHEN** `transaction_cost("sell", price=400.0, qty=1000, day_trade=True, fee_discount=0.28, trade_date="2028-01-01")` is called
- **THEN** `result["tax"] == 1200.0` (i.e. `400 * 1000 * 0.0030`, the regular sell-side tax)

---

### Requirement: ±10% daily price-limit fill gate

The fill model SHALL gate orders against the previous bar's close. Let `prev_close` be the close of the bar immediately preceding the fill bar.

- A fill bar is **limit-up** if `abs(open - prev_close * 1.10) < 0.005`. On a limit-up fill bar, every BUY order targeting that symbol SHALL be recorded as `status="rejected_limit_up"` with no fill; SELL orders SHALL fill at `open * (1 - 0.010)`.
- A fill bar is **limit-down** if `abs(open - prev_close * 0.90) < 0.005`. On a limit-down fill bar, every SELL order SHALL be recorded as `status="rejected_limit_down"` with no fill; BUY orders SHALL fill at `open * (1 + 0.010)`.
- Otherwise the standard slippage applies: BUY fills at `open * (1 + slippage_bps/10000)`, SELL fills at `open * (1 - slippage_bps/10000)`.

The first bar of the input range has no `prev_close`; orders signalled on the bar before would have nowhere to fill. The engine SHALL handle this by treating any bar without a prior bar in the input as a non-limit bar (standard slippage), since orders cannot be signalled "before" the first bar.

#### Scenario: BUY rejected at limit-up

- **GIVEN** bars where bar `t-1` has `c = 100.0` and bar `t` has `o = 110.0` (exact ±10%)
- **AND** a strategy emits a BUY for that symbol on bar `t-1`
- **WHEN** `run_backtest(...)` is called
- **THEN** the trade list SHALL include an entry with `status == "rejected_limit_up"` and the portfolio's position SHALL NOT change as a result of that order

#### Scenario: SELL rejected at limit-down

- **GIVEN** bars where bar `t-1` has `c = 100.0` and bar `t` has `o = 90.0` (exact -10%)
- **AND** a strategy emits a SELL for an existing long position on bar `t-1`
- **WHEN** `run_backtest(...)` is called
- **THEN** the trade list SHALL include an entry with `status == "rejected_limit_down"` and the long position SHALL still be held after that bar

---

### Requirement: T+2 cash settlement for sells

The portfolio SHALL track two cash counters, `cash` (book) and `available_cash` (settled). Sell proceeds (`fill_price * qty - cost.total`) SHALL be added to `cash` immediately at the fill bar but SHALL only be added to `available_cash` two trading days later, where "trading day" is defined by the input bar dates (so non-trading days are skipped naturally). Buys SHALL debit `available_cash` immediately at the fill bar; orders that would push `available_cash` below zero SHALL be recorded with `status="rejected_insufficient_cash"` and SHALL NOT fill.

The equity curve at any date `d` SHALL equal `cash[d] + sum(position_qty[d] * close[d])`.

#### Scenario: Sell proceeds not spendable until T+2

- **GIVEN** a portfolio with `available_cash = 0` after buying everything possible, and a sell on bar `d` realises NT$ 100,000 net
- **AND** the strategy emits a BUY for a NT$ 50,000 order on bar `d+1`
- **WHEN** the engine processes bar `d+2` (one trading day after the sell, since fill happens on `d+1`'s open which is one day later)
- **THEN** the BUY order SHALL be recorded with `status == "rejected_insufficient_cash"` because the sell proceeds have not yet settled

#### Scenario: Sell proceeds available on T+2

- **GIVEN** the same setup as the previous scenario, but the BUY is emitted on bar `d+2` (so it fills at the open of `d+3`)
- **WHEN** the engine processes the fill
- **THEN** the BUY SHALL fill (assuming sufficient sell proceeds) because the sell from bar `d` has fully settled into `available_cash` by the start of bar `d+2`

---

### Requirement: Strategy Protocol

The system SHALL define `class Strategy(Protocol)` in `ohmystock.backtest.strategy` with at least these members:
- attribute `name: str`
- method `warmup_bars(self) -> int` — minimum number of bars required before `on_bar` will be called (engine SHALL skip bars before warmup is satisfied);
- method `on_bar(self, ctx: BarContext) -> list[OrderIntent]` — called once per bar per symbol after warmup;
- optional method `required_indicators(self) -> dict[str, Callable]` — defaults to `{}`; values SHALL be callables that map a list of bars to a list of indicator values of the same length.

`OrderIntent` SHALL be `{"symbol": str, "side": "buy"|"sell", "qty": int, "order_type": "market"|"limit", "limit_price": float | None}`. `BarContext` SHALL expose `date`, `symbol`, `bars` (closed bars up to and including today), `indicators` (dict of pre-computed series sliced to `[start..t]`), and `portfolio` (read-only view with `cash`, `available_cash`, and `positions: dict[symbol, qty]`).

The package SHALL ship one reference strategy `ohmystock.backtest.strategy.sma_cross.SmaCross(fast: int, slow: int)` using the `sma` indicator from `ohmystock.indicators`. The reference strategy is for tests/examples only and is not a production strategy.

#### Scenario: Strategy without `required_indicators` still runs

- **GIVEN** a strategy class that defines `name`, `warmup_bars`, and `on_bar` but does NOT define `required_indicators`
- **WHEN** `run_backtest(...)` is called with that strategy
- **THEN** the engine SHALL treat `required_indicators()` as returning `{}` and SHALL still run successfully

#### Scenario: Reference SmaCross strategy is importable and usable

- **WHEN** `from ohmystock.backtest.strategy.sma_cross import SmaCross; s = SmaCross(fast=5, slow=20); run_backtest(strategy=s, bars_by_symbol={"2330": <30 daily bars>}, period={...}, initial_capital=1_000_000)` is called
- **THEN** the call SHALL return `result["ok"] is True` and the trade list SHALL be a list (possibly empty if no cross occurred in the window)

---

### Requirement: Performance metrics in payload

The success payload `data` SHALL contain key `metrics` that is a dict with at least these keys:
- `total_return: float` (final equity / initial equity − 1)
- `cagr: float` (annualised, using actual elapsed calendar days)
- `sharpe: float` (annualised; daily-return mean / std × √252; `0.0` when std is zero)
- `sortino: float` (annualised; daily-return mean / downside std × √252; `0.0` when downside std is zero)
- `max_drawdown: float` (worst peak-to-trough fractional drop, expressed as a non-positive float; e.g. `-0.18` for an 18% drawdown)
- `mdd_duration_days: int` (calendar days from prior peak to recovery, or to end of curve if not recovered)
- `win_rate: float` (closed-trade winners / closed trades; `0.0` when no closed trades)
- `profit_factor: float` (sum of winning P&L / abs(sum of losing P&L); `inf` when no losing trades, `0.0` when no winning trades)
- `expectancy: float` (mean P&L per closed trade)
- `total_trades: int` (count of closed round-trips)

The success payload SHALL also contain key `equity_curve: list[{"date": str, "equity": float}]` with one entry per processed bar date in ascending order, and key `trades: list[Trade]` where `Trade` has at minimum keys `{symbol, signal_date, fill_date, side, qty, fill_price, cost, status}`.

#### Scenario: Flat equity yields zero returns and zero Sharpe

- **GIVEN** a strategy that never trades over a 60-bar input
- **WHEN** `run_backtest(..., initial_capital=1_000_000)` is called
- **THEN** `metrics["total_return"] == 0.0`, `metrics["sharpe"] == 0.0`, `metrics["max_drawdown"] == 0.0`, `metrics["total_trades"] == 0`, and `equity_curve[-1]["equity"] == 1_000_000.0`

#### Scenario: Single winning round-trip yields positive metrics

- **GIVEN** a controlled strategy that buys at bar 1 open and sells at bar 30 open, with bars rising monotonically such that the round-trip nets a positive P&L after costs
- **WHEN** `run_backtest(...)` is called
- **THEN** `metrics["total_trades"] == 1`, `metrics["win_rate"] == 1.0`, `metrics["profit_factor"] == float("inf")`, and `metrics["total_return"] > 0`

---

### Requirement: No FastAPI / API-layer reverse import

The backtest modules SHALL NOT import anything from `ohmystock.api`. Importing the backtest layer alone SHALL NOT pull in FastAPI / Starlette / Uvicorn.

#### Scenario: Backtest modules import without FastAPI

- **WHEN** a fresh subprocess runs `python -c "import ohmystock.backtest.engine, ohmystock.backtest.costs, ohmystock.backtest.fills, ohmystock.backtest.metrics, ohmystock.backtest.strategy"`
- **THEN** the process SHALL exit 0 and `sys.modules` SHALL NOT contain any of `fastapi`, `uvicorn`, `starlette`
