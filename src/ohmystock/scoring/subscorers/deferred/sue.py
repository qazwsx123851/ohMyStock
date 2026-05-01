"""sue — sentiment sub-scorer (3 pts, deferred stub).

Returns status="skipped" until the underlying data source ships.

Spec: openspec/changes/phase-2b-deferred-cli/specs/phase-2b-scoring-engine/spec.md
("Deferred-stub sub-scorers register with `status=\"skipped\"`" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer


@register_subscorer(category="sentiment", name="sue", max_points=3.0)
def sue(ctx: ScoringContext) -> SubScoreResult:
    return SubScoreResult(
        name="sue",
        category="sentiment",
        points=0.0,
        max_points=3.0,
        status="skipped",
        evidence={"reason": "data source not implemented"},
    )
