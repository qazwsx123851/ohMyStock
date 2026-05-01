"""Tests for sub-scorer registry contract.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
("Sub-scorer registry contract" requirement).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset() -> None:
    # Trigger placeholder registration first, then save+restore around the test.
    import ohmystock.scoring  # noqa: F401
    from ohmystock.scoring import registry as _reg

    saved = dict(_reg._REGISTRY)
    _reg._reset_registry()
    yield
    _reg._reset_registry()
    _reg._REGISTRY.update(saved)


def _make_ctx():
    from ohmystock.scoring.context import ScoringContext

    return ScoringContext(
        asof_date="2026-04-30",
        symbol="2330",
        bars=[],
        three_major=[],
        margin_short=[],
    )


def test_decorator_registers_subscorer() -> None:
    from ohmystock.scoring.models import SubScoreResult
    from ohmystock.scoring.registry import list_subscorers, register_subscorer

    @register_subscorer(category="technical", name="trend_template", max_points=5)
    def _fn(ctx) -> SubScoreResult:
        return SubScoreResult(
            name="trend_template",
            category="technical",
            points=5,
            max_points=5,
            status="scored",
        )

    metas = list_subscorers()
    assert ("trend_template", "technical", 5) in metas


def test_duplicate_registration_raises_value_error() -> None:
    from ohmystock.scoring.models import SubScoreResult
    from ohmystock.scoring.registry import register_subscorer

    @register_subscorer(category="technical", name="dup", max_points=3)
    def _fn1(ctx) -> SubScoreResult:
        return SubScoreResult(
            name="dup", category="technical", points=0, max_points=3, status="scored"
        )

    with pytest.raises(ValueError, match="already registered"):

        @register_subscorer(category="technical", name="dup", max_points=3)
        def _fn2(ctx) -> SubScoreResult:
            return SubScoreResult(
                name="dup",
                category="technical",
                points=0,
                max_points=3,
                status="scored",
            )


def test_dispatch_invokes_function() -> None:
    from ohmystock.scoring.models import SubScoreResult
    from ohmystock.scoring.registry import dispatch, register_subscorer

    calls: list = []

    @register_subscorer(category="technical", name="trend", max_points=5)
    def _fn(ctx) -> SubScoreResult:
        calls.append(ctx.symbol)
        return SubScoreResult(
            name="trend", category="technical", points=3, max_points=5, status="scored"
        )

    result = dispatch("trend", _make_ctx())
    assert calls == ["2330"]
    assert result.points == 3


def test_dispatch_overwrites_metadata_from_registry() -> None:
    from ohmystock.scoring.models import SubScoreResult
    from ohmystock.scoring.registry import dispatch, register_subscorer

    @register_subscorer(category="technical", name="rs_pct", max_points=7)
    def _fn(ctx) -> SubScoreResult:
        # Liar return: claims wrong name/category/max_points and over-max points
        return SubScoreResult(
            name="WRONG",
            category="chip",
            points=20,
            max_points=99,
            status="scored",
        )

    result = dispatch("rs_pct", _make_ctx())
    assert result.name == "rs_pct"
    assert result.category == "technical"
    assert result.max_points == 7
    assert result.points == 7  # clamped from 20 to max 7


def test_dispatch_clamps_negative_points_to_zero() -> None:
    from ohmystock.scoring.models import SubScoreResult
    from ohmystock.scoring.registry import dispatch, register_subscorer

    @register_subscorer(category="chip", name="borrow", max_points=2)
    def _fn(ctx) -> SubScoreResult:
        return SubScoreResult(
            name="borrow", category="chip", points=-5, max_points=2, status="scored"
        )

    result = dispatch("borrow", _make_ctx())
    assert result.points == 0


def test_list_subscorers_alphabetical() -> None:
    from ohmystock.scoring.models import SubScoreResult
    from ohmystock.scoring.registry import list_subscorers, register_subscorer

    def _make(n: str):
        @register_subscorer(category="technical", name=n, max_points=1)
        def _fn(ctx) -> SubScoreResult:
            return SubScoreResult(
                name=n, category="technical", points=0, max_points=1, status="scored"
            )

    _make("b_subscorer")
    _make("a_subscorer")
    _make("c_subscorer")

    names = [m[0] for m in list_subscorers()]
    assert names == ["a_subscorer", "b_subscorer", "c_subscorer"]


def test_reset_registry_clears_state() -> None:
    from ohmystock.scoring.models import SubScoreResult
    from ohmystock.scoring.registry import (
        _reset_registry,
        list_subscorers,
        register_subscorer,
    )

    @register_subscorer(category="technical", name="x", max_points=1)
    def _fn(ctx) -> SubScoreResult:
        return SubScoreResult(
            name="x", category="technical", points=0, max_points=1, status="scored"
        )

    assert list_subscorers() != []
    _reset_registry()
    assert list_subscorers() == []


def test_dispatch_missing_name_raises_key_error() -> None:
    from ohmystock.scoring.registry import dispatch

    with pytest.raises(KeyError):
        dispatch("nonexistent", _make_ctx())
