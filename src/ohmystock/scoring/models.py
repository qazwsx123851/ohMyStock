"""Pydantic contracts for Phase 2B scoring.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
      openspec/changes/phase-2b-swarm-input-assembler/specs/phase-2b-scoring-engine/spec.md
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SubScoreCategory = Literal["technical", "chip", "fundamental", "sentiment"]
SubScoreStatus = Literal["scored", "skipped", "error"]
Classification = Literal["green", "yellow", "red"]
VcpQuality = Literal["none", "forming", "textbook", "breakout"]
StageLiteral = Literal[1, 2, 3, 4]


class SubScoreResult(BaseModel):
    name: str
    category: SubScoreCategory
    points: float
    max_points: float
    status: SubScoreStatus
    evidence: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None


class Phase2BCandidate(BaseModel):
    """Phase 2B scored candidate.

    SEPA fields (``stage`` / ``rs_percentile`` / ``trend_template_passed`` /
    ``vcp_quality`` / ``pivot_price``) are optional on the model itself —
    sub-scorers populate them when they have enough data. The swarm input
    assembler enforces their presence at consumption time.
    """

    symbol: str
    asof_date: str
    final_score: float
    tech_subtotal: float
    chip_subtotal: float
    fund_subtotal: float
    sent_subtotal: float
    classification: Classification
    risk_off_applied: bool
    subscores: list[SubScoreResult]

    stage: StageLiteral | None = None
    rs_percentile: int | None = Field(default=None, ge=0, le=99)
    trend_template_passed: int | None = Field(default=None, ge=0, le=8)
    vcp_quality: VcpQuality | None = None
    pivot_price: float | None = None
