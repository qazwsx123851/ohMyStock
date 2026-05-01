"""Pydantic contracts for Phase 2B scoring.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SubScoreCategory = Literal["technical", "chip", "fundamental", "sentiment"]
SubScoreStatus = Literal["scored", "skipped", "error"]
Classification = Literal["green", "yellow", "red"]


class SubScoreResult(BaseModel):
    name: str
    category: SubScoreCategory
    points: float
    max_points: float
    status: SubScoreStatus
    evidence: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None


class Phase2BCandidate(BaseModel):
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
