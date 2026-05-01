"""Tests for ``ohmystock.decider.validator.validate_decider_output``."""

from __future__ import annotations

import pytest

from ohmystock.decider.models import DeciderOutput
from ohmystock.decider.validator import (
    ValidationResult,
    validate_decider_output,
)
from ohmystock.swarm.models import CandidateSnapshot


def _make_candidate(**overrides: object) -> CandidateSnapshot:
    base = {
        "symbol": "2330",
        "name": "台積電",
        "final_score": 78,
        "tech_score": 32,
        "chip_score": 18,
        "fundamental_score": 22,
        "sentiment_score": 6,
        "ema20_distance_pct": 3.2,
        "atr_14_pct": 2.4,
        "current_price": 845.0,
        "stage": 2,
        "rs_percentile": 87,
        "trend_template_passed": 8,
        "vcp_quality": "breakout",
        "pivot_price": 832.0,
        "distance_from_52w_high_pct": 4.1,
        "distance_from_52w_low_pct": 41.6,
    }
    base.update(overrides)
    return CandidateSnapshot(**base)


def _make_output(**overrides: object) -> DeciderOutput:
    payload = {
        "output_schema_version": "v3.1",
        "decision_id": "dec_2026-04-30T14-30-00_2330",
        "decided_at": "2026-04-30T14:34:22+08:00",
        "model": "claude-opus-4-7",
        "decision": "enter",
        "confidence": 0.83,
        "stage": 2,
        "rs_percentile": 87,
        "trend_template_passed": 8,
        "vcp_quality": "breakout",
        "pivot_price": 832.0,
        "must_have_check": [
            {"name": "trend_template_8_of_8", "pass": True, "evidence": "..."},
            {"name": "stage_2_confirmed", "pass": True, "evidence": "..."},
            {
                "name": "vcp_pivot_breakout_with_volume",
                "pass": True,
                "evidence": "...",
            },
        ],
        "bonus_score": 6,
        "bonus_breakdown": [],
        "proposed_sizing_pct": 18.0,
        "expected_holding_days": 8,
        "reasoning": "x" * 250,
        "cited_skills": ["technical/breakout"],
        "invalidation_conditions": [],
        "risk_flags": [],
        "tool_calls_summary": [],
    }
    payload.update(overrides)
    return DeciderOutput.model_validate(payload)


def test_happy_path_passes_all_rules() -> None:
    raw = _make_output()
    candidate = _make_candidate()
    result = validate_decider_output(raw, candidate)
    assert isinstance(result, ValidationResult)
    assert result.force_reject_reason is None
    assert result.final_decision.decision == "enter"
    assert result.applied_overrides == []


def test_confidence_below_0_6_force_rejects() -> None:
    raw = _make_output(confidence=0.55)
    result = validate_decider_output(raw, _make_candidate())
    assert result.force_reject_reason == "confidence_below_0_6"
    assert result.final_decision.decision == "reject"
    assert result.final_decision.confidence == 0.55


def test_confidence_at_0_6_passes() -> None:
    raw = _make_output(confidence=0.6)
    result = validate_decider_output(raw, _make_candidate())
    assert result.force_reject_reason is None


def test_reasoning_below_200_force_rejects() -> None:
    raw = _make_output(reasoning="x" * 100)
    result = validate_decider_output(raw, _make_candidate())
    assert result.force_reject_reason == "reasoning_too_short:100"


def test_reasoning_at_199_force_rejects_at_200_passes() -> None:
    raw_199 = _make_output(reasoning="台" * 199)
    assert (
        validate_decider_output(raw_199, _make_candidate()).force_reject_reason
        == "reasoning_too_short:199"
    )

    raw_200 = _make_output(reasoning="台" * 200)
    assert (
        validate_decider_output(raw_200, _make_candidate()).force_reject_reason
        is None
    )


def test_reasoning_unicode_codepoints_count_not_bytes() -> None:
    raw = _make_output(reasoning="台" * 100)
    result = validate_decider_output(raw, _make_candidate())
    assert result.force_reject_reason == "reasoning_too_short:100"


def test_holding_days_31_force_rejects() -> None:
    raw = _make_output(expected_holding_days=30)
    raw_oob = raw.model_copy(update={"expected_holding_days": 31})
    result = validate_decider_output(raw_oob, _make_candidate())
    assert result.force_reject_reason == "holding_days_out_of_range:31"


def test_sizing_out_of_range_force_rejects_via_model_copy() -> None:
    raw = _make_output(proposed_sizing_pct=25.0)
    raw_oob = raw.model_copy(update={"proposed_sizing_pct": 30.0})
    result = validate_decider_output(raw_oob, _make_candidate())
    assert result.force_reject_reason == "sizing_out_of_range:30.0"


def test_stage_4_force_rejects() -> None:
    raw = _make_output(stage=4)
    candidate = _make_candidate(stage=4)
    result = validate_decider_output(raw, candidate)
    assert result.force_reject_reason == "stage_4_excluded"
    assert result.final_decision.decision == "reject"


@pytest.mark.parametrize(
    "field,raw_val,cand_val",
    [
        ("stage", 3, 2),
        ("rs_percentile", 90, 87),
        ("trend_template_passed", 7, 8),
    ],
)
def test_candidate_divergence_force_rejects(
    field: str, raw_val: object, cand_val: object
) -> None:
    raw = _make_output(**{field: raw_val})
    candidate = _make_candidate(**{field: cand_val})
    result = validate_decider_output(raw, candidate)
    assert result.force_reject_reason == f"llm_diverged_from_candidate:{field}"


