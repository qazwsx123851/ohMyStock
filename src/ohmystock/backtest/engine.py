"""Deterministic daily-bar backtest engine.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
"""

from __future__ import annotations

import re
import time
from typing import Any

from ohmystock.backtest.costs import transaction_cost
from ohmystock.backtest.fills import compute_fill
from ohmystock.backtest.metrics import compute_metrics
from ohmystock.backtest.portfolio import Portfolio
from ohmystock.backtest.strategy.base import BarContext, required_indicators_of
from ohmystock.data.sources.base import BarRow

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _err(code: str, message: str, retriable: bool = False) -> dict[str, Any]:
    return {"code": code, "message": message, "retriable": retriable}


def _envelope(
    ok: bool,
    elapsed_ms: int,
    data: dict | None,
    error: dict | None,
) -> dict[str, Any]:
    return {"ok": ok, "elapsed_ms": elapsed_ms, "data": data, "error": error}


def _validate_inputs(
    strategy: object,
    bars_by_symbol: dict[str, list[BarRow]],
    period: dict[str, str],
    initial_capital: int | float,
    fee_discount: float,
    slippage_bps: int,
) -> str | None:
    if not isinstance(period, dict) or "from" not in period or "to" not in period:
        return "period must be {'from': YYYY-MM-DD, 'to': YYYY-MM-DD}"
    if not (DATE_RE.match(period["from"]) and DATE_RE.match(period["to"])):
        return f"period dates must match YYYY-MM-DD, got {period}"
    if period["from"] > period["to"]:
        return f"period.from {period['from']} > period.to {period['to']}"
    if not isinstance(initial_capital, (int, float)) or initial_capital <= 0:
        return f"initial_capital must be positive, got {initial_capital}"
    if not (0 < fee_discount <= 1):
        return f"fee_discount must be in (0, 1], got {fee_discount}"
    if not isinstance(slippage_bps, int) or slippage_bps < 0:
        return f"slippage_bps must be a non-negative int, got {slippage_bps}"
    if not isinstance(bars_by_symbol, dict) or not bars_by_symbol:
        return "bars_by_symbol must be a non-empty dict"
    for sym, bars in bars_by_symbol.items():
        if not bars:
            return f"bars for {sym} are empty"
        prev_ts = ""
        for b in bars:
            ts = b["ts"]
            if not DATE_RE.match(ts):
                return f"bar ts {ts!r} for {sym} must match YYYY-MM-DD"
            if prev_ts and ts <= prev_ts:
                return f"bars for {sym} must be strictly ascending; {prev_ts} -> {ts}"
            prev_ts = ts
    if not hasattr(strategy, "on_bar") or not hasattr(strategy, "warmup_bars"):
        return "strategy must define on_bar and warmup_bars"
    return None


def _settlement_date(fill_date: str, timeline: list[str]) -> str:
    """Return T+2 trading-day settlement date.

    `Portfolio.advance_to(today)` drains entries with date `< today`, so a
    settlement key of `timeline[idx + 2]` becomes spendable from start of T+3.
    """
    try:
        idx = timeline.index(fill_date)
    except ValueError:
        return fill_date
    target = idx + 2
    if target < len(timeline):
        return timeline[target]
    return f"{fill_date}+sentinel"


