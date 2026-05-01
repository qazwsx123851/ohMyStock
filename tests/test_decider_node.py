"""Tests for ``ohmystock.decider.node`` — Anthropic impl + parse errors + fake."""

from __future__ import annotations

import json
import math
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from ohmystock.decider.models import DeciderOutput
from ohmystock.decider.node import (
    AnthropicPMConclusionNode,
    DeciderOutputParseError,
    FakePMConclusionNode,
    PMConclusionNode,
)
from ohmystock.swarm.models import (
    CandidateSnapshot,
    EntryDecisionInput,
    MarketContext,
    RulesDigest,
)


def _valid_decider_json(**overrides: object) -> dict:
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
            {"name": "rs_percentile_80", "pass": True, "evidence": "..."},
        ],
        "proposed_sizing_pct": 18.0,
        "expected_holding_days": 8,
        "reasoning": "x" * 250,
        "cited_skills": ["technical/breakout"],
        "invalidation_conditions": [],
        "risk_flags": [],
        "tool_calls_summary": [],
    }
    payload.update(overrides)
    return payload


def _entry_input() -> EntryDecisionInput:
    return EntryDecisionInput(
        decision_id="dec_2026-04-30T14-30-00_2330",
        trigger_at="2026-04-30T14:30:00+08:00",
        candidate=CandidateSnapshot(
            symbol="2330",
            name="台積電",
            final_score=78,
            tech_score=32,
            chip_score=18,
            fundamental_score=22,
            sentiment_score=6,
            ema20_distance_pct=3.2,
            atr_14_pct=2.4,
            current_price=845.0,
            stage=2,
            rs_percentile=87,
            trend_template_passed=8,
            vcp_quality="breakout",
            pivot_price=832.0,
            distance_from_52w_high_pct=4.1,
            distance_from_52w_low_pct=41.6,
        ),
        market_context=MarketContext(
            risk_off=False,
            monthly_pnl_pct=-1.8,
            recent_20_winrate=0.55,
            consecutive_loss=1,
            existing_positions=[],
            total_exposure_pct=0.0,
            same_sector_count=0,
        ),
        rules_summary=RulesDigest(
            must_have=["a", "b", "c"],
            bonus_items=["1", "2", "3", "4", "5", "6", "7", "8"],
        ),
        available_tools=[],
        available_skills=[],
    )


def _mock_response(text: str, *, input_tokens: int = 18420, output_tokens: int = 1240):
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    response.usage = MagicMock(
        input_tokens=input_tokens, output_tokens=output_tokens
    )
    return response


def test_anthropic_decide_happy_path() -> None:
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        json.dumps(_valid_decider_json())
    )
    node = AnthropicPMConclusionNode(client, "claude-opus-4-7")

    output, usage = node.decide(_entry_input())

    assert isinstance(output, DeciderOutput)
    assert output.decision == "enter"
    assert usage.input_tokens == 18420
    assert usage.output_tokens == 1240
    assert usage.model == "claude-opus-4-7"
    assert math.isclose(usage.cost_usd, 0.36930, abs_tol=1e-9)


def test_anthropic_decide_passes_system_and_user_message() -> None:
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        json.dumps(_valid_decider_json())
    )
    node = AnthropicPMConclusionNode(client, "claude-opus-4-7")
    node.decide(_entry_input())

    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-7"
    assert "PM Conclusion Node" in call_kwargs["system"]
    assert call_kwargs["max_tokens"] == 4096
    assert call_kwargs["messages"][0]["role"] == "user"
    assert "2330" in call_kwargs["messages"][0]["content"]


def test_anthropic_decide_non_json_raises_parse_error() -> None:
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        "I think we should enter, the chart looks good"
    )
    node = AnthropicPMConclusionNode(client, "claude-opus-4-7")

    with pytest.raises(DeciderOutputParseError) as exc_info:
        node.decide(_entry_input())

    exc = exc_info.value
    assert "I think we should enter" in exc.raw_text
    assert isinstance(exc.cause, json.JSONDecodeError)


def test_anthropic_decide_missing_fields_raises_parse_error() -> None:
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        json.dumps({"decision": "enter", "confidence": 0.8})
    )
    node = AnthropicPMConclusionNode(client, "claude-opus-4-7")

    with pytest.raises(DeciderOutputParseError) as exc_info:
        node.decide(_entry_input())

    assert isinstance(exc_info.value.cause, ValidationError)


def test_anthropic_decide_unknown_model_raises_keyerror() -> None:
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        json.dumps(_valid_decider_json())
    )
    node = AnthropicPMConclusionNode(client, "claude-fake-99")

    with pytest.raises(KeyError) as exc_info:
        node.decide(_entry_input())

    assert "claude-fake-99" in str(exc_info.value)


def test_parse_error_truncates_raw_text_to_500() -> None:
    raw = "x" * 1000
    exc = DeciderOutputParseError(raw, ValueError("boom"))
    assert len(exc.raw_text) == 500


def test_anthropic_class_satisfies_protocol() -> None:
    client = MagicMock()
    node = AnthropicPMConclusionNode(client, "claude-opus-4-7")
    assert isinstance(node, PMConclusionNode)


def test_fake_class_satisfies_protocol() -> None:
    fake = FakePMConclusionNode()
    assert isinstance(fake, PMConclusionNode)


def test_fake_returns_configured_output() -> None:
    output = DeciderOutput.model_validate(_valid_decider_json())
    fake = FakePMConclusionNode(output=output)
    out2, usage = fake.decide(_entry_input())
    assert out2 is output
    assert usage.model == "fake://"
    assert len(fake.calls) == 1


def test_fake_raises_parse_error_when_configured() -> None:
    err = DeciderOutputParseError(
        "garbage", json.JSONDecodeError("expecting value", "garbage", 0)
    )
    fake = FakePMConclusionNode(raise_parse_error=err)
    with pytest.raises(DeciderOutputParseError) as exc_info:
        fake.decide(_entry_input())
    assert exc_info.value is err
