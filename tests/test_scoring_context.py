"""Tests for ScoringContext dataclass.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
"""

from __future__ import annotations

import dataclasses

import pytest


def test_scoring_context_construction() -> None:
    from ohmystock.scoring.context import ScoringContext

    ctx = ScoringContext(
        asof_date="2026-04-30",
        symbol="2330",
        bars=[],
        three_major=[],
        margin_short=[],
    )
    assert ctx.asof_date == "2026-04-30"
    assert ctx.symbol == "2330"
    assert ctx.bars == []
    assert ctx.three_major == []
    assert ctx.margin_short == []


def test_scoring_context_is_frozen() -> None:
    from ohmystock.scoring.context import ScoringContext

    ctx = ScoringContext(
        asof_date="2026-04-30",
        symbol="2330",
        bars=[],
        three_major=[],
        margin_short=[],
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.symbol = "9999"  # type: ignore[misc]


def test_scoring_context_holds_lists_of_dicts() -> None:
    from ohmystock.scoring.context import ScoringContext

    bars = [{"date": "2026-04-30", "close": 100.0}]
    chip = [{"date": "2026-04-30", "foreign_net": 1000}]
    margin = [{"date": "2026-04-30", "margin_balance": 5000}]
    ctx = ScoringContext(
        asof_date="2026-04-30",
        symbol="2330",
        bars=bars,
        three_major=chip,
        margin_short=margin,
    )
    assert ctx.bars[0]["close"] == 100.0
    assert ctx.three_major[0]["foreign_net"] == 1000
    assert ctx.margin_short[0]["margin_balance"] == 5000
