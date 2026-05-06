"""rs_percentile sub-scorer tests.

After Decision 6 (openspec/changes/rs-percentile-skill/design.md) the sub-scorer
delegates to ``ohmystock.sepa.rs.compute_rs_rating`` instead of computing its
own IBD-weighted return against a seed universe. Tests monkey-patch the
delegate to drive each ``rs_rating -> points`` band.
"""

from __future__ import annotations

import pytest

import ohmystock.scoring.subscorers.rs_percentile as subscorer_mod
from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.subscorers.rs_percentile import rs_percentile


def _ctx(symbol: str = "2330") -> ScoringContext:
    return ScoringContext(
        asof_date="2026-04-30",
        symbol=symbol,
        bars=[],  # unused now — sub-scorer no longer reads bars
        three_major=[],
        margin_short=[],
    )


def _patch_rating(monkeypatch: pytest.MonkeyPatch, rating: int | None) -> None:
    monkeypatch.setattr(
        subscorer_mod, "compute_rs_rating", lambda symbol, asof: rating
    )


# ---------------------------------------------------------------------------
# Threshold-band mapping (the spec contract this sub-scorer owns)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rating, expected_points",
    [
        (1, 0.0),
        (50, 0.0),
        (64, 0.0),
        (65, 3.0),
        (79, 3.0),
        (80, 5.0),
        (89, 5.0),
        (90, 7.0),
        (99, 7.0),
    ],
)
def test_threshold_bands(
    monkeypatch: pytest.MonkeyPatch, rating: int, expected_points: float
) -> None:
    _patch_rating(monkeypatch, rating)
    res = rs_percentile(_ctx())
    assert res.status == "scored"
    assert res.points == expected_points
    assert res.evidence["rs_percentile"] == rating


def test_below_threshold_scores_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_rating(monkeypatch, 64)
    res = rs_percentile(_ctx())
    assert res.status == "scored"
    assert res.points == 0.0


# ---------------------------------------------------------------------------
# None handling — ineligible symbol
# ---------------------------------------------------------------------------


def test_none_rating_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_rating(monkeypatch, None)
    res = rs_percentile(_ctx("9999"))
    assert res.status == "skipped"
    assert res.points == 0.0
    assert res.evidence["reason"] == "rs_rating_unavailable"
    assert res.evidence["symbol"] == "9999"


# ---------------------------------------------------------------------------
# Delegate is called with the context's symbol + asof
# ---------------------------------------------------------------------------


def test_delegate_receives_symbol_and_asof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _spy(symbol: str, asof: object) -> int:
        captured["symbol"] = symbol
        captured["asof"] = asof
        return 90

    monkeypatch.setattr(subscorer_mod, "compute_rs_rating", _spy)
    rs_percentile(_ctx("2454"))
    assert captured == {"symbol": "2454", "asof": "2026-04-30"}


# ---------------------------------------------------------------------------
# Result shape sanity
# ---------------------------------------------------------------------------


def test_result_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_rating(monkeypatch, 85)
    res = rs_percentile(_ctx())
    assert res.name == "rs_percentile"
    assert res.category == "technical"
    assert res.max_points == 7.0
