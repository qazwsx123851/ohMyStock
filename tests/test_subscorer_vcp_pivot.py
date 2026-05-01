"""vcp_pivot sub-scorer tests.

Spec: openspec/changes/phase-2b-sepa-subscorers/specs/phase-2b-scoring-engine/spec.md
("vcp_pivot sub-scorer (real implementation)" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.subscorers.vcp_pivot import vcp_pivot


def _ctx_from_ohlcv(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
) -> ScoringContext:
    bars = [
        {
            "ts": f"2025-01-{(i % 28) + 1:02d}",
            "o": closes[i],
            "h": highs[i],
            "l": lows[i],
            "c": closes[i],
            "v": volumes[i],
            "amount": volumes[i] * closes[i],
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


def test_insufficient_bars_skipped() -> None:
    closes = [100.0] * 30
    res = vcp_pivot(_ctx_from_ohlcv(closes, closes, closes, [1000.0] * 30))
    assert res.status == "skipped"
    assert res.points == 0
    assert res.evidence["reason"] == "insufficient_bars"
    assert res.evidence["have"] == 30
    assert res.evidence["need"] == 60


def test_breakout_awards_eight_points() -> None:
    n = 60
    closes = [100.0 + (i % 2) * 0.5 for i in range(n - 1)] + [110.0]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    volumes = [1000.0] * (n - 1) + [2000.0]
    res = vcp_pivot(_ctx_from_ohlcv(closes, highs, lows, volumes))
    assert res.status == "scored"
    assert res.evidence["vcp_quality"] == "breakout"
    assert res.points == 8
    pivot = res.evidence["pivot_price"]
    assert isinstance(pivot, float)
    assert pivot > 0
    expected_pivot = max(highs[-20:-1])
    assert pivot == expected_pivot
    assert res.evidence["volume_ratio"] is not None
    assert res.evidence["volume_ratio"] >= 1.4


def test_textbook_with_two_contractions_scores_six() -> None:
    n = 60
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    base_floor = 100.0
    for i in range(40):
        if i == 5:
            h = 120.0
        elif i == 15:
            h = 115.0
        elif i == 25:
            h = 110.0
        elif i == 35:
            h = 105.0
        else:
            h = base_floor + (i % 3) * 0.1
        highs.append(h)
        lows.append(h - 0.5)
        closes.append(h - 0.25)
    for i in range(40, 60):
        c = 101.0 + ((i - 40) % 4) * 0.25
        closes.append(c)
        highs.append(c + 0.25)
        lows.append(c - 0.25)
    volumes = [1000.0] * n
    res = vcp_pivot(_ctx_from_ohlcv(closes, highs, lows, volumes))
    assert res.status == "scored"
    assert res.evidence["contractions"] >= 2, res.evidence
    assert res.evidence["range_pct"] < 0.10
    assert res.evidence["vcp_quality"] == "textbook"
    assert res.points == 6
    expected_pivot = max(highs[-20:])
    assert res.evidence["pivot_price"] == expected_pivot


def test_forming_loose_base_scores_three() -> None:
    n = 60
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    for i in range(40):
        closes.append(95.0 + (i % 5) * 0.2)
        highs.append(closes[-1] + 0.2)
        lows.append(closes[-1] - 0.2)
    for i in range(20):
        c = 100.0 + i * (12.0 / 19.0)
        closes.append(c)
        highs.append(c + 0.2)
        lows.append(c - 0.2)
    volumes = [1000.0] * n
    res = vcp_pivot(_ctx_from_ohlcv(closes, highs, lows, volumes))
    assert res.status == "scored"
    assert 0.10 <= res.evidence["range_pct"] < 0.15, res.evidence["range_pct"]
    assert res.evidence["vcp_quality"] == "forming"
    assert res.evidence["pivot_price"] is None
    assert res.points == 3


def test_wide_range_chop_scores_zero() -> None:
    n = 60
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    for _i in range(40):
        closes.append(100.0)
        highs.append(100.5)
        lows.append(99.5)
    for i in range(20):
        c = 100.0 if i % 2 == 0 else 130.0
        closes.append(c)
        highs.append(c + 1.0)
        lows.append(c - 1.0)
    volumes = [1000.0] * n
    res = vcp_pivot(_ctx_from_ohlcv(closes, highs, lows, volumes))
    assert res.status == "scored"
    assert res.evidence["range_pct"] >= 0.15
    assert res.evidence["vcp_quality"] == "none"
    assert res.evidence["pivot_price"] is None
    assert res.points == 0


def test_pivot_price_invariant_per_quality() -> None:
    """pivot_price is None iff quality ∈ {none, forming}; positive float for
    {textbook, breakout}."""
    closes_form = [100.0] * 40 + [100.0 + i * (12.0 / 19.0) for i in range(20)]
    highs_form = [c + 0.2 for c in closes_form]
    lows_form = [c - 0.2 for c in closes_form]
    res_form = vcp_pivot(
        _ctx_from_ohlcv(closes_form, highs_form, lows_form, [1000.0] * 60)
    )
    assert res_form.evidence["vcp_quality"] == "forming"
    assert res_form.evidence["pivot_price"] is None

    closes_none = [100.0] * 40 + ([100.0, 130.0] * 10)
    highs_none = [c + 1.0 for c in closes_none]
    lows_none = [c - 1.0 for c in closes_none]
    res_none = vcp_pivot(
        _ctx_from_ohlcv(closes_none, highs_none, lows_none, [1000.0] * 60)
    )
    assert res_none.evidence["vcp_quality"] == "none"
    assert res_none.evidence["pivot_price"] is None
