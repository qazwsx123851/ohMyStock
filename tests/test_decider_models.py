"""Tests for ``ohmystock.decider.models.DeciderOutput`` v3.1 schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ohmystock.decider.models import DeciderOutput


def _valid_payload(**overrides: object) -> dict:
    """Returns a synthetic v3.1 enter-decision payload mirroring
    ``docs/llm-decision-schema.md`` §2 example.
    """
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
        "bonus_breakdown": [
            {"name": "eps_yoy_25", "pass": True, "evidence": "..."},
        ],
        "proposed_sizing_pct": 18.0,
        "expected_holding_days": 8,
        "reasoning": "x" * 250,
        "cited_skills": ["technical/breakout"],
        "invalidation_conditions": ["RS Percentile 跌破 50"],
        "risk_flags": [],
        "tool_calls_summary": [
            {"tool": "market_data_tool", "action": "get_kline", "elapsed_ms": 230}
        ],
    }
    payload.update(overrides)
    return payload


def test_v3_1_example_parses() -> None:
    out = DeciderOutput.model_validate(_valid_payload())
    assert out.decision == "enter"
    assert out.stage == 2
    assert out.pivot_price == 832.0
    assert out.must_have_check[0].pass_ is True


def test_pivot_invariant_forming_with_pivot_price_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        DeciderOutput.model_validate(
            _valid_payload(vcp_quality="forming", pivot_price=820.0)
        )
    msg = str(exc_info.value)
    assert "pivot_price" in msg
    assert "vcp_quality" in msg


def test_pivot_invariant_breakout_without_pivot_price_rejected() -> None:
    with pytest.raises(ValidationError):
        DeciderOutput.model_validate(
            _valid_payload(vcp_quality="breakout", pivot_price=None)
        )


def test_pivot_invariant_textbook_with_zero_pivot_rejected() -> None:
    with pytest.raises(ValidationError):
        DeciderOutput.model_validate(
            _valid_payload(vcp_quality="textbook", pivot_price=0.0)
        )


def test_pivot_invariant_none_quality_with_null_pivot_ok() -> None:
    out = DeciderOutput.model_validate(
        _valid_payload(vcp_quality="none", pivot_price=None)
    )
    assert out.pivot_price is None


def test_must_have_check_length_2_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        DeciderOutput.model_validate(
            _valid_payload(
                must_have_check=[
                    {
                        "name": "trend_template_8_of_8",
                        "pass": True,
                        "evidence": "...",
                    },
                    {
                        "name": "stage_2_confirmed",
                        "pass": True,
                        "evidence": "...",
                    },
                ]
            )
        )
    assert "must_have_check" in str(exc_info.value)


def test_extra_field_rejected() -> None:
    payload = _valid_payload()
    payload["foo"] = "bar"
    with pytest.raises(ValidationError) as exc_info:
        DeciderOutput.model_validate(payload)
    msg = str(exc_info.value).lower()
    assert "foo" in msg
    assert "extra" in msg


def test_confidence_above_one_rejected() -> None:
    with pytest.raises(ValidationError):
        DeciderOutput.model_validate(_valid_payload(confidence=1.5))


def test_unknown_decision_enum_rejected() -> None:
    with pytest.raises(ValidationError):
        DeciderOutput.model_validate(_valid_payload(decision="hold"))


def test_proposed_sizing_above_25_rejected() -> None:
    with pytest.raises(ValidationError):
        DeciderOutput.model_validate(_valid_payload(proposed_sizing_pct=30.0))


def test_expected_holding_days_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        DeciderOutput.model_validate(_valid_payload(expected_holding_days=0))


def test_cited_skills_empty_rejected() -> None:
    with pytest.raises(ValidationError):
        DeciderOutput.model_validate(_valid_payload(cited_skills=[]))
