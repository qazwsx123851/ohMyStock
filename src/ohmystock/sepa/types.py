"""Frozen dataclasses + module-level constants for the SEPA package.

Spec: openspec/changes/sepa-trend-template-and-stage/specs/{sepa-trend-template,sepa-stage-classification}/spec.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MIN_HISTORY: int = 252
MA200_SLOPE_WINDOW: int = 20
STAGE_RANGE_WINDOW: int = 30
STAGE_3_RANGE_THRESHOLD: float = 0.20
RS_THRESHOLD: float = 65.0
HIGH_52W_DISCOUNT: float = 0.75
LOW_52W_PREMIUM: float = 1.30


class InsufficientHistoryError(ValueError):
    pass


@dataclass(frozen=True)
class ConditionOutcome:
    name: str
    passed: bool | None
    detail: str


@dataclass(frozen=True)
class TrendTemplateResult:
    passed: bool
    conditions: dict[str, ConditionOutcome]
    rs_percentile: float | None


@dataclass(frozen=True)
class StageResult:
    stage: Literal[1, 2, 3, 4]
    reason: str
