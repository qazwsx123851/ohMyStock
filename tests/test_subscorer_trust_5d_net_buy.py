"""trust_5d_net_buy sub-scorer tests.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("trust_5d_net_buy sub-scorer" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.subscorers.trust_5d_net_buy import trust_5d_net_buy


def _ctx_with_trust_nets(trust_nets: list[int]) -> ScoringContext:
    rows = [
        {
            "date": f"2026-04-{i + 1:02d}",
            "foreign_net": 0,
            "invest_trust_net": trust_nets[i],
            "prop_dealer_net": 0,
        }
        for i in range(len(trust_nets))
    ]
    return ScoringContext(
        asof_date="2026-04-30",
        symbol="2330",
        bars=[],
        three_major=rows,
        margin_short=[],
    )


def test_heavy_buying_scores_4() -> None:
    res = trust_5d_net_buy(_ctx_with_trust_nets([120, 120, 120, 120, 120]))
    assert res.status == "scored"
    assert res.points == 4
    assert res.evidence["net_5d_lots"] == 600


def test_boundary_301_scores_4() -> None:
    res = trust_5d_net_buy(_ctx_with_trust_nets([100, 100, 100, 1, 0]))
    assert res.points == 4
    assert res.evidence["net_5d_lots"] == 301


def test_boundary_300_scores_2() -> None:
    res = trust_5d_net_buy(_ctx_with_trust_nets([100, 100, 100, 0, 0]))
    assert res.points == 2
    assert res.evidence["net_5d_lots"] == 300


def test_mid_tier_250_scores_2() -> None:
    res = trust_5d_net_buy(_ctx_with_trust_nets([100, 100, 50, 0, 0]))
    assert res.points == 2
    assert res.evidence["net_5d_lots"] == 250


def test_boundary_100_scores_1() -> None:
    res = trust_5d_net_buy(_ctx_with_trust_nets([50, 50, 0, 0, 0]))
    assert res.points == 1
    assert res.evidence["net_5d_lots"] == 100


def test_zero_scores_zero() -> None:
    res = trust_5d_net_buy(_ctx_with_trust_nets([0, 0, 0, 0, 0]))
    assert res.points == 0


def test_net_selling_scores_zero() -> None:
    res = trust_5d_net_buy(_ctx_with_trust_nets([-20, -10, -10, -5, -5]))
    assert res.points == 0
    assert res.evidence["net_5d_lots"] == -50


def test_insufficient_rows_skipped() -> None:
    res = trust_5d_net_buy(_ctx_with_trust_nets([]))
    assert res.status == "skipped"
    assert res.points == 0
