"""foreign_5d_net_buy sub-scorer tests.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("foreign_5d_net_buy sub-scorer" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.subscorers.foreign_5d_net_buy import foreign_5d_net_buy


def _ctx_with_foreign_nets(foreign_nets: list[int]) -> ScoringContext:
    rows = [
        {
            "date": f"2026-04-{i + 1:02d}",
            "foreign_net": foreign_nets[i],
            "invest_trust_net": 0,
            "prop_dealer_net": 0,
        }
        for i in range(len(foreign_nets))
    ]
    return ScoringContext(
        asof_date="2026-04-30",
        symbol="2330",
        bars=[],
        three_major=rows,
        margin_short=[],
    )


def test_heavy_buying_scores_5() -> None:
    res = foreign_5d_net_buy(_ctx_with_foreign_nets([300, 300, 300, 300, 300]))
    assert res.status == "scored"
    assert res.points == 5
    assert res.evidence["net_5d_lots"] == 1500


def test_boundary_1000_scores_3() -> None:
    res = foreign_5d_net_buy(_ctx_with_foreign_nets([200, 200, 200, 200, 200]))
    assert res.points == 3
    assert res.evidence["net_5d_lots"] == 1000


def test_boundary_1001_scores_5() -> None:
    res = foreign_5d_net_buy(_ctx_with_foreign_nets([200, 200, 200, 200, 201]))
    assert res.points == 5
    assert res.evidence["net_5d_lots"] == 1001


def test_mid_tier_350_scores_2() -> None:
    res = foreign_5d_net_buy(_ctx_with_foreign_nets([100, 100, 100, 50, 0]))
    assert res.points == 2
    assert res.evidence["net_5d_lots"] == 350


def test_boundary_200_scores_1() -> None:
    res = foreign_5d_net_buy(_ctx_with_foreign_nets([50, 50, 50, 50, 0]))
    assert res.points == 1
    assert res.evidence["net_5d_lots"] == 200


def test_zero_scores_zero() -> None:
    res = foreign_5d_net_buy(_ctx_with_foreign_nets([0, 0, 0, 0, 0]))
    assert res.points == 0


def test_net_selling_scores_zero() -> None:
    res = foreign_5d_net_buy(_ctx_with_foreign_nets([-100, -100, -50, -50, 0]))
    assert res.points == 0
    assert res.evidence["net_5d_lots"] == -300


def test_insufficient_rows_skipped() -> None:
    res = foreign_5d_net_buy(_ctx_with_foreign_nets([100, 100, 100]))
    assert res.status == "skipped"
    assert res.points == 0
    assert res.evidence["have"] == 3
    assert res.evidence["need"] == 5
