"""Tests for ohmystock.scoring.iter_qualified_candidates.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/phase-2b-scoring-engine/spec.md
"""

from __future__ import annotations

import pytest

from ohmystock.scoring import (
    Phase2BCandidate,
    iter_qualified_candidates,
    reset_candidate_loader,
    set_candidate_loader,
)


def _candidate(symbol: str, score: float, **overrides) -> Phase2BCandidate:
    base = dict(
        symbol=symbol,
        asof_date="2026-04-30",
        final_score=score,
        tech_subtotal=0.0,
        chip_subtotal=0.0,
        fund_subtotal=0.0,
        sent_subtotal=0.0,
        classification="green",
        risk_off_applied=False,
        subscores=[],
        stage=2,
        rs_percentile=87,
        trend_template_passed=8,
        vcp_quality="breakout",
        pivot_price=832.0,
    )
    base.update(overrides)
    return Phase2BCandidate(**base)


def test_filters_below_threshold() -> None:
    cands = [
        _candidate("2330", 78),
        _candidate("1234", 60),
        _candidate("2454", 72),
    ]
    out = list(iter_qualified_candidates("2026-04-30", candidates=cands))
    symbols = [c.symbol for c in out]
    assert symbols == ["2330", "2454"]


def test_orders_by_score_desc_then_symbol_asc() -> None:
    cands = [
        _candidate("3008", 72),
        _candidate("2454", 72),
        _candidate("2330", 78),
    ]
    out = list(iter_qualified_candidates("2026-04-30", candidates=cands))
    assert [c.symbol for c in out] == ["2330", "2454", "3008"]


def test_empty_iterable_when_none_qualify() -> None:
    cands = [_candidate("0050", 30), _candidate("0056", 50)]
    out = list(iter_qualified_candidates("2026-04-30", candidates=cands))
    assert out == []


def test_empty_iterable_when_no_input() -> None:
    out = list(iter_qualified_candidates("2026-04-30", candidates=[]))
    assert out == []


def test_threshold_kwarg_overrides_default() -> None:
    cands = [_candidate("2330", 50), _candidate("2317", 60)]
    out = list(iter_qualified_candidates("2026-04-30", candidates=cands, threshold=55.0))
    assert [c.symbol for c in out] == ["2317"]


def test_default_loader_raises_when_unset() -> None:
    reset_candidate_loader()
    with pytest.raises(NotImplementedError, match="loader"):
        list(iter_qualified_candidates("2026-04-30"))


def test_set_candidate_loader_swaps_resolution() -> None:
    fake = [_candidate("2330", 78), _candidate("9999", 30)]
    set_candidate_loader(lambda asof: fake)
    try:
        out = list(iter_qualified_candidates("2026-04-30"))
        assert [c.symbol for c in out] == ["2330"]
    finally:
        reset_candidate_loader()


def test_qualified_candidates_have_sepa_fields_populated() -> None:
    cands = [_candidate("2330", 78)]
    out = list(iter_qualified_candidates("2026-04-30", candidates=cands))
    c = out[0]
    assert c.stage == 2
    assert c.rs_percentile == 87
    assert c.trend_template_passed == 8
    assert c.vcp_quality == "breakout"
    assert c.pivot_price == 832.0
