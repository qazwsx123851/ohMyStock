"""Snapshot test for the swarm input assembler.

Pins the JSON output for a fixed input fixture so unintended drift fails CI.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

import pytest

from ohmystock.scoring.models import Phase2BCandidate
from ohmystock.swarm import (
    AssemblerInputError,
    MarketSnapshot,
    PortfolioPosition,
    PortfolioSnapshot,
    RulesDigest,
    build_entry_decision_input,
)


class _FakeJournal:
    def __init__(self, winrate: float = 0.55, streak: int = 1) -> None:
        self._w = winrate
        self._s = streak

    def recent_winrate(self, n: int = 20) -> float:
        return self._w

    def consecutive_loss(self) -> int:
        return self._s


def _candidate() -> Phase2BCandidate:
    return Phase2BCandidate(
        symbol="2330",
        asof_date="2026-04-30",
        final_score=78.0,
        tech_subtotal=32.0,
        chip_subtotal=18.0,
        fund_subtotal=22.0,
        sent_subtotal=6.0,
        classification="green",
        risk_off_applied=False,
        subscores=[],
        stage=2,
        rs_percentile=87,
        trend_template_passed=8,
        vcp_quality="breakout",
        pivot_price=832.0,
    )


def _digest() -> RulesDigest:
    return RulesDigest(
        must_have=[
            "Trend Template 8/8 全過（依 §2 第一層）",
            "Stage 2 確認（依 §0.4 / §2 第三層）",
            "VCP/杯柄/平台 + Pivot Breakout 量能（≥ 1.4× 20DMA、Pivot~Pivot+5%）",
        ],
        bonus_items=[
            "季 EPS YoY ≥ 25%（且本季 > 前季加速）",
            "月營收 YoY ≥ 20% 且創歷史新高",
            "RS Percentile ≥ 80",
            "距 52 週高 ≤ 15%",
            "VCP 收縮 ≥ 4 次（每次振幅 ≤ 前次 50%）",
            "機構持股遞增（外資/投信 30 日 + 主力分點 ≥ 25%）",
            "產業 RS 領先（產業 RS Percentile ≥ 80）",
            "新高 + 量爆（突破 52 週新高 + 量 ≥ 1.5× 20DMA）",
        ],
    )


def _market() -> MarketSnapshot:
    return MarketSnapshot(
        taiex_close=20000.0,
        taiex_change_pct=0.5,
        risk_off=False,
        monthly_pnl_pct=-1.8,
    )


def _portfolio() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        positions=[
            PortfolioPosition(symbol="2454", sector="半導體", exposure_pct=18.0),
            PortfolioPosition(symbol="2317", sector="電子組裝", exposure_pct=12.0),
        ],
        total_exposure_pct=30.0,
    )


_KW_BASE = dict(
    candidate_name="台積電",
    candidate_sector="半導體",
    current_price=845.0,
    ema20_distance_pct=3.2,
    atr_14_pct=2.4,
    distance_from_52w_high_pct=4.1,
    distance_from_52w_low_pct=41.6,
    available_tools=[
        "market_data_tool",
        "chip_data_tool",
        "pattern_recognition_tool",
        "news_sentiment_tool",
        "fundamental_data_tool",
    ],
    available_skills=[
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
    trigger_at="2026-04-30T14:30:00+08:00",
)


def _build():
    return build_entry_decision_input(
        candidate=_candidate(),
        market=_market(),
        portfolio=_portfolio(),
        journal_stats=_FakeJournal(),
        rules_digest=_digest(),
        **_KW_BASE,
    )


def test_snapshot_pins_output_shape() -> None:
    obj = _build()
    dumped = obj.model_dump(mode="json")

    assert dumped["input_schema_version"] == "v3.1"
    assert dumped["decision_id"] == "dec_2026-04-30T14-30-00_2330"
    assert dumped["trigger_at"] == "2026-04-30T14:30:00+08:00"

    assert dumped["candidate"] == {
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

    assert dumped["market_context"]["existing_positions"] == [
        {"symbol": "2454", "sector": "半導體", "exposure_pct": 18.0},
        {"symbol": "2317", "sector": "電子組裝", "exposure_pct": 12.0},
    ]
    assert dumped["market_context"]["same_sector_count"] == 1
    assert dumped["market_context"]["recent_20_winrate"] == 0.55
    assert dumped["market_context"]["consecutive_loss"] == 1

    assert dumped["available_tools"] == sorted(dumped["available_tools"])
    assert dumped["available_skills"] == sorted(dumped["available_skills"])


def test_existing_positions_sorted_by_exposure_desc_then_symbol_asc() -> None:
    portfolio = PortfolioSnapshot(
        positions=[
            PortfolioPosition(symbol="2317", sector="電子組裝", exposure_pct=12.0),
            PortfolioPosition(symbol="3008", sector="光學", exposure_pct=18.0),
            PortfolioPosition(symbol="2454", sector="半導體", exposure_pct=18.0),
        ],
        total_exposure_pct=48.0,
    )
    obj = build_entry_decision_input(
        candidate=_candidate(),
        market=_market(),
        portfolio=portfolio,
        journal_stats=_FakeJournal(),
        rules_digest=_digest(),
        **_KW_BASE,
    )
    symbols = [p.symbol for p in obj.market_context.existing_positions]
    assert symbols == ["2454", "3008", "2317"]


def test_same_sector_count_counts_matches() -> None:
    portfolio = PortfolioSnapshot(
        positions=[
            PortfolioPosition(symbol="2454", sector="半導體", exposure_pct=18.0),
            PortfolioPosition(symbol="3008", sector="半導體", exposure_pct=10.0),
            PortfolioPosition(symbol="2317", sector="電子組裝", exposure_pct=12.0),
        ],
        total_exposure_pct=40.0,
    )
    obj = build_entry_decision_input(
        candidate=_candidate(),
        market=_market(),
        portfolio=portfolio,
        journal_stats=_FakeJournal(),
        rules_digest=_digest(),
        **_KW_BASE,
    )
    assert obj.market_context.same_sector_count == 2


def test_score_below_threshold_raises() -> None:
    bad = _candidate().model_copy(update={"final_score": 64.9})
    with pytest.raises(AssemblerInputError, match="score below threshold"):
        build_entry_decision_input(
            candidate=bad,
            market=_market(),
            portfolio=_portfolio(),
            journal_stats=_FakeJournal(),
            rules_digest=_digest(),
            **_KW_BASE,
        )


def test_exactly_at_threshold_succeeds() -> None:
    cand = _candidate().model_copy(update={"final_score": 65.0})
    obj = build_entry_decision_input(
        candidate=cand,
        market=_market(),
        portfolio=_portfolio(),
        journal_stats=_FakeJournal(),
        rules_digest=_digest(),
        **_KW_BASE,
    )
    assert obj.candidate.final_score == 65


def test_missing_sepa_field_raises() -> None:
    bad = _candidate().model_copy(update={"vcp_quality": None})
    with pytest.raises(AssemblerInputError, match="vcp_quality"):
        build_entry_decision_input(
            candidate=bad,
            market=_market(),
            portfolio=_portfolio(),
            journal_stats=_FakeJournal(),
            rules_digest=_digest(),
            **_KW_BASE,
        )


def test_trigger_at_without_offset_raises() -> None:
    bad_kw = dict(_KW_BASE)
    bad_kw["trigger_at"] = "2026-04-30T14:30:00"
    with pytest.raises(AssemblerInputError, match="trigger_at"):
        build_entry_decision_input(
            candidate=_candidate(),
            market=_market(),
            portfolio=_portfolio(),
            journal_stats=_FakeJournal(),
            rules_digest=_digest(),
            **bad_kw,
        )


def test_decision_id_uses_normalized_trigger_at() -> None:
    kw = dict(_KW_BASE)
    kw["trigger_at"] = "2026-04-30T09:00:30+08:00"
    obj = build_entry_decision_input(
        candidate=_candidate(),
        market=_market(),
        portfolio=_portfolio(),
        journal_stats=_FakeJournal(),
        rules_digest=_digest(),
        **kw,
    )
    assert obj.decision_id == "dec_2026-04-30T09-00-30_2330"
