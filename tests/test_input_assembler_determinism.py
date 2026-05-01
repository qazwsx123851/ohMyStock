"""Determinism test for the swarm input assembler.

Identical inputs (including ``trigger_at``) must produce byte-identical JSON.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

import json

from ohmystock.scoring.models import Phase2BCandidate
from ohmystock.swarm import (
    MarketSnapshot,
    PortfolioPosition,
    PortfolioSnapshot,
    RulesDigest,
    build_entry_decision_input,
)


class _FakeJournal:
    def recent_winrate(self, n: int = 20) -> float:
        return 0.55

    def consecutive_loss(self) -> int:
        return 1


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
        must_have=["a", "b", "c"],
        bonus_items=["1", "2", "3", "4", "5", "6", "7", "8"],
    )


def _kwargs() -> dict:
    return dict(
        candidate=_candidate(),
        candidate_name="台積電",
        candidate_sector="半導體",
        current_price=845.0,
        ema20_distance_pct=3.2,
        atr_14_pct=2.4,
        distance_from_52w_high_pct=4.1,
        distance_from_52w_low_pct=41.6,
        market=MarketSnapshot(
            taiex_close=20000.0,
            taiex_change_pct=0.5,
            risk_off=False,
            monthly_pnl_pct=-1.8,
        ),
        portfolio=PortfolioSnapshot(
            positions=[
                PortfolioPosition(symbol="2454", sector="半導體", exposure_pct=18.0),
                PortfolioPosition(symbol="2317", sector="電子組裝", exposure_pct=12.0),
            ],
            total_exposure_pct=30.0,
        ),
        journal_stats=_FakeJournal(),
        rules_digest=_digest(),
        available_tools=["b_tool", "a_tool"],
        available_skills=["z/skill", "a/skill"],
        trigger_at="2026-04-30T14:30:00+08:00",
    )


def test_repeated_calls_byte_identical_json() -> None:
    a = build_entry_decision_input(**_kwargs())
    b = build_entry_decision_input(**_kwargs())
    payload_a = json.dumps(a.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    payload_b = json.dumps(b.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    assert payload_a == payload_b


def test_input_iteration_does_not_mutate_inputs() -> None:
    kw = _kwargs()
    original_tools = list(kw["available_tools"])
    original_skills = list(kw["available_skills"])

    build_entry_decision_input(**kw)
    build_entry_decision_input(**kw)

    assert kw["available_tools"] == original_tools
    assert kw["available_skills"] == original_skills


def test_lists_are_sorted_in_output() -> None:
    obj = build_entry_decision_input(**_kwargs())
    assert obj.available_tools == ["a_tool", "b_tool"]
    assert obj.available_skills == ["a/skill", "z/skill"]
