"""trend_template_8 sub-scorer tests.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("trend_template_8 sub-scorer" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.subscorers.trend_template_8 import trend_template_8


def _ctx_from_close_high_low(
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> ScoringContext:
    if highs is None:
        highs = list(closes)
    if lows is None:
        lows = list(closes)
    bars = [
        {
            "ts": f"2025-01-{(i % 28) + 1:02d}",
            "o": closes[i],
            "h": highs[i],
            "l": lows[i],
            "c": closes[i],
            "v": 1000,
            "amount": 1000,
        }
        for i in range(len(closes))
    ]
    return ScoringContext(
        asof_date="2026-04-30",
        symbol="2330",
        bars=bars,
        three_major=[],
        margin_short=[],
    )


def _make_uptrend_252() -> list[float]:
    # Linear uptrend: closes go from 10 to 100 over 252 bars.
    return [10.0 + (90.0 * i / 251.0) for i in range(252)]


def test_all_seven_conditions_score_5() -> None:
    closes = _make_uptrend_252()
    res = trend_template_8(_ctx_from_close_high_low(closes))
    assert res.status == "scored"
    assert res.points == 5
    assert res.evidence["conditions_passed"] == 7
    assert res.evidence["of"] == 7


def test_close_far_below_52w_high_scores_zero() -> None:
    # Uptrending closes, but a single prior bar had a huge high — leaves close
    # below 75% of the 52w high while every other SEPA condition still holds.
    closes = _make_uptrend_252()
    highs = list(closes)
    highs[100] = 200.0
    res = trend_template_8(_ctx_from_close_high_low(closes, highs=highs))
    assert res.status == "scored"
    assert res.points == 0
    assert res.evidence["conditions_passed"] == 6
    assert res.evidence["cond7"] is False


def test_ma200_flat_scores_zero() -> None:
    # All closes flat — 200-MA does not rise (cond3 fails).
    closes = [100.0] * 252
    res = trend_template_8(_ctx_from_close_high_low(closes))
    assert res.status == "scored"
    assert res.points == 0
    assert res.evidence["cond3"] is False


def test_insufficient_bars_skipped() -> None:
    closes = [float(i) for i in range(1, 101)]
    res = trend_template_8(_ctx_from_close_high_low(closes))
    assert res.status == "skipped"
    assert res.points == 0
    assert res.evidence["have"] == 100
    assert res.evidence["need"] == 252
