"""Phase 2B deferred-stub sub-scorers — registration and dispatch behaviour.

Spec: openspec/changes/phase-2b-deferred-cli/specs/phase-2b-scoring-engine/spec.md
("Deferred-stub sub-scorers register with `status=\"skipped\"`" requirement).
"""

from __future__ import annotations

import pytest

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.registry import dispatch, list_subscorers

# Force registration via package import (side effect).
import ohmystock.scoring  # noqa: F401


# Spec contract: 14 deferred stubs with exact (name, category, max_points)
# after phase-2b-sepa-subscorers promoted rs_percentile and kline_patterns
# (the latter renamed to vcp_pivot) to real sub-scorers under subscorers/.
DEFERRED_STUBS: list[tuple[str, str, float]] = [
    ("broker_concentration", "chip", 7.0),
    ("futures_oi", "chip", 3.0),
    ("margin_tightening", "chip", 2.0),
    ("tdcc_concentration", "chip", 2.0),
    ("borrow_change", "chip", 2.0),
    ("eps_yoy", "fundamental", 8.0),
    ("eps_qoq", "fundamental", 5.0),
    ("monthly_revenue_yoy", "fundamental", 6.0),
    ("quarterly_revenue_yoy", "fundamental", 3.0),
    ("institutional_30d_holding", "fundamental", 3.0),
    ("analyst_target_upgrades", "sentiment", 3.0),
    ("sue", "sentiment", 3.0),
    ("important_announcements", "sentiment", 2.0),
    ("search_heat", "sentiment", 2.0),
]

# 8 real sub-scorers after phase-2b-sepa-subscorers shipped rs_percentile
# and vcp_pivot. Used to assert the registry contains exactly 22 entries
# (14 deferred + 8 real) after package load.
REAL_SUBSCORERS: list[tuple[str, str, float]] = [
    ("foreign_5d_net_buy", "chip", 5.0),
    ("rs_percentile", "technical", 7.0),
    ("stage_2_confirmed", "technical", 5.0),
    ("trend_structure_ma", "technical", 10.0),
    ("trend_template_8", "technical", 5.0),
    ("trust_5d_net_buy", "chip", 4.0),
    ("vcp_pivot", "technical", 8.0),
    ("volume_breakout_obv", "technical", 5.0),
]

NEGATIVE_BAND_NAMES = {"borrow_change", "search_heat"}
NEGATIVE_BAND_REASON_FRAGMENT = "negative-band scoring requires registry contract change"


def _empty_ctx() -> ScoringContext:
    return ScoringContext(
        asof_date="2026-04-30",
        symbol="2330",
        bars=[],
        three_major=[],
        margin_short=[],
    )


@pytest.mark.parametrize(("name", "category", "max_points"), DEFERRED_STUBS)
def test_deferred_stub_dispatches_as_skipped(
    name: str, category: str, max_points: float
) -> None:
    result = dispatch(name, _empty_ctx())
    assert result.status == "skipped"
    assert result.points == 0.0
    assert result.max_points == max_points
    assert result.category == category
    assert result.name == name
    assert isinstance(result.evidence, dict)
    assert isinstance(result.evidence.get("reason"), str)
    assert result.evidence["reason"]
    assert result.error_message is None


@pytest.mark.parametrize("name", sorted(NEGATIVE_BAND_NAMES))
def test_negative_band_stubs_annotate_registry_gap(name: str) -> None:
    result = dispatch(name, _empty_ctx())
    assert NEGATIVE_BAND_REASON_FRAGMENT in result.evidence["reason"], (
        f"{name} should document the registry-contract gap; "
        f"got reason={result.evidence['reason']!r}"
    )


def test_registry_contains_all_22_subscorers() -> None:
    actual = {(n, cat, mp) for n, cat, mp in list_subscorers()}
    expected = set(DEFERRED_STUBS) | set(REAL_SUBSCORERS)
    assert actual == expected, (
        f"unexpected registry contents.\n"
        f"missing: {expected - actual}\n"
        f"extra:   {actual - expected}"
    )
