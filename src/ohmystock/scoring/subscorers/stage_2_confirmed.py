"""stage_2_confirmed — technical sub-scorer (5 pts, all-or-nothing).

Stan Weinstein's Stage 2 confirmation: close above a rising 30-week MA
(approximated as 150-day MA on daily bars), within 25% of the 52-week high
and ≥30% above the 52-week low.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("stage_2_confirmed sub-scorer" requirement).
"""

from __future__ import annotations

from ohmystock.indicators.core import sma
from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer


_NEED_BARS = 252
_MAX_POINTS = 5.0


@register_subscorer(category="technical", name="stage_2_confirmed", max_points=_MAX_POINTS)
def stage_2_confirmed(ctx: ScoringContext) -> SubScoreResult:
    if len(ctx.bars) < _NEED_BARS:
        return SubScoreResult(
            name="stage_2_confirmed",
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
    highs = [float(b["h"]) for b in ctx.bars]
    lows = [float(b["l"]) for b in ctx.bars]
    close = closes[-1]

    ma150_series = sma(closes, 150)
    ma150 = ma150_series[-1]
    ma150_5ago = ma150_series[-6]
    high_52w = max(highs[-252:])
    low_52w = min(lows[-252:])

    cond1 = close > ma150
    cond2 = ma150_5ago is not None and ma150 > ma150_5ago
    cond3 = close >= 1.30 * low_52w
    cond4 = close >= 0.75 * high_52w

    conds = [cond1, cond2, cond3, cond4]
    passed = sum(1 for c in conds if c)
    points = _MAX_POINTS if passed == 4 else 0.0

    return SubScoreResult(
        name="stage_2_confirmed",
        category="technical",
        points=points,
        max_points=_MAX_POINTS,
        status="scored",
        evidence={
            "cond1": bool(cond1),
            "cond2": bool(cond2),
            "cond3": bool(cond3),
            "cond4": bool(cond4),
            "conditions_passed": passed,
            "close": close,
            "ma150": ma150,
            "ma150_5ago": ma150_5ago,
            "high_52w": high_52w,
            "low_52w": low_52w,
        },
    )
