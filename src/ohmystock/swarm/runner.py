"""Public entry point for the swarm input assembler.

``build_entry_decision_input`` is the single function that converts a
Phase 2B scored candidate plus pre-built snapshots into a v3.1
``EntryDecisionInput`` payload (per ``docs/llm-decision-schema.md`` §1).

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

from ohmystock.scoring.models import Phase2BCandidate
from ohmystock.swarm._adapters import (
    JournalStatsProvider,
    MarketSnapshot,
    PortfolioSnapshot,
)
from ohmystock.swarm._input_assembler import assemble
from ohmystock.swarm.models import EntryDecisionInput, RulesDigest


def build_entry_decision_input(
    *,
    candidate: Phase2BCandidate,
    candidate_name: str,
    candidate_sector: str,
    current_price: float,
    ema20_distance_pct: float,
    atr_14_pct: float,
    distance_from_52w_high_pct: float,
    distance_from_52w_low_pct: float,
    market: MarketSnapshot,
    portfolio: PortfolioSnapshot,
    journal_stats: JournalStatsProvider,
    rules_digest: RulesDigest,
    available_tools: list[str],
    available_skills: list[str],
    trigger_at: str,
) -> EntryDecisionInput:
    """Assemble the entry-decision-team input. See ``_input_assembler.assemble``."""
    return assemble(
        candidate=candidate,
        candidate_name=candidate_name,
        candidate_sector=candidate_sector,
        current_price=current_price,
        ema20_distance_pct=ema20_distance_pct,
        atr_14_pct=atr_14_pct,
        distance_from_52w_high_pct=distance_from_52w_high_pct,
        distance_from_52w_low_pct=distance_from_52w_low_pct,
        market=market,
        portfolio=portfolio,
        journal_stats=journal_stats,
        rules_digest=rules_digest,
        available_tools=available_tools,
        available_skills=available_skills,
        trigger_at=trigger_at,
    )
