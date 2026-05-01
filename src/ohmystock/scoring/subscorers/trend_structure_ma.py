"""trend_structure_ma — technical sub-scorer (10 pts, all-or-nothing).

Awards 10 points when close > 5MA AND 5MA > 20MA AND 20MA > 60MA, else 0.
Skipped when fewer than 60 bars are available.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("trend_structure_ma sub-scorer" requirement).
"""

from __future__ import annotations

from ohmystock.indicators.core import sma
from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer


_NEED_BARS = 60
_MAX_POINTS = 10.0


@register_subscorer(category="technical", name="trend_structure_ma", max_points=_MAX_POINTS)
def trend_structure_ma(ctx: ScoringContext) -> SubScoreResult:
    if len(ctx.bars) < _NEED_BARS:
        return SubScoreResult(
            name="trend_structure_ma",
            category="technical",
            points=0.0,
            max_points=_MAX_POINTS,
            status="skipped",
            evidence={
                "reason": "insufficient_bars",
                "have": len(ctx.bars),
                "need": _NEED_BARS,
            },
        )

    closes = [float(b["c"]) for b in ctx.bars]
    ma5 = sma(closes, 5)[-1]
    ma20 = sma(closes, 20)[-1]
    ma60 = sma(closes, 60)[-1]
    close = closes[-1]

    conds = [close > ma5, ma5 > ma20, ma20 > ma60]
    passed = sum(1 for c in conds if c)
    points = _MAX_POINTS if passed == 3 else 0.0

    return SubScoreResult(
        name="trend_structure_ma",
        category="technical",
        points=points,
        max_points=_MAX_POINTS,
        status="scored",
        evidence={
            "close": close,
            "ma5": ma5,
            "ma20": ma20,
            "ma60": ma60,
            "conditions_passed": passed,
        },
    )