def test_candidate_divergence_pivot_price() -> None:
    raw = _make_output(pivot_price=832.0)
    candidate = _make_candidate(pivot_price=830.0)
    result = validate_decider_output(raw, candidate)
    assert (
        result.force_reject_reason == "llm_diverged_from_candidate:pivot_price"
    )


def test_candidate_divergence_vcp_quality_with_consistent_pivot() -> None:
    raw = _make_output(vcp_quality="textbook", pivot_price=832.0)
    candidate = _make_candidate(vcp_quality="breakout", pivot_price=832.0)
    result = validate_decider_output(raw, candidate)
    assert (
        result.force_reject_reason
        == "llm_diverged_from_candidate:vcp_quality"
    )


def test_must_have_names_wrong_force_rejects() -> None:
    raw = _make_output(
        must_have_check=[
            {"name": "old_v3_0_name", "pass": True, "evidence": "..."},
            {"name": "stage_2_confirmed", "pass": True, "evidence": "..."},
            {
                "name": "vcp_pivot_breakout_with_volume",
                "pass": True,
                "evidence": "...",
            },
        ]
    )
    result = validate_decider_output(raw, _make_candidate())
    assert result.force_reject_reason == "must_have_names_invalid"


def test_rs_percentile_diverge_fires_before_must_have() -> None:
    raw = _make_output()  # rs_percentile=87
    candidate = _make_candidate(rs_percentile=64)
    result = validate_decider_output(raw, candidate)
    assert (
        result.force_reject_reason
        == "llm_diverged_from_candidate:rs_percentile"
    )


def test_rs_percentile_64_when_consistent_auto_fails_trend_template() -> None:
    raw = _make_output(rs_percentile=64)
    candidate = _make_candidate(rs_percentile=64)
    result = validate_decider_output(raw, candidate)
    assert result.force_reject_reason == "must_have_failed:trend_template_8_of_8"


def test_rs_percentile_65_boundary_passes() -> None:
    raw = _make_output(rs_percentile=65)
    candidate = _make_candidate(rs_percentile=65)
    result = validate_decider_output(raw, candidate)
    assert result.force_reject_reason is None


def test_trend_template_passed_7_auto_fails() -> None:
    raw = _make_output(trend_template_passed=7)
    candidate = _make_candidate(trend_template_passed=7)
    result = validate_decider_output(raw, candidate)
    assert result.force_reject_reason == "must_have_failed:trend_template_8_of_8"


def test_vcp_forming_auto_fails_third_pillar() -> None:
    raw = _make_output(vcp_quality="forming", pivot_price=None)
    candidate = _make_candidate(vcp_quality="forming", pivot_price=None)
    result = validate_decider_output(raw, candidate)
    assert (
        result.force_reject_reason
        == "must_have_failed:vcp_pivot_breakout_with_volume"
    )


def test_vcp_none_auto_fails_third_pillar() -> None:
    raw = _make_output(vcp_quality="none", pivot_price=None)
    candidate = _make_candidate(vcp_quality="none", pivot_price=None)
    result = validate_decider_output(raw, candidate)
    assert (
        result.force_reject_reason
        == "must_have_failed:vcp_pivot_breakout_with_volume"
    )


def test_must_have_explicit_failure() -> None:
    raw = _make_output(
        must_have_check=[
            {"name": "trend_template_8_of_8", "pass": True, "evidence": "..."},
            {"name": "stage_2_confirmed", "pass": False, "evidence": "..."},
            {
                "name": "vcp_pivot_breakout_with_volume",
                "pass": True,
                "evidence": "...",
            },
        ]
    )
    result = validate_decider_output(raw, _make_candidate())
    assert result.force_reject_reason == "must_have_failed:stage_2_confirmed"


def test_bonus_score_3_force_rejects() -> None:
    raw = _make_output(bonus_score=3)
    result = validate_decider_output(raw, _make_candidate())
    assert result.force_reject_reason == "bonus_score_below_4:3"


def test_bonus_score_4_boundary_passes() -> None:
    raw = _make_output(bonus_score=4)
    result = validate_decider_output(raw, _make_candidate())
    assert result.force_reject_reason is None


def test_stage_3_sizing_capped() -> None:
    raw = _make_output(stage=3, proposed_sizing_pct=18.0)
    candidate = _make_candidate(stage=3)
    result = validate_decider_output(raw, candidate)
    assert result.force_reject_reason is None
    assert result.final_decision.proposed_sizing_pct == 10.0
    assert any(
        s == "stage_3_sizing_capped:18.0->10.0" for s in result.applied_overrides
    )


def test_stage_3_sizing_below_cap_unchanged() -> None:
    raw = _make_output(stage=3, proposed_sizing_pct=8.0)
    candidate = _make_candidate(stage=3)
    result = validate_decider_output(raw, candidate)
    assert result.force_reject_reason is None
    assert result.final_decision.proposed_sizing_pct == 8.0
    assert result.applied_overrides == []


def test_force_rejected_marker_in_applied_overrides() -> None:
    raw = _make_output(stage=4)
    candidate = _make_candidate(stage=4)
    result = validate_decider_output(raw, candidate)
    assert "force_rejected:stage_4_excluded" in result.applied_overrides


def test_first_violation_wins_confidence_before_reasoning() -> None:
    raw = _make_output(confidence=0.4, reasoning="x" * 50)
    result = validate_decider_output(raw, _make_candidate())
    assert result.force_reject_reason == "confidence_below_0_6"
