"""Tests for ohmystock.backtest.engine.run_backtest.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from ohmystock.backtest import run_backtest
from ohmystock.backtest.strategy.sma_cross import SmaCross
from tests._strategies import BuyAndHold, BuyEveryBar, NoIndicators, RaisingStrategy


def _bars(prices: list[float], start: str = "2026-04-01") -> list[dict]:
    y, m, d = (int(p) for p in start.split("-"))
    base = date(y, m, d)
    return [
        {
            "ts": (base + timedelta(days=i)).isoformat(),
            "o": float(p),
            "h": float(p) * 1.01,
            "l": float(p) * 0.99,
            "c": float(p),
            "v": 1000,
            "amount": int(p * 1000),
        }
        for i, p in enumerate(prices)
    ]


def _rising_bars(n: int = 30, start_price: float = 100.0, step: float = 1.0) -> list[dict]:
    return _bars([start_price + i * step for i in range(n)])


def test_success_envelope_shape():
    bars = _rising_bars(20)
    result = run_backtest(
        BuyAndHold("2330", qty=100),
        {"2330": bars},
        period={"from": "2026-04-01", "to": "2026-04-28"},
        initial_capital=1_000_000,
    )
    assert result["ok"] is True
    assert result["error"] is None
    assert isinstance(result["elapsed_ms"], int)
    assert "metrics" in result["data"]
    assert "trades" in result["data"]
    assert "equity_curve" in result["data"]
    assert len(result["data"]["equity_curve"]) >= 1


def test_strategy_raising_returns_internal_error():
    bars = _rising_bars(10)
    result = run_backtest(
        RaisingStrategy(),
        {"2330": bars},
        period={"from": "2026-04-01", "to": "2026-04-30"},
        initial_capital=1_000_000,
    )
    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == "INTERNAL_ERROR"
    assert result["error"]["retriable"] is False


def test_last_bar_orders_cancelled_eob():
    bars = _rising_bars(5)
    result = run_backtest(
        BuyEveryBar("2330", qty=10),
        {"2330": bars},
        period={"from": "2026-04-01", "to": "2026-04-30"},
        initial_capital=1_000_000,
    )
    assert result["ok"] is True
    cancelled = [t for t in result["data"]["trades"] if t["status"] == "cancelled_eob"]
    assert len(cancelled) >= 1
    assert cancelled[-1]["signal_date"] == bars[-1]["ts"]


def test_same_bar_fill_impossible():
    bars = _rising_bars(15)
    result = run_backtest(
        BuyAndHold("2330", qty=100),
        {"2330": bars},
        period={"from": "2026-04-01", "to": "2026-04-30"},
        initial_capital=1_000_000,
    )
    assert result["ok"] is True
    for t in result["data"]["trades"]:
        if t["status"] == "filled":
            assert t["fill_date"] > t["signal_date"]


def test_strategy_without_required_indicators_runs():
    bars = _rising_bars(10)
    result = run_backtest(
        NoIndicators(),
        {"2330": bars},
        period={"from": "2026-04-01", "to": "2026-04-30"},
        initial_capital=1_000_000,
    )
    assert result["ok"] is True


def test_sma_cross_importable_and_usable():
    bars = _bars([100, 101, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90,
                  91, 92, 93, 94, 95, 96, 97, 98,
                  99, 100, 101, 102, 103, 104, 105, 106, 107, 108])
    result = run_backtest(
        SmaCross(fast=5, slow=20, qty=100),
        {"2330": bars},
        period={"from": "2026-04-01", "to": "2026-04-30"},
        initial_capital=1_000_000,
    )
    assert result["ok"] is True
    assert isinstance(result["data"]["trades"], list)


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        (
            {"bars_by_symbol": {"2330": []}, "period": {"from": "2026-04-01", "to": "2026-04-28"}},
            "INVALID_INPUT",
        ),
        (
            {
                "bars_by_symbol": {"2330": _rising_bars(5)},
                "period": {"from": "2026-04-28", "to": "2026-04-01"},
            },
            "INVALID_INPUT",
        ),
        (
            {
                "bars_by_symbol": {
                    "2330": [
                        {"ts": "2026-04-01", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1, "amount": 1},
                        {"ts": "2026-04-01", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1, "amount": 1},
                    ]
                },
                "period": {"from": "2026-04-01", "to": "2026-04-30"},
            },
            "INVALID_INPUT",
        ),
        (
            {
                "bars_by_symbol": {"2330": _rising_bars(5)},
                "period": {"from": "2026-04-01", "to": "2026-04-30"},
                "initial_capital": 0,
            },
            "INVALID_INPUT",
        ),
        (
            {
                "bars_by_symbol": {"2330": _rising_bars(5)},
                "period": {"from": "2026-04-01", "to": "2026-04-30"},
                "fee_discount": 1.5,
            },
            "INVALID_INPUT",
        ),
        (
            {
                "bars_by_symbol": {"2330": _rising_bars(5)},
                "period": {"from": "2026-04-01", "to": "2026-04-30"},
                "slippage_bps": -5,
            },
            "INVALID_INPUT",
        ),
    ],
)
def test_input_validation(kwargs, expected):
    base = {
        "initial_capital": 1_000_000,
        "fee_discount": 0.28,
        "slippage_bps": 30,
    }
    base.update(kwargs)
    result = run_backtest(BuyAndHold("2330"), **base)
    assert result["ok"] is False
    assert result["error"]["code"] == expected
