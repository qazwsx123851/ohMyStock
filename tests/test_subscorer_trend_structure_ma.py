"""trend_structure_ma sub-scorer tests.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("trend_structure_ma sub-scorer" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.subscorers.trend_structure_ma import trend_structure_ma


def _ctx_from_closes(closes: list[float]) -> ScoringContext:
    bars = [
        {"ts": f"2026-01-{(i % 28) + 1:02d}", "o": c, "h": c, "l": c, "c": c, "v": 1000, "amount": 1000}
        for i, c in enumerate(closes)
    ]
    return ScoringContext(
        asof_date="2026-04-30",
        symbol="2330",
        bars=bars,
        three_major=[],
        margin_short=[],
    )


def test_full_uptrend_scores_10() -> None:
    closes = [float(i) for i in range(1, 121)]
    res = trend_structure_ma(_ctx_from_closes(closes))
    assert res.status == "scored"
    assert res.points == 10
    assert res.evidence["conditions_passed"] == 3
    assert res.evidence["close"] == 120.0
    assert res.evidence["ma5"] is not None
    assert res.evidence["ma20"] is not None
    assert res.evidence["ma60"] is not None


def test_close_below_ma5_scores_zero() -> None:
    closes = [float(i) for i in range(1, 120)] + [50.0]
    res = trend_structure_ma(_ctx_from_closes(closes))
    assert res.status == "scored"
    assert res.points == 0
    assert res.evidence["conditions_passed"] < 3


def test_flat_closes_score_zero() -> None:
    closes = [100.0] * 120
    res = trend_structure_ma(_ctx_from_closes(closes))
    assert res.status == "scored"
    assert res.points == 0
    assert res.evidence["conditions_passed"] == 0


def test_insufficient_bars_skipped() -> None:
    closes = [float(i) for i in range(1, 31)]
    res = trend_structure_ma(_ctx_from_closes(closes))
    assert res.status == "skipped"
    assert res.points == 0
    assert res.evidence["reason"] == "insufficient_bars"
    assert res.evidence["have"] == 30
    assert res.evidence["need"] == 60
