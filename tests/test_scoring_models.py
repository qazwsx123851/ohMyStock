"""Tests for Phase 2B Pydantic contracts.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
("Phase2BCandidate and SubScoreResult Pydantic contracts" requirement).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_subscore_result_valid_construction() -> None:
    from ohmystock.scoring.models import SubScoreResult

    r = SubScoreResult(
        name="trend_template",
        category="technical",
        points=5,
        max_points=5,
        status="scored",
    )
    assert r.name == "trend_template"
    assert r.category == "technical"
    assert r.points == 5
    assert r.max_points == 5
    assert r.status == "scored"
    assert r.evidence == {}
    assert r.error_message is None


def test_subscore_result_evidence_default_empty_dict() -> None:
    from ohmystock.scoring.models import SubScoreResult

    r = SubScoreResult(
        name="x", category="chip", points=0, max_points=2, status="skipped"
    )
    assert r.evidence == {}


def test_subscore_result_error_message_default_none() -> None:
    from ohmystock.scoring.models import SubScoreResult

    r = SubScoreResult(
        name="x", category="chip", points=0, max_points=2, status="error"
    )
    assert r.error_message is None


def test_subscore_result_rejects_unknown_category() -> None:
    from ohmystock.scoring.models import SubScoreResult

    with pytest.raises(ValidationError):
        SubScoreResult(
            name="x", category="other", points=0, max_points=2, status="scored"
        )


def test_subscore_result_rejects_unknown_status() -> None:
    from ohmystock.scoring.models import SubScoreResult

    with pytest.raises(ValidationError):
        SubScoreResult(
            name="x", category="technical", points=0, max_points=2, status="bogus"
        )


def test_phase2b_candidate_valid_construction_empty_subscores() -> None:
    from ohmystock.scoring.models import Phase2BCandidate

    c = Phase2BCandidate(
        symbol="2330",
        asof_date="2026-04-30",
        final_score=70.0,
        tech_subtotal=30.0,
        chip_subtotal=20.0,
        fund_subtotal=15.0,
        sent_subtotal=5.0,
        classification="green",
        risk_off_applied=False,
        subscores=[],
    )
    assert c.symbol == "2330"
    assert c.classification == "green"
    assert c.risk_off_applied is False
    assert c.subscores == []


def test_phase2b_candidate_rejects_unknown_classification() -> None:
    from ohmystock.scoring.models import Phase2BCandidate

    with pytest.raises(ValidationError):
        Phase2BCandidate(
            symbol="2330",
            asof_date="2026-04-30",
            final_score=0.0,
            tech_subtotal=0.0,
            chip_subtotal=0.0,
            fund_subtotal=0.0,
            sent_subtotal=0.0,
            classification="blue",
            risk_off_applied=False,
            subscores=[],
        )


def test_phase2b_candidate_accepts_subscore_list() -> None:
    from ohmystock.scoring.models import Phase2BCandidate, SubScoreResult

    sub = SubScoreResult(
        name="x", category="technical", points=5, max_points=5, status="scored"
    )
    c = Phase2BCandidate(
        symbol="2330",
        asof_date="2026-04-30",
        final_score=5.0,
        tech_subtotal=5.0,
        chip_subtotal=0.0,
        fund_subtotal=0.0,
        sent_subtotal=0.0,
        classification="red",
        risk_off_applied=False,
        subscores=[sub],
    )
    assert len(c.subscores) == 1
    assert c.subscores[0].name == "x"
