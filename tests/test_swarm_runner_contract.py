"""End-to-end contract test for the swarm runner.

Validates the runner output against ``EntryDecisionInput`` (round-trip the
serialised JSON back through the model).

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

import json

from ohmystock.scoring.models import Phase2BCandidate
from ohmystock.swarm import (
    EntryDecisionInput,
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


def test_runner_output_round_trips_through_model() -> None:
    candidate = Phase2BCandidate(
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
    obj = build_entry_decision_input(
        candidate=candidate,
        candidate_name="台積電",
        candidate_sector="半導體",
        current_price=845.0,
        ema20_distance_pct=3.2,
        atr_14_pct=2.4,
        distance_from_52w_high_pct=4.1,
        distance_from_52w_low_pct=41.6,
        market=MarketSnapshot(20000.0, 0.5, False, -1.8),
        portfolio=PortfolioSnapshot(
            positions=[PortfolioPosition("2454", "半導體", 18.0)],
            total_exposure_pct=18.0,
        ),
        journal_stats=_FakeJournal(),
        rules_digest=RulesDigest(
            must_have=["a", "b", "c"],
            bonus_items=["1", "2", "3", "4", "5", "6", "7", "8"],
        ),
        available_tools=["chip_data_tool", "market_data_tool"],
        available_skills=["chip/three-major-investors", "technical/breakout"],
        trigger_at="2026-04-30T14:30:00+08:00",
    )

    serialized = json.dumps(obj.model_dump(mode="json"), ensure_ascii=False)
    rebuilt = EntryDecisionInput.model_validate_json(serialized)
    assert rebuilt == obj
