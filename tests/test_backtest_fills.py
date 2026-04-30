"""Tests for ohmystock.backtest.fills.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
"""

from __future__ import annotations

import pytest

from ohmystock.backtest.fills import compute_fill


def _bar(ts: str, o: float, c: float | None = None) -> dict:
    c = o if c is None else c
    return {"ts": ts, "o": o, "h": o, "l": o, "c": c, "v": 0, "amount": 0}


def _order(side: str) -> dict:
    return {
        "symbol": "2330",
        "side": side,
        "qty": 1000,
        "order_type": "market",
        "limit_price": None,
    }


def test_buy_rejected_at_limit_up():
    bar = _bar("2026-04-22", 110.0)
    r = compute_fill(_order("buy"), bar, prev_close=100.0, slippage_bps=30)
    assert r["status"] == "rejected_limit_up"
    assert r["fill_price"] is None


def test_sell_fills_with_1pct_slippage_at_limit_up():
    bar = _bar("2026-04-22", 110.0)
    r = compute_fill(_order("sell"), bar, prev_close=100.0, slippage_bps=30)
    assert r["status"] == "filled"
    assert r["fill_price"] == pytest.approx(110.0 * (1 - 0.010))


def test_sell_rejected_at_limit_down():
    bar = _bar("2026-04-22", 90.0)
    r = compute_fill(_order("sell"), bar, prev_close=100.0, slippage_bps=30)
    assert r["status"] == "rejected_limit_down"
    assert r["fill_price"] is None


def test_buy_fills_with_1pct_slippage_at_limit_down():
    bar = _bar("2026-04-22", 90.0)
    r = compute_fill(_order("buy"), bar, prev_close=100.0, slippage_bps=30)
    assert r["status"] == "filled"
    assert r["fill_price"] == pytest.approx(90.0 * (1 + 0.010))


def test_standard_slippage_buy():
    bar = _bar("2026-04-22", 100.0)
    r = compute_fill(_order("buy"), bar, prev_close=99.0, slippage_bps=30)
    assert r["status"] == "filled"
    assert r["fill_price"] == pytest.approx(100.0 * 1.003)


def test_standard_slippage_sell():
    bar = _bar("2026-04-22", 100.0)
    r = compute_fill(_order("sell"), bar, prev_close=99.0, slippage_bps=30)
    assert r["status"] == "filled"
    assert r["fill_price"] == pytest.approx(100.0 * 0.997)


def test_no_prev_close_uses_standard_slippage():
    bar = _bar("2026-04-22", 100.0)
    r = compute_fill(_order("buy"), bar, prev_close=None, slippage_bps=30)
    assert r["status"] == "filled"
    assert r["fill_price"] == pytest.approx(100.3)
