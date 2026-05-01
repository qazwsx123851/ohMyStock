"""Tests for ``ohmystock.decider._pricing``."""

from __future__ import annotations

import math

import pytest

from ohmystock.decider._pricing import (
    MODEL_PRICING_USD_PER_MTOK,
    compute_cost_usd,
)


def test_table_contains_three_production_models() -> None:
    assert set(MODEL_PRICING_USD_PER_MTOK) >= {
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
    }


def test_opus_cost_exact() -> None:
    cost = compute_cost_usd("claude-opus-4-7", 18420, 1240)
    expected = 18420 / 1_000_000.0 * 15.0 + 1240 / 1_000_000.0 * 75.0
    assert math.isclose(cost, expected, rel_tol=0, abs_tol=1e-9)
    assert math.isclose(cost, 0.36930, rel_tol=0, abs_tol=1e-9)


def test_sonnet_cost() -> None:
    cost = compute_cost_usd("claude-sonnet-4-6", 1_000_000, 0)
    assert math.isclose(cost, 3.0, abs_tol=1e-9)


def test_haiku_cost_zero_tokens() -> None:
    assert compute_cost_usd("claude-haiku-4-5", 0, 0) == 0.0


def test_unknown_model_raises_keyerror() -> None:
    with pytest.raises(KeyError) as exc_info:
        compute_cost_usd("claude-fake-99", 100, 50)
    assert "claude-fake-99" in str(exc_info.value)
