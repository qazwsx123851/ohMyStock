"""trust_5d_net_buy — chip sub-scorer (4 pts, banded).

Sums invest_trust_net (lots) over the last 5 trading days and awards points:

  net_5d <=    0    →  0 pts
  net_5d   1..100   →  1 pt
  net_5d 101..300   →  2 pts
  net_5d   >=301    →  4 pts (full)

Bands marked TODO(calibration); SEPA Golden Sample WFA tunes them later.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("trust_5d_net_buy sub-scorer" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer


_NEED_ROWS = 5
_MAX_POINTS = 4.0


def _band(net_lots: int) -> float:
    # TODO(calibration): re-tune via SEPA Golden Sample WFA after deferred
    # sub-scorers ship.
    if net_lots <= 0:
        return 0.0
    if net_lots <= 100:
        return 1.0
    if net_lots <= 300:
        return 2.0
    return 4.0


@register_subscorer(category="chip", name="trust_5d_net_buy", max_points=_MAX_POINTS)
def trust_5d_net_buy(ctx: ScoringContext) -> SubScoreResult:
    rows = ctx.three_major
    if len(rows) < _NEED_ROWS:
        return SubScoreResult(
            name="trust_5d_net_buy",
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
    net_5d = sum(int(r["invest_trust_net"]) for r in last_5)
    points = _band(net_5d)

    return SubScoreResult(
        name="trust_5d_net_buy",
        category="chip",
        points=points,
        max_points=_MAX_POINTS,
        status="scored",
        evidence={
            "net_5d_lots": net_5d,
            "rows_used": len(last_5),
        },
    )
