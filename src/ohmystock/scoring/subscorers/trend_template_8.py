"""trend_template_8 — technical sub-scorer (5 pts, all-or-nothing).

Mark Minervini's SEPA Trend Template, conditions 1-7 (the 8th — RS Rank ≥ 70 —
is deferred to the RS Percentile sub-scorer). Awards 5 points only when all
seven hold.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("trend_template_8 sub-scorer" requirement).
"""

from __future__ import annotations

from ohmystock.indicators.core import sma
from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer


_NEED_BARS = 252
_MAX_POINTS = 5.0


@register_subscorer(category="technical", name="trend_template_8", max_points=_MAX_POINTS)
def trend_template_8(ctx: ScoringContext) -> SubScoreResult:
    if len(ctx.bars) < _NEED_BARS:
        return SubScoreResult(
            name="trend_template_8",
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

    bars = ctx.bars
    closes = [float(b["c"]) for b in bars]
    highs = [float(b["h"]) for b in bars]
    lows = [float(b["l"]) for b in bars]

    close = closes[-1]
    ma50 = sma(closes, 50)[-1]
    ma150 = sma(closes, 150)[-1]
    ma200_series = sma(closes, 200)
    ma200 = ma200_series[-1]
    ma200_22ago = ma200_series[-23]
    high_52w = max(highs[-252:])
    low_52w = min(lows[-252:])

    cond1 = close > ma150 and close > ma200
    cond2 = ma150 > ma200
    cond3 = ma200_22ago is not None and ma200 > ma200_22ago
    cond4 = ma50 > ma150 and ma50 > ma200
    cond5 = close > ma50
    cond6 = close >= 1.30 * low_52w
    cond7 = close >= 0.75 * high_52w

    conds = [cond1, cond2, cond3, cond4, cond5, cond6, cond7]
    passed = sum(1 for c in conds if c)
    points = _MAX_POINTS if passed == 7 else 0.0

    return SubScoreResult(
        name="trend_template_8",
        category="technical",
        points=points,
        max_points=_MAX_POINTS,
        status="scored",
        evidence={
            "cond1": bool(cond1),
            "cond2": bool(cond2),
            "cond3": bool(cond3),
            "cond4": bool(cond4),
            "cond5": bool(cond5),
            "cond6": bool(cond6),
            "cond7": bool(cond7),
            "conditions_passed": passed,
            "of": 7,
            "close": close,
            "ma50": ma50,
            "ma150": ma150,
            "ma200": ma200,
            "high_52w": high_52w,
            "low_52w": low_52w,
        },
    )
