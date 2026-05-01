"""foreign_5d_net_buy — chip sub-scorer (5 pts, banded).

Sums foreign_net (lots) over the last 5 trading days of three_major data
and awards points per the SEPA-leaning band table:

  net_5d <=    0    →  0 pts
  net_5d   1..200   →  1 pt
  net_5d 201..500   →  2 pts
  net_5d 501..1000  →  3 pts
  net_5d   >=1001   →  5 pts

Bands marked TODO(calibration); SEPA Golden Sample WFA tunes them later.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("foreign_5d_net_buy sub-scorer" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer


_NEED_ROWS = 5
_MAX_POINTS = 5.0


def _band(net_lots: int) -> float:
    # TODO(calibration): re-tune via SEPA Golden Sample WFA after deferred
    # sub-scorers ship.
    if net_lots <= 0:
        return 0.0
    if net_lots <= 200:
        return 1.0
    if net_lots <= 500:
        return 2.0
    if net_lots <= 1000:
        return 3.0
    return 5.0


@register_subscorer(category="chip", name="foreign_5d_net_buy", max_points=_MAX_POINTS)
def foreign_5d_net_buy(ctx: ScoringContext) -> SubScoreResult:
    rows = ctx.three_major
    if len(rows) < _NEED_ROWS:
        return SubScoreResult(
            name="foreign_5d_net_buy",
            category="chip",
            points=0.0,
            max_points=_MAX_POINTS,
            status="skipped",
            evidence={
                "reason": "insufficient_three_major_rows",
                "have": len(rows),
                "need": _NEED_ROWS,
            },
        )

    last_5 = rows[-5:]
    net_5d = sum(int(r["foreign_net"]) for r in last_5)
    points = _band(net_5d)

    return SubScoreResult(
        name="foreign_5d_net_buy",
        category="chip",
        points=points,
        max_points=_MAX_POINTS,
        status="scored",
        evidence={
            "net_5d_lots": net_5d,
            "rows_used": len(last_5),
        },
    )
