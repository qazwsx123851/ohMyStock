"""monthly_revenue_yoy — fundamental sub-scorer (6 pts, deferred stub).

Returns status="skipped" until the underlying data source ships.

Spec: openspec/changes/phase-2b-deferred-cli/specs/phase-2b-scoring-engine/spec.md
("Deferred-stub sub-scorers register with `status=\"skipped\"`" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer


@register_subscorer(category="fundamental", name="monthly_revenue_yoy", max_points=6.0)
def monthly_revenue_yoy(ctx: ScoringContext) -> SubScoreResult:
    return SubScoreResult(
        name="monthly_revenue_yoy",
        category="fundamental",
        points=0.0,
        max_points=6.0,
        status="skipped",
        evidence={"reason": "data source not implemented"},
    )
