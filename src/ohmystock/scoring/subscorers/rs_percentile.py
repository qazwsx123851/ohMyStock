"""rs_percentile — technical sub-scorer (7 pts).

Delegates the actual percentile calculation to ``ohmystock.sepa.rs`` so c8
in the trend template and this 7-pt sub-scorer share one number and one
SQLite cache (Decision 6 in
``openspec/changes/rs-percentile-skill/design.md``). This module only owns
the threshold mapping ``rs_rating -> 0/3/5/7 pts`` at ``65/80/90``.

Spec: openspec/specs/phase-2b-scoring-engine/spec.md
      ("rs_percentile sub-scorer (real implementation)" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer
from ohmystock.sepa.rs import compute_rs_rating


_MAX_POINTS = 7.0


def _points_for_rating(rs_rating: int) -> float:
    if rs_rating >= 90:
        return 7.0
    if rs_rating >= 80:
        return 5.0
    if rs_rating >= 65:
        return 3.0
    return 0.0


@register_subscorer(category="technical", name="rs_percentile", max_points=_MAX_POINTS)
def rs_percentile(ctx: ScoringContext) -> SubScoreResult:
    rs_rating = compute_rs_rating(ctx.symbol, ctx.asof_date)
    if rs_rating is None:
        return SubScoreResult(
            name="rs_percentile",
            category="technical",
            points=0.0,
            max_points=_MAX_POINTS,
            status="skipped",
            evidence={"reason": "rs_rating_unavailable", "symbol": ctx.symbol},
        )

    return SubScoreResult(
        name="rs_percentile",
        category="technical",
        points=_points_for_rating(rs_rating),
        max_points=_MAX_POINTS,
        status="scored",
        evidence={"rs_percentile": rs_rating},
    )
