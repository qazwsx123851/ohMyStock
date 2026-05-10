"""Pydantic models for the Phase 5 post-trade review pipeline.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
SSOT: docs/post-trade-review-rubric.md §1 / §2 / §3

The five nodes share a single ``models`` module so the pipeline runner can
type-check the data flow with a single import and the JSON shapes match
the rubric byte-for-byte. All models are frozen + ``extra="forbid"``.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


_FROZEN = ConfigDict(frozen=True, extra="forbid")
_FROZEN_BY_NAME = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


AttributionCategory = Literal[
    "thesis_held",
    "thesis_failed_but_profit",
    "thesis_failed_loss",
    "stop_saved",
    "time_stop_correct",
    "time_stop_wrong",
]


class Period(BaseModel):
    model_config = _FROZEN_BY_NAME

    from_: date = Field(alias="from")
    to: date


# ---------------------------------------------------------------------------
# data_loader (rubric §1)
# ---------------------------------------------------------------------------


class TradeRow(BaseModel):
    model_config = _FROZEN

    decision_id: str
    symbol: str
    entry_ts: str
    exit_ts: str
    entry_price: float | None
    exit_price: float | None
    pnl_pct: float | None
    hold_days: int | None
    exit_tag: str | None
    thesis_held: bool | None
    post_exit_return_5d: float | None
    post_exit_return_10d: float | None
    post_exit_return_20d: float | None
    entry_thesis: str
    cited_skills: list[str]
    risk_flags_at_entry: list[str]
    confidence: float | None
    sector: str | None
    data_missing: bool


class RejectRow(BaseModel):
    model_config = _FROZEN

    decision_id: str
    symbol: str
    created_at: str
    reject_layer: str
    reject_reason: str


class ExpireRow(BaseModel):
    model_config = _FROZEN

    decision_id: str
    symbol: str
    created_at: str
    expire_reason: str


class DataLoaderStats(BaseModel):
    model_config = _FROZEN

    total_entries: int
    total_rejects: int
    total_expires: int
    expire_rate: float


class DataLoaderOutput(BaseModel):
    model_config = _FROZEN_BY_NAME

    period: Period
    trades: list[TradeRow]
    rejected: list[RejectRow]
    expired: list[ExpireRow]
    stats: DataLoaderStats


# ---------------------------------------------------------------------------
# attributor (rubric §2)
# ---------------------------------------------------------------------------


class AttributionRow(BaseModel):
    model_config = _FROZEN

    decision_id: str
    category: AttributionCategory
    evidence: str
    post_exit_return_5d: float | None
    rule_based: bool


class CategoryDistribution(BaseModel):
    model_config = _FROZEN

    thesis_held: int = 0
    thesis_failed_but_profit: int = 0
    thesis_failed_loss: int = 0
    stop_saved: int = 0
    time_stop_correct: int = 0
    time_stop_wrong: int = 0


class AttributionOutput(BaseModel):
    model_config = _FROZEN

    review_id: str
    attribution: list[AttributionRow]
    category_distribution: CategoryDistribution


# ---------------------------------------------------------------------------
# aggregator (rubric §3)
# ---------------------------------------------------------------------------


class OverallMetrics(BaseModel):
    model_config = _FROZEN

    total_trades: int
    win_rate: float
    profit_factor: float
    expectancy_pct: float
    max_drawdown_pct: float
    max_consecutive_loss: int
    avg_hold_days: float


class GroupMetrics(BaseModel):
    model_config = _FROZEN

    n: int
    win_rate: float
    expectancy: float


class ExitTagMetrics(BaseModel):
    model_config = _FROZEN

    count: int
    avg_pnl: float


class RejectionLayerMetrics(BaseModel):
    model_config = _FROZEN

    count: int
    top_reason: str | None


class MetricsOutput(BaseModel):
    model_config = _FROZEN

    overall: OverallMetrics
    by_skill: dict[str, GroupMetrics]
    by_pattern: dict[str, GroupMetrics]
    by_exit_tag: dict[str, ExitTagMetrics]
    by_confidence: dict[str, GroupMetrics]
    by_sector: dict[str, GroupMetrics]
    rejection_breakdown: dict[str, RejectionLayerMetrics]


# ---------------------------------------------------------------------------
# index (reviews/_index.json)
# ---------------------------------------------------------------------------


class IndexEntry(BaseModel):
    model_config = _FROZEN

    review_id: str
    kind: str
    period: Period
    trade_count: int
    win_rate: float
    pf: float
    proposals_created: int
    completed_at: str
