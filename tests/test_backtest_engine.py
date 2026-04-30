"""Tests for ohmystock.backtest.engine.run_backtest.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from ohmystock.backtest import run_backtest
from ohmystock.backtest.strategy.sma_cross import SmaCross
from tests._strategies import BuyAndHold, BuyEveryBar, NoIndicators, RaisingStrategy


class RoundTripThenRebuy:
    name = "round_trip_then_rebuy"

    def warmup_bars(self) -> int:
        return 0

    def on_bar(self, ctx) -> list[dict]:
        if ctx.date == "2026-04-01":
            return [_intent("2330", "buy", 1000)]
        if ctx.date == "2026-04-02" and ctx.portfolio["positions"].get("2330", 0):
            return [_intent("2330", "sell", 1000)]
        if ctx.date == "2026-04-04":
            return [_intent("2330", "buy", 1000)]
        return []


def _intent(symbol: str, side: str, qty: int) -> dict:
    return {
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "order_type": "market",
        "limit_price": None,
    }


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


def test_period_clips_bars_and_signals_outside_range():
    bars = [
        {"ts": "2026-03-31", "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.0, "v": 1, "amount": 1},
        {"ts": "2026-04-01", "o": 101.0, "h": 102.0, "l": 100.0, "c": 101.0, "v": 1, "amount": 1},
        {"ts": "2026-04-02", "o": 102.0, "h": 103.0, "l": 101.0, "c": 102.0, "v": 1, "amount": 1},
        {"ts": "2026-05-01", "o": 120.0, "h": 121.0, "l": 119.0, "c": 120.0, "v": 1, "amount": 1},
    ]

    result = run_backtest(
        BuyEveryBar("2330", qty=1),
        {"2330": bars},
        period={"from": "2026-04-01", "to": "2026-04-02"},
        initial_capital=100_000,
    )

    assert result["ok"] is True
    assert [pt["date"] for pt in result["data"]["equity_curve"]] == [
        "2026-04-01",
        "2026-04-02",
    ]
    assert {t["signal_date"] for t in result["data"]["trades"]} == {
        "2026-04-01",
        "2026-04-02",
    }
    assert all(t["fill_date"] in {"2026-04-02", None} for t in result["data"]["trades"])


def test_period_with_no_bars_after_clipping_is_invalid():
    result = run_backtest(
        BuyAndHold("2330", qty=1),
        {"2330": _rising_bars(3, start_price=100.0)},
        period={"from": "2026-05-01", "to": "2026-05-31"},
        initial_capital=100_000,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


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


def test_sell_proceeds_are_available_on_t2_open():
    bars = _bars([100.0, 100.0, 100.0, 100.0, 100.0])
    result = run_backtest(
        RoundTripThenRebuy(),
        {"2330": bars},
        period={"from": "2026-04-01", "to": "2026-04-05"},
        initial_capital=110_000,
        fee_discount=0.28,
        slippage_bps=0,
    )

    assert result["ok"] is True
    trades = result["data"]["trades"]
    assert [(t["side"], t["fill_date"], t["status"]) for t in trades] == [
        ("buy", "2026-04-02", "filled"),
        ("sell", "2026-04-03", "filled"),
        ("buy", "2026-04-05", "filled"),
    ]


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
