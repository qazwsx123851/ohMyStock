"""Performance metrics for the backtest engine.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
("Performance metrics in payload" requirement).
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, TypedDict

TRADING_DAYS_PER_YEAR = 252
CAGR_DAYS_PER_YEAR = 365.25


class EquityPoint(TypedDict):
    date: str
    equity: float


def _parse(d: str) -> date:
    y, m, dd = d.split("-")
    return date(int(y), int(m), int(dd))


def _daily_returns(equity: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(equity)):
        prev = equity[i - 1]
        if prev <= 0:
            out.append(0.0)
        else:
            out.append(equity[i] / prev - 1.0)
    return out


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float], mean: float) -> float:
    if len(xs) < 2:
        return 0.0
    var = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def _max_drawdown(equity: list[float], dates: list[str]) -> tuple[float, int]:
    if not equity:
        return 0.0, 0
    peak = equity[0]
    peak_idx = 0
    worst = 0.0
    worst_peak_idx = 0
    recovered_after_worst = True
    for i, e in enumerate(equity):
        if e > peak:
            peak = e
            peak_idx = i
        if peak > 0:
            dd = e / peak - 1.0
            if dd < worst:
                worst = dd
                worst_peak_idx = peak_idx
                recovered_after_worst = False
        if not recovered_after_worst and e >= equity[worst_peak_idx]:
            recovered_after_worst = True
            duration = (_parse(dates[i]) - _parse(dates[worst_peak_idx])).days
            return worst, duration
    if worst == 0.0:
        return 0.0, 0
    end_idx = len(equity) - 1
    duration = (_parse(dates[end_idx]) - _parse(dates[worst_peak_idx])).days
    return worst, duration


def compute_metrics(
    equity_curve: list[EquityPoint],
    trades: list[dict[str, Any]],
    *,
    initial_capital: float,
) -> dict[str, Any]:
    if not equity_curve:
        return {
            "total_return": 0.0,
            "cagr": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "mdd_duration_days": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "total_trades": 0,
        }

    equity = [pt["equity"] for pt in equity_curve]
    dates = [pt["date"] for pt in equity_curve]
    final_equity = equity[-1]
    total_return = final_equity / initial_capital - 1.0 if initial_capital > 0 else 0.0

    elapsed_days = (_parse(dates[-1]) - _parse(dates[0])).days
    if elapsed_days > 0 and initial_capital > 0 and final_equity > 0:
        years = elapsed_days / CAGR_DAYS_PER_YEAR
        cagr = (final_equity / initial_capital) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    else:
        cagr = 0.0

    rets = _daily_returns(equity)
    mean_r = _mean(rets)
    std_r = _std(rets, mean_r)
    sharpe = (
        (mean_r / std_r) * math.sqrt(TRADING_DAYS_PER_YEAR)
        if std_r > 0
        else 0.0
    )
    downside = [r for r in rets if r < 0]
    if downside:
        mean_d = _mean(downside)
        std_d = _std(downside, mean_d)
        sortino = (mean_r / std_d) * math.sqrt(TRADING_DAYS_PER_YEAR) if std_d > 0 else 0.0
    else:
        sortino = 0.0

    mdd, mdd_days = _max_drawdown(equity, dates)

    closed = _closed_round_trips(trades)
    if not closed:
        win_rate = 0.0
        profit_factor = 0.0
        expectancy = 0.0
        total_trades = 0
    else:
        wins = [p for p in closed if p > 0]
        losses = [p for p in closed if p < 0]
        win_rate = len(wins) / len(closed)
        win_sum = sum(wins)
        loss_sum = sum(losses)
        if not losses and wins:
            profit_factor = float("inf")
        elif not wins:
            profit_factor = 0.0
        else:
            profit_factor = win_sum / abs(loss_sum)
        expectancy = sum(closed) / len(closed)
        total_trades = len(closed)

    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": mdd,
        "mdd_duration_days": int(mdd_days),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "total_trades": total_trades,
    }


def _closed_round_trips(trades: list[dict[str, Any]]) -> list[float]:
    """Pair filled BUYs and SELLs per symbol FIFO; return realised P&L per closed trip.

    Only `status == "filled"` entries participate.
    """
    pnl: list[float] = []
    open_lots: dict[str, list[tuple[int, float, float]]] = {}
    for t in trades:
        if t.get("status") != "filled":
            continue
        sym = t["symbol"]
        side = t["side"]
        qty = int(t["qty"])
        px = float(t["fill_price"])
        cost = float(t["cost"]["total"]) if isinstance(t.get("cost"), dict) else 0.0
        if side == "buy":
            open_lots.setdefault(sym, []).append((qty, px, cost))
        else:
            remaining = qty
            sell_cost_total = cost
            sell_qty_total = qty
            lots = open_lots.get(sym, [])
            while remaining > 0 and lots:
                lot_qty, lot_px, lot_cost = lots[0]
                used = min(remaining, lot_qty)
                portion_buy_cost = lot_cost * (used / lot_qty) if lot_qty > 0 else 0.0
                portion_sell_cost = (
                    sell_cost_total * (used / sell_qty_total) if sell_qty_total > 0 else 0.0
                )
                trip_pnl = (px - lot_px) * used - portion_buy_cost - portion_sell_cost
                pnl.append(trip_pnl)
                remaining -= used
                if used == lot_qty:
                    lots.pop(0)
                else:
                    lots[0] = (lot_qty - used, lot_px, lot_cost - portion_buy_cost)
            if not lots:
                open_lots.pop(sym, None)
    return pnl
