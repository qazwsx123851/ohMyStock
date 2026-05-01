"""Pydantic contracts for the Phase 2B → entry_decision_team input.

Shape SSOT: docs/llm-decision-schema.md §1 (v3.1).
Spec:       openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


VcpQuality = Literal["none", "forming", "textbook", "breakout"]
StageLiteral = Literal[1, 2, 3, 4]
SchemaVersion = Literal["v3.1"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False, strict=False)


class CandidateSnapshot(_Strict):
    symbol: str
    name: str
    final_score: int
    tech_score: int
    chip_score: int
    fundamental_score: int
    sentiment_score: int
    ema20_distance_pct: float
    atr_14_pct: float
    current_price: float
    stage: StageLiteral
    rs_percentile: int = Field(ge=0, le=99)
    trend_template_passed: int = Field(ge=0, le=8)
    vcp_quality: VcpQuality
    pivot_price: float | None
    distance_from_52w_high_pct: float
    distance_from_52w_low_pct: float

    @model_validator(mode="after")
    def _check_pivot_invariant(self) -> "CandidateSnapshot":
        needs_pivot = self.vcp_quality in ("textbook", "breakout")
        if needs_pivot and (self.pivot_price is None or self.pivot_price <= 0):
            raise ValueError(
                "pivot_price must be a positive float when "
                f"vcp_quality={self.vcp_quality!r}"
            )
        if not needs_pivot and self.pivot_price is not None:
            raise ValueError(
                "pivot_price must be None when "
                f"vcp_quality={self.vcp_quality!r}"
            )
        return self


class ExistingPosition(_Strict):
    symbol: str
    sector: str
    exposure_pct: float


class MarketContext(_Strict):
    risk_off: bool
    monthly_pnl_pct: float
    recent_20_winrate: float = Field(ge=0.0, le=1.0)
    consecutive_loss: int = Field(ge=0)
    existing_positions: list[ExistingPosition]
    total_exposure_pct: float
    same_sector_count: int = Field(ge=0)


class RulesDigest(_Strict):
    must_have: list[str]
    bonus_items: list[str]

    @model_validator(mode="after")
    def _check_counts(self) -> "RulesDigest":
        if len(self.must_have) != 3:
            raise ValueError(
                f"must_have must have exactly 3 entries, got {len(self.must_have)}"
            )
        if len(self.bonus_items) != 8:
            raise ValueError(
                f"bonus_items must have exactly 8 entries, got {len(self.bonus_items)}"
            )
        return self


class EntryDecisionInput(_Strict):
    input_schema_version: SchemaVersion = "v3.1"
    decision_id: str
    trigger_at: str
    candidate: CandidateSnapshot
    market_context: MarketContext
    rules_summary: RulesDigest
    available_tools: list[str]
    available_skills: list[str]
