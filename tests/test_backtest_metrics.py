"""Tests for ohmystock.backtest.metrics.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from ohmystock.backtest.metrics import compute_metrics


def _flat_curve(n: int = 60, equity: float = 1_000_000.0) -> list[dict]:
    start = date(2026, 4, 1)
    return [
        {"date": (start + timedelta(days=i)).isoformat(), "equity": equity}
        for i in range(n)
    ]


def test_flat_equity_zeros():
    curve = _flat_curve(60)
    m = compute_metrics(curve, [], initial_capital=1_000_000.0)
    assert m["total_return"] == 0.0
    assert m["sharpe"] == 0.0
    assert m["sortino"] == 0.0
    assert m["max_drawdown"] == 0.0
    assert m["mdd_duration_days"] == 0
    assert m["total_trades"] == 0
    assert m["win_rate"] == 0.0
    assert m["profit_factor"] == 0.0
    assert curve[-1]["equity"] == 1_000_000.0


def test_single_winning_round_trip():
    start = date(2026, 4, 1)
    n = 30
    curve = [
        {"date": (start + timedelta(days=i)).isoformat(), "equity": 1_000_000.0 + i * 2000.0}
        for i in range(n)
    ]
    trades = [
        {
            "symbol": "TEST",
            "signal_date": "2026-04-01",
            "fill_date": "2026-04-02",
            "side": "buy",
            "qty": 1000,
            "fill_price": 400.0,
            "cost": {"fee": 159.6, "tax": 0.0, "total": 159.6},
            "status": "filled",
        },
        {
            "symbol": "TEST",
            "signal_date": "2026-04-29",
            "fill_date": "2026-04-30",
            "side": "sell",
            "qty": 1000,
            "fill_price": 460.0,
            "cost": {"fee": 183.5, "tax": 1380.0, "total": 1563.5},
            "status": "filled",
        },
    ]
    m = compute_metrics(curve, trades, initial_capital=1_000_000.0)
    assert m["total_trades"] == 1
    assert m["win_rate"] == 1.0
    assert m["profit_factor"] == float("inf")
    assert m["total_return"] > 0
    assert m["expectancy"] > 0


def test_no_winning_trades_profit_factor_zero():
    start = date(2026, 4, 1)
    curve = [
        {"date": (start + timedelta(days=i)).isoformat(), "equity": 1_000_000.0 - i * 100}
        for i in range(10)
    ]
    trades = [
        {
            "symbol": "T",
            "signal_date": "2026-04-01",
            "fill_date": "2026-04-02",
            "side": "buy",
            "qty": 100,
            "fill_price": 100.0,
            "cost": {"fee": 20.0, "tax": 0.0, "total": 20.0},
            "status": "filled",
        },
        {
            "symbol": "T",
            "signal_date": "2026-04-04",
            "fill_date": "2026-04-05",
            "side": "sell",
            "qty": 100,
            "fill_price": 90.0,
            "cost": {"fee": 20.0, "tax": 27.0, "total": 47.0},
            "status": "filled",
        },
    ]
    m = compute_metrics(curve, trades, initial_capital=1_000_000.0)
    assert m["total_trades"] == 1
    assert m["win_rate"] == 0.0
    assert m["profit_factor"] == 0.0


def test_sharpe_finite_with_volatility():
    start = date(2026, 4, 1)
    eq = 1_000_000.0
    pts = []
    for i in range(40):
        eq *= 1.01 if i % 2 == 0 else 0.995
        pts.append({"date": (start + timedelta(days=i)).isoformat(), "equity": eq})
    m = compute_metrics(pts, [], initial_capital=1_000_000.0)
    assert math.isfinite(m["sharpe"])
    assert math.isfinite(m["sortino"])
    assert m["max_drawdown"] <= 0.0
