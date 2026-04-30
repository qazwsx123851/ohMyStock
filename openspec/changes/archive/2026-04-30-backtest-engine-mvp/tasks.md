## 1. Package skeleton

- [x] 1.1 Add module files under `src/ohmystock/backtest/`: `engine.py`, `costs.py`, `fills.py`, `metrics.py`, `portfolio.py`, `strategy/__init__.py`, `strategy/base.py`, `strategy/sma_cross.py`. Re-export `run_backtest` from `ohmystock/backtest/__init__.py`.
- [x] 1.2 Add empty test placeholders: `tests/test_backtest_costs.py`, `tests/test_backtest_fills.py`, `tests/test_backtest_metrics.py`, `tests/test_backtest_portfolio.py`, `tests/test_backtest_engine.py`, `tests/test_backtest_reverse_import.py`, `tests/test_backtest_determinism.py`.

## 2. Cost model (`costs.py`)

- [x] 2.1 Define `CostBreakdown = TypedDict("CostBreakdown", {"fee": float, "tax": float, "total": float})`.
- [x] 2.2 Implement `transaction_cost(side, price, qty, *, day_trade, fee_discount=0.28, trade_date=None) -> CostBreakdown` with: NT$ 20 fee floor; sell-only tax 0.3% (regular) / 0.15% (day-trade ≤ 2027-12-31); sunset fallback to 0.3% with one-time `warnings.warn` when `day_trade=True` and `trade_date > "2027-12-31"`.
- [x] 2.3 Tests in `tests/test_backtest_costs.py` cover the four scenarios in spec "Taiwan cost model" plus a regression test pinning the literal constants `0.001425`, `0.28`, `0.0030`, `0.0015`, `20.0`.

## 3. Fill model (`fills.py`)

- [x] 3.1 Implement `compute_fill(order, fill_bar, prev_close, *, slippage_bps) -> FillResult` returning either a filled price or a rejection status (`rejected_limit_up`, `rejected_limit_down`).
- [x] 3.2 Use tolerance `abs(open - prev_close * 1.10) < 0.005` for limit-up detection and `abs(open - prev_close * 0.90) < 0.005` for limit-down. Treat `prev_close=None` as a non-limit bar (standard slippage).
- [x] 3.3 Tests in `tests/test_backtest_fills.py` cover both limit-up scenarios (BUY rejected, SELL fills at -1.0%), both limit-down scenarios (SELL rejected, BUY fills at +1.0%), and the standard-slippage path.

## 4. Portfolio with T+2 settlement (`portfolio.py`)

- [x] 4.1 Implement `Portfolio` class with fields `cash`, `available_cash`, `positions: dict[str, int]`, `pending_settlements: dict[str, float]` (key = settlement date string).
- [x] 4.2 On `apply_buy(symbol, qty, fill_price, cost, fill_date)`: debit `available_cash` and `cash` by `fill_price*qty + cost.total`; raise/return rejection if `available_cash` would go negative.
- [x] 4.3 On `apply_sell(symbol, qty, fill_price, cost, fill_date, settlement_date)`: credit `cash` immediately; queue net proceeds to `pending_settlements[settlement_date]` (settlement_date = fill_date + 2 trading days from the input bar dates passed by the engine).
- [x] 4.4 On `advance_to(today)`: drain every pending settlement whose date `<` `today` (strict, so settlement at T+2 becomes spendable at start of T+3) into `available_cash`.
- [x] 4.5 Provide a read-only `view()` returning `{cash, available_cash, positions}` for `BarContext.portfolio`.
- [x] 4.6 Tests in `tests/test_backtest_portfolio.py` cover both T+2 scenarios from the spec ("not spendable until T+2", "available on T+2") and `rejected_insufficient_cash`.

## 5. Strategy Protocol + reference strategy (`strategy/`)

