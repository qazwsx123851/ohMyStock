"""Placeholder sub-scorer to keep the engine end-to-end testable.

Removed (file deleted) in the follow-on change `phase-2b-shipped-subscorers`.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
("Always-zero placeholder sub-scorer is registered" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer


@register_subscorer(category="technical", name="_always_zero_placeholder", max_points=0)
def _always_zero_placeholder(ctx: ScoringContext) -> SubScoreResult:
    return SubScoreResult(
        name="_always_zero_placeholder",
        category="technical",
        points=0.0,
        max_points=0.0,
        status="scored",
        evidence={"placeholder": True},
    )
