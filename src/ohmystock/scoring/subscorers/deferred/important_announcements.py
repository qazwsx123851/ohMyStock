"""important_announcements — sentiment sub-scorer (2 pts, deferred stub).

Returns status="skipped" until the underlying data source ships.

Spec: openspec/changes/phase-2b-deferred-cli/specs/phase-2b-scoring-engine/spec.md
("Deferred-stub sub-scorers register with `status=\"skipped\"`" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer


@register_subscorer(category="sentiment", name="important_announcements", max_points=2.0)
def important_announcements(ctx: ScoringContext) -> SubScoreResult:
    return SubScoreResult(
        name="important_announcements",
        category="sentiment",
        points=0.0,
        max_points=2.0,
        status="skipped",
        evidence={"reason": "data source not implemented"},
    )