def run_backtest(
    strategy: Any,
    bars_by_symbol: dict[str, list[BarRow]],
    *,
    period: dict[str, str],
    initial_capital: int | float,
    fee_discount: float = 0.28,
    slippage_bps: int = 30,
    day_trade: bool = False,
) -> dict[str, Any]:
    t0 = time.perf_counter_ns()
    try:
        msg = _validate_inputs(
            strategy, bars_by_symbol, period, initial_capital, fee_discount, slippage_bps
        )
        if msg is not None:
            elapsed_ms = (time.perf_counter_ns() - t0) // 1_000_000
            return _envelope(False, int(elapsed_ms), None, _err("INVALID_INPUT", msg))

        symbols = sorted(bars_by_symbol.keys())
        bars_by_symbol = {s: list(bars_by_symbol[s]) for s in symbols}

        ind_specs = required_indicators_of(strategy)
        indicators_by_symbol: dict[str, dict[str, list]] = {
            sym: {name: list(fn(bars_by_symbol[sym])) for name, fn in ind_specs.items()}
            for sym in symbols
        }

        all_dates: set[str] = set()
        for sym in symbols:
            for b in bars_by_symbol[sym]:
                all_dates.add(b["ts"])
        timeline = sorted(all_dates)

        bar_index: dict[str, dict[str, int]] = {
            sym: {b["ts"]: i for i, b in enumerate(bars_by_symbol[sym])}
            for sym in symbols
        }

        portfolio = Portfolio.with_initial(float(initial_capital))
        pending_orders: list[dict[str, Any]] = []
        trades: list[dict[str, Any]] = []
        equity_curve: list[dict[str, Any]] = []
        warmup = int(strategy.warmup_bars())

        for t_idx, today in enumerate(timeline):
            portfolio.advance_to(today)

            still_pending: list[dict[str, Any]] = []
            for po in pending_orders:
                sym = po["symbol"]
                if today not in bar_index[sym]:
                    still_pending.append(po)
                    continue
                fill_idx = bar_index[sym][today]
                fill_bar = bars_by_symbol[sym][fill_idx]
                prev_close = (
                    bars_by_symbol[sym][fill_idx - 1]["c"] if fill_idx > 0 else None
                )
                fr = compute_fill(po["intent"], fill_bar, prev_close, slippage_bps=slippage_bps)
                if fr["status"] != "filled":
                    trades.append(
                        {
                            "symbol": sym,
                            "signal_date": po["signal_date"],
                            "fill_date": today,
                            "side": po["intent"]["side"],
                            "qty": po["intent"]["qty"],
                            "fill_price": None,
                            "cost": {"fee": 0.0, "tax": 0.0, "total": 0.0},
                            "status": fr["status"],
                            "reason": fr.get("reason"),
                        }
                    )
                    continue
                fill_price = float(fr["fill_price"])
                qty = int(po["intent"]["qty"])
                side = po["intent"]["side"]
                cost = transaction_cost(
                    side,
                    fill_price,
                    qty,
                    day_trade=day_trade,
                    fee_discount=fee_discount,
                    trade_date=today,
                )
                if side == "buy":
                    if not portfolio.can_afford_buy(fill_price, qty, cost):
                        trades.append(
                            {
                                "symbol": sym,
                                "signal_date": po["signal_date"],
                                "fill_date": today,
                                "side": side,
                                "qty": qty,
                                "fill_price": None,
                                "cost": {"fee": 0.0, "tax": 0.0, "total": 0.0},
                                "status": "rejected_insufficient_cash",
                                "reason": (
                                    f"available_cash {portfolio.available_cash:.2f} < "
                                    f"required {fill_price * qty + cost['total']:.2f}"
                                ),
                            }
                        )
                        continue
                    portfolio.apply_buy(sym, qty, fill_price, cost, today)
                else:
                    held = portfolio.positions.get(sym, 0)
                    if qty > held:
                        trades.append(
                            {
                                "symbol": sym,
                                "signal_date": po["signal_date"],
                                "fill_date": today,
                                "side": side,
                                "qty": qty,
                                "fill_price": None,
                                "cost": {"fee": 0.0, "tax": 0.0, "total": 0.0},
                                "status": "rejected_no_position",
                                "reason": f"sell qty {qty} exceeds holdings {held}",
                            }
                        )
                        continue
                    settlement = _settlement_date(today, timeline)
                    portfolio.apply_sell(sym, qty, fill_price, cost, today, settlement)
                trades.append(
                    {
                        "symbol": sym,
                        "signal_date": po["signal_date"],
                        "fill_date": today,
                        "side": side,
                        "qty": qty,
                        "fill_price": fill_price,
                        "cost": dict(cost),
                        "status": "filled",
                        "reason": None,
                    }
                )
            pending_orders = still_pending

            is_last_bar = t_idx == len(timeline) - 1
            for sym in symbols:
                if today not in bar_index[sym]:
                    continue
                bar_idx = bar_index[sym][today]
                if bar_idx + 1 < warmup:
                    continue
                bars_visible = bars_by_symbol[sym][: bar_idx + 1]
                indicators_visible = {
                    name: series[: bar_idx + 1]
                    for name, series in indicators_by_symbol[sym].items()
                }
                ctx = BarContext(
                    date=today,
                    symbol=sym,
                    bars=bars_visible,
                    indicators=indicators_visible,
                    portfolio=portfolio.view(),
                )
                intents = strategy.on_bar(ctx) or []
                for intent in intents:
                    if is_last_bar:
                        trades.append(
                            {
                                "symbol": intent["symbol"],
                                "signal_date": today,
                                "fill_date": None,
                                "side": intent["side"],
                                "qty": intent["qty"],
                                "fill_price": None,
                                "cost": {"fee": 0.0, "tax": 0.0, "total": 0.0},
                                "status": "cancelled_eob",
                                "reason": "signal on last bar; nowhere to fill",
                            }
                        )
                        continue
                    pending_orders.append(
                        {
                            "intent": dict(intent),
                            "symbol": intent["symbol"],
                            "signal_date": today,
                        }
                    )

            equity = portfolio.cash
            for sym, qty in portfolio.positions.items():
                if today in bar_index[sym]:
                    close_px = bars_by_symbol[sym][bar_index[sym][today]]["c"]
                else:
                    last_idx = max(
                        i for i, b in enumerate(bars_by_symbol[sym]) if b["ts"] <= today
                    )
                    close_px = bars_by_symbol[sym][last_idx]["c"]
                equity += qty * close_px
            equity_curve.append({"date": today, "equity": float(equity)})

        metrics = compute_metrics(
            equity_curve, trades, initial_capital=float(initial_capital)
        )
        elapsed_ms = (time.perf_counter_ns() - t0) // 1_000_000
        return _envelope(
            True,
            int(elapsed_ms),
            {"metrics": metrics, "equity_curve": equity_curve, "trades": trades},
            None,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.perf_counter_ns() - t0) // 1_000_000
        return _envelope(
            False,
            int(elapsed_ms),
            None,
            _err("INTERNAL_ERROR", f"{type(exc).__name__}: {exc}"),
        )
