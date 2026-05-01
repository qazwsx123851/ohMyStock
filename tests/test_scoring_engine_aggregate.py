"""Tests for score_watchlist aggregation, Risk-Off, sort, top_n.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _reset() -> None:
    import ohmystock.scoring  # noqa: F401
    from ohmystock.scoring import registry as _reg

    saved = dict(_reg._REGISTRY)
    _reg._reset_registry()
    yield
    _reg._reset_registry()
    _reg._REGISTRY.update(saved)


@pytest.fixture(autouse=True)
def _mock_data_sources():
    """Make all three data fetches return ok=True with empty rows."""

    ok_envelope = {
        "ok": True,
        "elapsed_ms": 0,
        "data": {"bars": [], "rows": []},
        "error": None,
    }

    with (
        patch(
            "ohmystock.scoring._engine.get_kline",
            return_value=ok_envelope,
        ) as mk,
        patch(
            "ohmystock.scoring._engine.get_three_major_investors",
            return_value=ok_envelope,
        ) as mt,
        patch(
            "ohmystock.scoring._engine.get_margin_short",
            return_value=ok_envelope,
        ) as mm,
    ):
        yield mk, mt, mm


def _register(
    name: str, category: str, max_pts: float, points: float, status: str = "scored"
):
    from ohmystock.scoring.models import SubScoreResult
    from ohmystock.scoring.registry import register_subscorer

    @register_subscorer(category=category, name=name, max_points=max_pts)
    def _fn(ctx) -> SubScoreResult:
        return SubScoreResult(
            name=name,
            category=category,
            points=points,
            max_points=max_pts,
            status=status,
        )


def _candidate(env: dict, symbol: str) -> dict:
    return next(c for c in env["data"]["candidates"] if c["symbol"] == symbol)


def test_sum_within_caps() -> None:
    from ohmystock.scoring import score_watchlist

    _register("t1", "technical", 30, 30)
    _register("c1", "chip", 20, 20)
    _register("f1", "fundamental", 15, 15)
    _register("s1", "sentiment", 5, 5)

    env = score_watchlist("2026-04-30", ["2330"])
    c = _candidate(env, "2330")
    assert c["tech_subtotal"] == 30
    assert c["chip_subtotal"] == 20
    assert c["fund_subtotal"] == 15
    assert c["sent_subtotal"] == 5
    assert c["final_score"] == 70


def test_category_cap_clamps_overflow() -> None:
    from ohmystock.scoring import score_watchlist

    _register("t1", "technical", 30, 25)
    _register("t2", "technical", 30, 25)
    _register("c1", "chip", 20, 20)
    _register("f1", "fundamental", 15, 15)
    _register("s1", "sentiment", 5, 5)

    env = score_watchlist("2026-04-30", ["2330"])
    c = _candidate(env, "2330")
    assert c["tech_subtotal"] == 40
    assert c["final_score"] == 80


def test_negative_category_sum_floored_to_zero() -> None:
    from ohmystock.scoring import score_watchlist

    _register("c_neg", "chip", 10, -3)  # dispatch clamps to 0
    _register("t1", "technical", 5, 5)

    env = score_watchlist("2026-04-30", ["2330"])
    c = _candidate(env, "2330")
    assert c["chip_subtotal"] >= 0
    assert c["chip_subtotal"] == 0


def test_skipped_and_error_results_not_summed() -> None:
    from ohmystock.scoring import score_watchlist

    _register("t_scored", "technical", 10, 10, status="scored")
    _register("t_skipped", "technical", 10, 0, status="skipped")
    _register("t_errored", "technical", 10, 0, status="error")

    env = score_watchlist("2026-04-30", ["2330"])
    c = _candidate(env, "2330")
    assert c["tech_subtotal"] == 10
    names = {s["name"] for s in c["subscores"]}
    assert names == {"t_scored", "t_skipped", "t_errored"}


def test_subscorer_raising_becomes_error_status() -> None:
    from ohmystock.scoring.models import SubScoreResult
    from ohmystock.scoring.registry import register_subscorer

    @register_subscorer(category="technical", name="boomer", max_points=5)
    def _fn(ctx) -> SubScoreResult:
        raise RuntimeError("boom")

    from ohmystock.scoring import score_watchlist

    env = score_watchlist("2026-04-30", ["2330"])
    c = _candidate(env, "2330")
    boomer = next(s for s in c["subscores"] if s["name"] == "boomer")
    assert boomer["status"] == "error"
    assert boomer["points"] == 0
    assert "boom" in boomer["error_message"]


def test_risk_off_resolver_called_once_per_batch() -> None:
    from ohmystock.scoring import score_watchlist

    calls = []

    def _resolver() -> bool:
        calls.append(True)
        return False

    _register("t1", "technical", 10, 5)
    score_watchlist(
        "2026-04-30",
        ["2330", "2317", "2454", "2412", "1101"],
        risk_off_resolver=_resolver,
    )
    assert len(calls) == 1


def test_risk_off_off_score_70_classifies_green() -> None:
    from ohmystock.scoring import score_watchlist

    _register("t1", "technical", 30, 30)
    _register("c1", "chip", 20, 20)
    _register("f1", "fundamental", 15, 15)
    _register("s1", "sentiment", 5, 5)

    env = score_watchlist("2026-04-30", ["2330"], risk_off_resolver=lambda: False)
    c = _candidate(env, "2330")
    assert c["final_score"] == 70
    assert c["risk_off_applied"] is False
    assert c["classification"] == "green"


def test_risk_off_on_score_70_capped_to_50_yellow() -> None:
    from ohmystock.scoring import score_watchlist

    _register("t1", "technical", 30, 30)
    _register("c1", "chip", 20, 20)
    _register("f1", "fundamental", 15, 15)
    _register("s1", "sentiment", 5, 5)

    env = score_watchlist("2026-04-30", ["2330"], risk_off_resolver=lambda: True)
    c = _candidate(env, "2330")
    assert c["final_score"] == 50
    assert c["risk_off_applied"] is True
    assert c["classification"] == "yellow"


def test_risk_off_on_score_30_unchanged_red() -> None:
    from ohmystock.scoring import score_watchlist

    _register("t1", "technical", 30, 30)

    env = score_watchlist("2026-04-30", ["2330"], risk_off_resolver=lambda: True)
    c = _candidate(env, "2330")
    assert c["final_score"] == 30
    assert c["risk_off_applied"] is True
    assert c["classification"] == "red"


def test_tie_break_by_symbol_asc() -> None:
    from ohmystock.scoring import score_watchlist

    _register("t1", "technical", 60, 60)

    env = score_watchlist("2026-04-30", ["2330", "2317"])
    syms = [c["symbol"] for c in env["data"]["candidates"]]
    assert syms == ["2317", "2330"]


def test_top_n_truncates_after_sort() -> None:
    from ohmystock.scoring import score_watchlist

    _register("t1", "technical", 40, 40)

    env = score_watchlist(
        "2026-04-30", ["2330", "2317", "2454", "2412", "1101"], top_n=2
    )
    assert len(env["data"]["candidates"]) == 2


def test_top_n_none_returns_all() -> None:
    from ohmystock.scoring import score_watchlist

    _register("t1", "technical", 10, 10)

    env = score_watchlist(
        "2026-04-30",
        ["2330", "2317", "2454", "2412", "1101"],
        top_n=None,
    )
    assert len(env["data"]["candidates"]) == 5
