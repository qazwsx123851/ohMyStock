"""Pure assembler — Phase2BCandidate + snapshots → EntryDecisionInput.

Strict mirror of ``docs/llm-decision-schema.md`` §1 v3.1. No I/O.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

import re

from ohmystock.scoring.models import Phase2BCandidate
from ohmystock.swarm._adapters import (
    JournalStatsProvider,
    MarketSnapshot,
    PortfolioSnapshot,
)
from ohmystock.swarm._errors import AssemblerInputError
from ohmystock.swarm.models import (
    CandidateSnapshot,
    EntryDecisionInput,
    ExistingPosition,
    MarketContext,
    RulesDigest,
)


_SCORE_THRESHOLD = 65.0
_TZ_OFFSET_RE = re.compile(r"[+-]\d{2}:\d{2}$")


def _normalize_trigger_at(iso: str) -> str:
    """Strip ``:`` and the trailing ``+HH:MM`` offset for filesystem-safe IDs."""
    if not isinstance(iso, str) or not iso:
        raise AssemblerInputError(f"trigger_at must be a non-empty string, got {iso!r}")
    if not _TZ_OFFSET_RE.search(iso):
        raise AssemblerInputError(
            f"trigger_at must include a timezone offset (+HH:MM), got {iso!r}"
        )

    without_offset = _TZ_OFFSET_RE.sub("", iso)
    return without_offset.replace(":", "-")


def _candidate_to_snapshot(
    candidate: Phase2BCandidate,
    *,
    name: str,
    current_price: float,
    ema20_distance_pct: float,
    atr_14_pct: float,
    distance_from_52w_high_pct: float,
    distance_from_52w_low_pct: float,
) -> CandidateSnapshot:
    if candidate.final_score < _SCORE_THRESHOLD:
        raise AssemblerInputError(
            f"score below threshold: {candidate.symbol} final_score="
            f"{candidate.final_score} < {_SCORE_THRESHOLD}"
        )

    sepa_fields = {
        "stage": candidate.stage,
        "rs_percentile": candidate.rs_percentile,
        "trend_template_passed": candidate.trend_template_passed,
        "vcp_quality": candidate.vcp_quality,
    }
    missing = [k for k, v in sepa_fields.items() if v is None]
    if missing:
        raise AssemblerInputError(
            f"candidate {candidate.symbol} missing SEPA field(s): {missing}"
        )

    return CandidateSnapshot(
        symbol=candidate.symbol,
        name=name,
        final_score=int(round(candidate.final_score)),
        tech_score=int(round(candidate.tech_subtotal)),
        chip_score=int(round(candidate.chip_subtotal)),
        fundamental_score=int(round(candidate.fund_subtotal)),
        sentiment_score=int(round(candidate.sent_subtotal)),
        ema20_distance_pct=float(ema20_distance_pct),
        atr_14_pct=float(atr_14_pct),
        current_price=float(current_price),
        stage=candidate.stage,  # type: ignore[arg-type]
        rs_percentile=int(candidate.rs_percentile),  # type: ignore[arg-type]
        trend_template_passed=int(candidate.trend_template_passed),  # type: ignore[arg-type]
        vcp_quality=candidate.vcp_quality,  # type: ignore[arg-type]
        pivot_price=candidate.pivot_price,
        distance_from_52w_high_pct=float(distance_from_52w_high_pct),
        distance_from_52w_low_pct=float(distance_from_52w_low_pct),
    )


def _build_market_context(
    candidate_sector: str,
    market: MarketSnapshot,
    portfolio: PortfolioSnapshot,
    journal_stats: JournalStatsProvider,
) -> MarketContext:
    sorted_positions = sorted(
        portfolio.positions,
        key=lambda p: (-float(p.exposure_pct), p.symbol),
    )
    existing = [
        ExistingPosition(symbol=p.symbol, sector=p.sector, exposure_pct=float(p.exposure_pct))
        for p in sorted_positions
    ]
    same_sector_count = sum(1 for p in sorted_positions if p.sector == candidate_sector)

    return MarketContext(
        risk_off=bool(market.risk_off),
        monthly_pnl_pct=float(market.monthly_pnl_pct),
        recent_20_winrate=float(journal_stats.recent_winrate(20)),
        consecutive_loss=int(journal_stats.consecutive_loss()),
        existing_positions=existing,
        total_exposure_pct=float(portfolio.total_exposure_pct),
        same_sector_count=same_sector_count,
    )


def assemble(
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
    """Build the v3.1 ``EntryDecisionInput`` payload.

    Pure: no network, no DB, no clock reads. ``trigger_at`` is supplied by
    the caller in ISO-8601 form with an explicit timezone offset.
    """
    snap = _candidate_to_snapshot(
        candidate,
        name=candidate_name,
        current_price=current_price,
        ema20_distance_pct=ema20_distance_pct,
        atr_14_pct=atr_14_pct,
        distance_from_52w_high_pct=distance_from_52w_high_pct,
        distance_from_52w_low_pct=distance_from_52w_low_pct,
    )
    market_ctx = _build_market_context(
        candidate_sector=candidate_sector,
        market=market,
        portfolio=portfolio,
        journal_stats=journal_stats,
    )

    decision_id = f"dec_{_normalize_trigger_at(trigger_at)}_{candidate.symbol}"

    return EntryDecisionInput(
        decision_id=decision_id,
        trigger_at=trigger_at,
        candidate=snap,
        market_context=market_ctx,
        rules_summary=rules_digest,
        available_tools=sorted({str(t) for t in available_tools}),
        available_skills=sorted({str(s) for s in available_skills}),
    )
