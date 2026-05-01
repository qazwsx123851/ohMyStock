"""Pydantic-model tests for swarm input assembler.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ohmystock.swarm import (
    CandidateSnapshot,
    EntryDecisionInput,
    ExistingPosition,
    MarketContext,
    RulesDigest,
)


_SAMPLE_PAYLOAD = {
    "input_schema_version": "v3.1",
    "decision_id": "dec_2026-04-30T14-30-00_2330",
    "trigger_at": "2026-04-30T14:30:00+08:00",
    "candidate": {
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
    },
    "market_context": {
        "risk_off": False,
        "monthly_pnl_pct": -1.8,
        "recent_20_winrate": 0.55,
        "consecutive_loss": 1,
        "existing_positions": [
            {"symbol": "2454", "sector": "半導體", "exposure_pct": 18.0},
            {"symbol": "2317", "sector": "電子組裝", "exposure_pct": 12.0},
        ],
        "total_exposure_pct": 30.0,
        "same_sector_count": 1,
    },
    "rules_summary": {
        "must_have": [
            "Trend Template 8/8 全過（依 §2 第一層）",
            "Stage 2 確認（依 §0.4 / §2 第三層）",
            "VCP/杯柄/平台 + Pivot Breakout 量能（≥ 1.4× 20DMA、Pivot~Pivot+5%）",
        ],
        "bonus_items": [
            "季 EPS YoY ≥ 25%（且本季 > 前季加速）",
            "月營收 YoY ≥ 20% 且創歷史新高",
            "RS Percentile ≥ 80",
            "距 52 週高 ≤ 15%",
            "VCP 收縮 ≥ 4 次（每次振幅 ≤ 前次 50%）",
            "機構持股遞增（外資/投信 30 日 + 主力分點 ≥ 25%）",
            "產業 RS 領先（產業 RS Percentile ≥ 80）",
            "新高 + 量爆（突破 52 週新高 + 量 ≥ 1.5× 20DMA）",
        ],
    },
    "available_tools": [
        "market_data_tool",
        "chip_data_tool",
        "pattern_recognition_tool",
        "news_sentiment_tool",
        "fundamental_data_tool",
    ],
    "available_skills": [
        "technical/trend-template",
        "technical/stage-analysis",
        "technical/vcp-pivot",
        "technical/breakout",
        "chip/three-major-investors",
        "chip/broker-branch",
        "chip/securities-lending",
        "fundamental/eps-growth",
        "fundamental/revenue-growth",
        "tw_specific/momentum-swing",
        "tw_specific/rs-percentile",
    ],
}


def _candidate(**overrides) -> CandidateSnapshot:
    payload = dict(_SAMPLE_PAYLOAD["candidate"])
    payload.update(overrides)
    return CandidateSnapshot(**payload)


def test_round_trip_sample_payload() -> None:
    obj = EntryDecisionInput.model_validate(_SAMPLE_PAYLOAD)
    dumped = obj.model_dump(mode="json")
    assert dumped == _SAMPLE_PAYLOAD


def test_unknown_field_rejected() -> None:
    bad = dict(_SAMPLE_PAYLOAD)
    bad["extra_field"] = 1
    with pytest.raises(ValidationError):
        EntryDecisionInput.model_validate(bad)


def test_unknown_field_in_candidate_rejected() -> None:
    bad = dict(_SAMPLE_PAYLOAD)
    bad_candidate = dict(_SAMPLE_PAYLOAD["candidate"])
    bad_candidate["surprise"] = "no"
    bad["candidate"] = bad_candidate
    with pytest.raises(ValidationError):
        EntryDecisionInput.model_validate(bad)


def test_input_schema_version_must_be_v3_1() -> None:
    bad = dict(_SAMPLE_PAYLOAD)
    bad["input_schema_version"] = "v3.0"
    with pytest.raises(ValidationError):
        EntryDecisionInput.model_validate(bad)


def test_pivot_price_required_when_breakout() -> None:
    with pytest.raises(ValidationError):
        _candidate(vcp_quality="breakout", pivot_price=None)


def test_pivot_price_required_when_textbook() -> None:
    with pytest.raises(ValidationError):
        _candidate(vcp_quality="textbook", pivot_price=None)


def test_pivot_price_must_be_none_when_forming() -> None:
    with pytest.raises(ValidationError):
        _candidate(vcp_quality="forming", pivot_price=832.0)


def test_pivot_price_must_be_none_when_none_quality() -> None:
    with pytest.raises(ValidationError):
        _candidate(vcp_quality="none", pivot_price=832.0)


def test_pivot_price_zero_rejected_for_breakout() -> None:
    with pytest.raises(ValidationError):
        _candidate(vcp_quality="breakout", pivot_price=0.0)


def test_rs_percentile_out_of_range() -> None:
    with pytest.raises(ValidationError):
        _candidate(rs_percentile=100)


def test_rs_percentile_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        _candidate(rs_percentile=-1)


def test_trend_template_passed_out_of_range() -> None:
    with pytest.raises(ValidationError):
        _candidate(trend_template_passed=9)


def test_stage_must_be_one_through_four() -> None:
    with pytest.raises(ValidationError):
        _candidate(stage=5)


def test_vcp_quality_enum_enforced() -> None:
    with pytest.raises(ValidationError):
        _candidate(vcp_quality="bogus")


def test_rules_digest_must_have_count() -> None:
    with pytest.raises(ValidationError):
        RulesDigest(must_have=["a", "b"], bonus_items=["x"] * 8)


def test_rules_digest_bonus_items_count() -> None:
    with pytest.raises(ValidationError):
        RulesDigest(must_have=["a", "b", "c"], bonus_items=["x"] * 7)


def test_market_context_winrate_range() -> None:
    base = dict(_SAMPLE_PAYLOAD["market_context"])
    base["recent_20_winrate"] = 1.5
    with pytest.raises(ValidationError):
        MarketContext(**base)


def test_existing_position_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ExistingPosition(symbol="2330", sector="半導體", exposure_pct=10.0, unexpected=True)
