"""Tests for ohmystock.backtest.costs.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
"""

from __future__ import annotations

import warnings

import pytest

from ohmystock.backtest import costs
from ohmystock.backtest.costs import (
    DAYTRADE_TAX_SUNSET,
    FEE_FLOOR_TWD,
    FEE_RATE,
    TAX_RATE_DAYTRADE,
    TAX_RATE_REGULAR,
    transaction_cost,
)


def test_buy_fee_with_discount_no_tax():
    r = transaction_cost("buy", price=400.0, qty=1000, day_trade=False, fee_discount=0.28)
    assert r["fee"] == pytest.approx(159.6)
    assert r["tax"] == 0.0
    assert r["total"] == pytest.approx(159.6)


def test_fee_floor_for_tiny_order():
    r = transaction_cost("buy", price=10.0, qty=10, day_trade=False, fee_discount=0.28)
    assert r["fee"] == 20.0
    assert r["total"] == 20.0


def test_daytrade_half_rate_before_sunset():
    r = transaction_cost(
        "sell",
        price=400.0,
        qty=1000,
        day_trade=True,
        fee_discount=0.28,
        trade_date="2027-12-31",
    )
    assert r["tax"] == pytest.approx(600.0)


def test_daytrade_falls_back_after_sunset():
    costs._warned_sunset = False
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        r = transaction_cost(
            "sell",
            price=400.0,
            qty=1000,
            day_trade=True,
            fee_discount=0.28,
            trade_date="2028-01-01",
        )
        assert any(issubclass(rec.category, RuntimeWarning) for rec in w)
    assert r["tax"] == pytest.approx(1200.0)


def test_literal_constants_are_pinned():
    assert FEE_RATE == 0.001425
    assert TAX_RATE_REGULAR == 0.0030
    assert TAX_RATE_DAYTRADE == 0.0015
    assert FEE_FLOOR_TWD == 20.0
    assert DAYTRADE_TAX_SUNSET == "2027-12-31"


def test_regular_sell_tax_is_03pct():
    r = transaction_cost("sell", price=100.0, qty=1000, day_trade=False, fee_discount=0.28)
    assert r["tax"] == pytest.approx(300.0)


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        transaction_cost("hold", price=10.0, qty=1, day_trade=False)
    with pytest.raises(ValueError):
        transaction_cost("buy", price=-1.0, qty=1, day_trade=False)
    with pytest.raises(ValueError):
        transaction_cost("buy", price=1.0, qty=1, day_trade=False, fee_discount=0)
    with pytest.raises(ValueError):
        transaction_cost("buy", price=1.0, qty=1, day_trade=False, fee_discount=1.5)
