"""rs_percentile — technical sub-scorer (7 pts, deferred stub).

Returns status="skipped" until the underlying data source ships.

Spec: openspec/changes/phase-2b-deferred-cli/specs/phase-2b-scoring-engine/spec.md
("Deferred-stub sub-scorers register with `status=\"skipped\"`" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer


@register_subscorer(category="technical", name="rs_percentile", max_points=7.0)
def rs_percentile(ctx: ScoringContext) -> SubScoreResult:
    return SubScoreResult(
        name="rs_percentile",
        category="technical",
        points=0.0,
        max_points=7.0,
        status="skipped",
        evidence={"reason": "data source not implemented"},
    )
