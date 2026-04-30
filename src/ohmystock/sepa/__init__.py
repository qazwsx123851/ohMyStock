"""SEPA framework primitives — Trend Template + Stage classifier.

Spec: openspec/changes/sepa-trend-template-and-stage/specs/{sepa-trend-template,sepa-stage-classification}/spec.md
"""

from ohmystock.sepa.stage import classify_stage, is_stage_4_reject
from ohmystock.sepa.trend_template import evaluate_trend_template
from ohmystock.sepa.types import (
    ConditionOutcome,
    InsufficientHistoryError,
    StageResult,
    TrendTemplateResult,
)

__all__ = [
    "evaluate_trend_template",
    "classify_stage",
    "is_stage_4_reject",
    "TrendTemplateResult",
    "ConditionOutcome",
    "StageResult",
    "InsufficientHistoryError",
]