- [x] 5.1 Define `Strategy` Protocol (`name`, `warmup_bars`, `on_bar`, optional `required_indicators`), `OrderIntent` TypedDict, `BarContext` dataclass (`date`, `symbol`, `bars`, `indicators`, `portfolio`).
- [x] 5.2 Add a small `BuyAndHold(symbol)` test helper strategy in `tests/conftest.py` (or a `tests/_strategies.py`).
- [x] 5.3 Implement `SmaCross(fast: int, slow: int)` in `strategy/sma_cross.py`: `required_indicators` returns `{"sma_fast": lambda bars: sma([b["c"] for b in bars], fast), "sma_slow": ...}`; `on_bar` emits BUY on golden cross / SELL on death cross.
- [x] 5.4 Test in `tests/test_backtest_engine.py` confirms the strategy without `required_indicators` still runs (default `{}`) and the importable-and-usable scenario for `SmaCross`.

## 6. Metrics (`metrics.py`)

- [x] 6.1 Implement `compute_metrics(equity_curve: list[EquityPoint], trades: list[Trade], *, initial_capital: float) -> dict` producing all keys in spec "Performance metrics in payload".
- [x] 6.2 Edge-case handling: zero std → `sharpe=0.0`; no losing trades → `profit_factor=float('inf')`; no closed trades → `win_rate=0.0`, `profit_factor=0.0`; no recovery → `mdd_duration_days = days_from_peak_to_end`.
- [x] 6.3 Tests in `tests/test_backtest_metrics.py` cover flat-equity zeros and a hand-checked single-winning-round-trip case.

## 7. Engine loop (`engine.py`)

- [x] 7.1 Implement input validation per spec "Input validation" — return envelope with `INVALID_INPUT` for empty bars, inverted period, non-monotonic bars, non-positive `initial_capital`, `fee_discount` out of range, negative `slippage_bps`.
- [x] 7.2 Pre-compute every indicator the strategy declares once per symbol over the full bar series; treat absent `required_indicators` as `{}`.
- [x] 7.3 Build the trading-day timeline from the union of bar `ts` values across symbols, sorted ascending.
- [x] 7.4 Per timeline date `t` in deterministic symbol-sorted order: drain pending settlements ≤ `t`; fill any orders signalled at `t-1` using `fills.compute_fill`; call `strategy.on_bar(ctx)` for each symbol that has a bar at `t` and warmup is satisfied; queue resulting `OrderIntent` for fill at `t+1`. Append an `EquityPoint` per timeline date using close prices at `t`.
- [x] 7.5 Wrap the entire entrypoint in `try/except` translating any unexpected exception to envelope `error.code = "INTERNAL_ERROR"` with `retriable=False`. Capture `elapsed_ms` at the boundary using `time.perf_counter_ns()` (only wall-clock read allowed).
- [x] 7.6 On the last timeline bar, mark any newly-emitted orders as `status="cancelled_eob"` and SHALL NOT fill.
- [x] 7.7 Tests in `tests/test_backtest_engine.py` cover the success scenario, strategy-raises scenario, last-bar-cancellation, and same-bar-fill-impossible invariant.

## 8. Determinism + reverse-import guards

- [x] 8.1 `tests/test_backtest_determinism.py`: run `run_backtest(...)` twice with identical inputs and assert byte-identical `equity_curve` and `trades`.
- [x] 8.2 Add a static check to the same file (or a new `test_backtest_no_random.py`) that greps the `ohmystock.backtest` source for `random`, `numpy.random`, `time.time`, `datetime.now` (allowing `time.perf_counter_ns` only in `engine.py` boundary).
- [x] 8.3 `tests/test_backtest_reverse_import.py`: subprocess-import every backtest module and assert `fastapi`, `uvicorn`, `starlette` are NOT in `sys.modules`.

## 9. Validate + verify

- [x] 9.1 Run `openspec validate --change backtest-engine-mvp --strict` and resolve any warnings.
- [x] 9.2 Run `pytest tests/test_backtest_*.py -q` — all new tests green.
- [x] 9.3 Run the full repo test suite (`pytest -q`) to confirm no regression in existing capabilities.
- [x] 9.4 Manual smoke: run a 60-bar `SmaCross(5, 20)` against a single cached symbol and inspect that `metrics`, `equity_curve`, and `trades` are all present and finite.

## 10. Archive

- [x] 10.1 When all task groups above are checked, run `/opsx:archive backtest-engine-mvp` to fold `specs/backtest-engine/spec.md` into `openspec/specs/backtest-engine/spec.md` and move the change to `openspec/changes/archive/`.
