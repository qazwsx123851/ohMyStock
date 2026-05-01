"""volume_breakout_obv sub-scorer tests.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("volume_breakout_obv sub-scorer" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.subscorers.volume_breakout_obv import volume_breakout_obv


def _make_bars(
    closes: list[float],
    highs: list[float] | None = None,
    volumes: list[int] | None = None,
) -> list[dict]:
    if highs is None:
        highs = list(closes)
    if volumes is None:
        volumes = [1000] * len(closes)
    return [
        {
            "ts": f"2026-01-{(i % 28) + 1:02d}",
            "o": closes[i],
            "h": highs[i],
            "l": closes[i],
            "c": closes[i],
            "v": volumes[i],
            "amount": int(closes[i] * volumes[i]),
        }
        for i in range(len(closes))
    ]


def _ctx(bars: list[dict]) -> ScoringContext:
    return ScoringContext(
        asof_date="2026-04-30",
        symbol="2330",
        bars=bars,
        three_major=[],
        margin_short=[],
    )


def test_breakout_volume_and_obv_score_5() -> None:
    # Closes climb from 100 to 119 over first 20 bars, then breakout to 130.
    closes = [100.0 + i for i in range(20)] + [130.0]
    highs = list(closes)
    volumes = [1000] * 20 + [1500]  # 1.5× avg
    res = volume_breakout_obv(_ctx(_make_bars(closes, highs=highs, volumes=volumes)))
    assert res.status == "scored"
    assert res.points == 5
    assert res.evidence["conditions_passed"] == 3


def test_breakout_low_volume_scores_zero() -> None:
    closes = [100.0 + i for i in range(20)] + [130.0]
    volumes = [1000] * 20 + [1000]  # 1.0× avg, below 1.4× threshold
    res = volume_breakout_obv(_ctx(_make_bars(closes, volumes=volumes)))
    assert res.status == "scored"
    assert res.points == 0
    assert res.evidence["volume_ratio"] < 1.4


def test_no_breakout_scores_zero() -> None:
    # 20-day high is 119; close stays at 115 (below high).
    closes = [100.0 + i for i in range(20)] + [115.0]
    volumes = [1000] * 20 + [1500]
    res = volume_breakout_obv(_ctx(_make_bars(closes, volumes=volumes)))
    assert res.status == "scored"
    assert res.points == 0
    assert res.evidence["breakout"] is False


def test_obv_slope_negative_scores_zero() -> None:
    # Recent 5 bars show declining closes (negative OBV slope), then breakout via high.
    closes = (
        [50.0] * 15
        + [60.0, 59.0, 58.0, 57.0, 56.0]   # last 5 bars decline → OBV slope ≤ 0
        + [70.0]                           # final breakout above 20-day high
    )
    highs = list(closes)
    volumes = [1000] * 20 + [1500]
    res = volume_breakout_obv(_ctx(_make_bars(closes, highs=highs, volumes=volumes)))
    assert res.status == "scored"
    assert res.evidence["obv_slope_5d"] <= 0
    assert res.points == 0


def test_insufficient_bars_skipped() -> None:
    closes = [100.0 + i for i in range(10)]
    res = volume_breakout_obv(_ctx(_make_bars(closes)))
    assert res.status == "skipped"
    assert res.points == 0
