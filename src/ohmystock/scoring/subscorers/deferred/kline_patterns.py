"""kline_patterns — technical sub-scorer (8 pts, deferred stub).

Returns status="skipped" until the K-line pattern detector data source ships.

Spec: openspec/changes/phase-2b-deferred-cli/specs/phase-2b-scoring-engine/spec.md
("Deferred-stub sub-scorers register with `status=\"skipped\"`" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer


@register_subscorer(category="technical", name="kline_patterns", max_points=8.0)
def kline_patterns(ctx: ScoringContext) -> SubScoreResult:
    return SubScoreResult(
        name="kline_patterns",
        category="technical",
        points=0.0,
        max_points=8.0,
        status="skipped",
        evidence={"reason": "data source not implemented"},
    )
