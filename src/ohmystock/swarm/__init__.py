"""Swarm input assembler — Phase 2B candidate → entry_decision_team input.

Public API:
    EntryDecisionInput, CandidateSnapshot, ExistingPosition, MarketContext,
    RulesDigest, AssemblerInputError, RulesDigestError, build_entry_decision_input,
    load_rules_digest, discover_available_tools, discover_available_skills.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from ohmystock.swarm._adapters import (
    JournalStatsProvider,
    LiveJournalStatsProvider,
    LiveMarketSnapshotProvider,
    LivePortfolioSnapshotProvider,
    MarketSnapshot,
    MarketSnapshotProvider,
    PortfolioPosition,
    PortfolioSnapshot,
    PortfolioSnapshotProvider,
)
from ohmystock.swarm._discovery import (
    discover_available_skills,
    discover_available_tools,
)
from ohmystock.swarm._errors import (
    AssemblerInputError,
    LiveProviderError,
    RulesDigestError,
)
from ohmystock.swarm._live_candidate import (
    CandidateLiveSnapshot,
    live_candidate_snapshot,
)
from ohmystock.swarm._rules_digest import load_rules_digest
from ohmystock.swarm.models import (
    CandidateSnapshot,
    EntryDecisionInput,
    ExistingPosition,
    MarketContext,
    RulesDigest,
)
from ohmystock.swarm.runner import build_entry_decision_input


__all__ = [
    "AssemblerInputError",
    "CandidateLiveSnapshot",
    "CandidateSnapshot",
    "EntryDecisionInput",
    "ExistingPosition",
    "JournalStatsProvider",
    "LiveJournalStatsProvider",
    "LiveMarketSnapshotProvider",
    "LivePortfolioSnapshotProvider",
    "LiveProviderError",
    "MarketContext",
    "MarketSnapshot",
    "MarketSnapshotProvider",
    "PortfolioPosition",
    "PortfolioSnapshot",
    "PortfolioSnapshotProvider",
    "RulesDigest",
    "RulesDigestError",
    "build_entry_decision_input",
    "discover_available_skills",
    "discover_available_tools",
    "live_candidate_snapshot",
    "load_rules_digest",
]
