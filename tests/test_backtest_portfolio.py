"""Tests for ohmystock.backtest.portfolio.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
"""

from __future__ import annotations

import pytest

from ohmystock.backtest.portfolio import Portfolio


def _zero_cost() -> dict:
    return {"fee": 0.0, "tax": 0.0, "total": 0.0}


def test_initial_state():
    p = Portfolio.with_initial(1_000_000)
    assert p.cash == 1_000_000.0
    assert p.available_cash == 1_000_000.0
    assert p.positions == {}
    assert p.pending_settlements == {}


def test_buy_debits_both_cash_and_available_cash():
    p = Portfolio.with_initial(1_000_000)
    p.apply_buy("2330", qty=1000, fill_price=400.0, cost=_zero_cost(), fill_date="2026-04-22")
    assert p.cash == 600_000.0
    assert p.available_cash == 600_000.0
    assert p.positions == {"2330": 1000}


def test_can_afford_buy_rejects_when_available_cash_insufficient():
    p = Portfolio.with_initial(100_000)
    cost = _zero_cost()
    assert p.can_afford_buy(50.0, 1000, cost) is True
    assert p.can_afford_buy(50.0, 3000, cost) is False


def test_sell_credits_cash_and_queues_settlement():
    p = Portfolio.with_initial(0)
    p.positions["2330"] = 1000
    p.apply_sell(
        "2330",
        qty=1000,
        fill_price=400.0,
        cost=_zero_cost(),
        fill_date="2026-04-22",
        settlement_date="2026-04-26",
    )
    assert p.cash == 400_000.0
    assert p.available_cash == 0.0
    assert p.pending_settlements == {"2026-04-26": 400_000.0}
    assert p.positions == {}


def test_settlement_drains_on_settlement_day():
    p = Portfolio.with_initial(0)
    p.pending_settlements["2026-04-26"] = 100_000.0
    p.advance_to("2026-04-26")
    assert p.available_cash == 100_000.0
    assert p.pending_settlements == {}


def test_t2_scenario_spendable_at_t2_open():
    p = Portfolio.with_initial(0)
    p.positions["2330"] = 1000
    p.apply_sell(
        "2330",
        qty=1000,
        fill_price=100.0,
        cost=_zero_cost(),
        fill_date="2026-04-22",
        settlement_date="2026-04-26",
    )
    p.advance_to("2026-04-26")
    assert p.can_afford_buy(50.0, 1000, _zero_cost()) is True


def test_unsettled_proceeds_not_spendable_before_t2():
    p = Portfolio.with_initial(0)
    p.positions["2330"] = 1000
    p.apply_sell(
        "2330",
        qty=1000,
        fill_price=100.0,
        cost=_zero_cost(),
        fill_date="2026-04-22",
        settlement_date="2026-04-26",
    )
    p.advance_to("2026-04-25")
    assert p.available_cash == 0.0
    assert p.can_afford_buy(50.0, 1000, _zero_cost()) is False


def test_oversell_raises():
    p = Portfolio.with_initial(0)
    p.positions["2330"] = 500
    with pytest.raises(ValueError):
        p.apply_sell(
            "2330",
            qty=1000,
            fill_price=100.0,
            cost=_zero_cost(),
            fill_date="2026-04-22",
            settlement_date="2026-04-26",
        )


def test_view_is_a_copy_of_positions():
    p = Portfolio.with_initial(1_000_000)
    p.positions["2330"] = 1000
    v = p.view()
    v["positions"]["2330"] = 9999
    assert p.positions["2330"] == 1000
