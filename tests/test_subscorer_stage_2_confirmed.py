"""stage_2_confirmed sub-scorer tests.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("stage_2_confirmed sub-scorer" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.subscorers.stage_2_confirmed import stage_2_confirmed


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
    return [10.0 + (90.0 * i / 251.0) for i in range(252)]


def test_all_four_conditions_score_5() -> None:
    closes = _make_uptrend_252()
    res = stage_2_confirmed(_ctx_from_close_high_low(closes))
    assert res.status == "scored"
    assert res.points == 5
    assert res.evidence["conditions_passed"] == 4


def test_ma150_flat_scores_zero() -> None:
    closes = [100.0] * 252
    res = stage_2_confirmed(_ctx_from_close_high_low(closes))
    assert res.status == "scored"
    assert res.points == 0
    assert res.evidence["cond2"] is False


def test_close_31pct_below_52w_high_scores_zero() -> None:
    closes = _make_uptrend_252()
    highs = list(closes)
    highs[100] = 200.0  # close (~100) is now <75% of 52w high (200)
    res = stage_2_confirmed(_ctx_from_close_high_low(closes, highs=highs))
    assert res.status == "scored"
    assert res.points == 0
    assert res.evidence["cond4"] is False


def test_insufficient_bars_skipped() -> None:
    closes = [float(i) for i in range(1, 201)]
    res = stage_2_confirmed(_ctx_from_close_high_low(closes))
    assert res.status == "skipped"
    assert res.points == 0
    assert res.evidence["need"] == 252
