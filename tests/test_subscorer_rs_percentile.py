"""rs_percentile sub-scorer tests.

Spec: openspec/changes/phase-2b-sepa-subscorers/specs/phase-2b-scoring-engine/spec.md
("rs_percentile sub-scorer (real implementation)" requirement).
"""

from __future__ import annotations

import pytest

from ohmystock.scoring._rs_universe import (
    reset_rs_universe_loader,
    set_rs_universe_loader,
)
from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.subscorers.rs_percentile import rs_percentile


def _ctx_from_closes(closes: list[float]) -> ScoringContext:
    bars = [
        {
            "ts": f"2025-01-{(i % 28) + 1:02d}",
            "o": closes[i],
            "h": closes[i],
            "l": closes[i],
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


def _linear_closes(n: int, start: float, end: float) -> list[float]:
    if n == 1:
        return [start]
    return [start + (end - start) * (i / (n - 1)) for i in range(n)]


@pytest.fixture(autouse=True)
def _restore_universe_loader():
    yield
    reset_rs_universe_loader()


def test_insufficient_bars_skipped() -> None:
    closes = _linear_closes(100, 10.0, 100.0)
    res = rs_percentile(_ctx_from_closes(closes))
    assert res.status == "skipped"
    assert res.points == 0
    assert res.evidence["reason"] == "insufficient_bars"
    assert res.evidence["have"] == 100
    assert res.evidence["need"] == 252


def test_top_decile_scores_seven() -> None:
    candidate_closes = _linear_closes(252, 10.0, 30.0)

    def _flat_universe() -> list[tuple[str, list[float]]]:
        return [(f"FLAT{i}", [50.0] * 252) for i in range(10)]

    set_rs_universe_loader(_flat_universe)
    res = rs_percentile(_ctx_from_closes(candidate_closes))
    assert res.status == "scored"
    assert res.evidence["rs_percentile"] >= 90
    assert res.points == 7
    assert res.evidence["universe_size"] == 10


def test_threshold_tiers_map_to_point_bands() -> None:
    """Construct universes that place the candidate at exactly 65 / 80 / 90
    percentile, and assert points == 3 / 5 / 7 respectively."""
    candidate_closes = _linear_closes(252, 10.0, 30.0)

    def _make_universe(below: int, above: int) -> list[tuple[str, list[float]]]:
        below_series = [10.0] * 252  # zero return
        above_series = _linear_closes(252, 10.0, 100.0)  # 9× return, beats candidate
        return [
            *((f"LOW{i}", below_series) for i in range(below)),
            *((f"HIGH{i}", above_series) for i in range(above)),
        ]

    cases = [
        (66, 34, 3),
        (81, 19, 5),
        (91, 9, 7),
    ]
    for below, above, expected_points in cases:
        set_rs_universe_loader(lambda b=below, a=above: _make_universe(b, a))
        res = rs_percentile(_ctx_from_closes(candidate_closes))
        assert res.status == "scored", (below, above)
        assert res.points == expected_points, (
            below, above, res.evidence["rs_percentile"], res.points,
        )


def test_rs_percentile_in_valid_range() -> None:
    """rs_percentile must always be int in [0, 99] regardless of universe."""
    candidate = _linear_closes(252, 10.0, 30.0)
    cases: list[tuple[str, object]] = [
        ("empty", lambda: []),
        (
            "all-above",
            lambda: [
                (f"X{i}", _linear_closes(252, 10.0, 100.0)) for i in range(10)
            ],
        ),
        (
            "all-below",
            lambda: [(f"X{i}", [10.0] * 252) for i in range(10)],
        ),
    ]
    for label, loader in cases:
        set_rs_universe_loader(loader)  # type: ignore[arg-type]
        res = rs_percentile(_ctx_from_closes(candidate))
        assert res.status == "scored", label
        rs_val = res.evidence["rs_percentile"]
        assert isinstance(rs_val, int), (label, type(rs_val))
        assert 0 <= rs_val <= 99, (label, rs_val)


def test_custom_universe_loader_is_honoured() -> None:
    candidate = _linear_closes(252, 10.0, 30.0)

    def _single_symbol_universe() -> list[tuple[str, list[float]]]:
        return [("FAKE", _linear_closes(252, 10.0, 11.0))]

    set_rs_universe_loader(_single_symbol_universe)
    res = rs_percentile(_ctx_from_closes(candidate))
    assert res.status == "scored"
    assert res.evidence["universe_size"] == 1
