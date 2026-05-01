"""rs_percentile — technical sub-scorer (7 pts, real implementation).

IBD-style 252-day weighted relative strength against a swappable TWSE+OTC
universe (default = 5-symbol seed). Awards 3/5/7 pts at the 65/80/90
percentile thresholds (cheatsheet §6.3 + §6.4).

Spec: openspec/changes/phase-2b-sepa-subscorers/specs/phase-2b-scoring-engine/spec.md
("rs_percentile sub-scorer (real implementation)" requirement).
"""

from __future__ import annotations

from ohmystock.scoring._rs_universe import get_rs_universe_loader
from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer


_NEED_BARS = 252
_MAX_POINTS = 7.0


def _pct_change(closes: list[float], lookback: int) -> float | None:
    """Return (closes[-1] / closes[-lookback]) - 1.

    Uses the close ``lookback`` bars before the end as the base — i.e. with
    ``lookback=252`` and 252 bars, the base is ``closes[0]`` (the IBD
    "year-ago" close). Returns None if ``len(closes) < lookback`` or the base
    is non-positive.
    """
    if len(closes) < lookback:
        return None
    base = closes[-lookback]
    if base <= 0:
        return None
    return (closes[-1] / base) - 1.0


def _weighted_return(closes: list[float]) -> float | None:
    """0.4×63d + 0.2×126d + 0.2×189d + 0.2×252d, or None if any leg missing."""
    legs = [
        (0.4, _pct_change(closes, 63)),
        (0.2, _pct_change(closes, 126)),
        (0.2, _pct_change(closes, 189)),
        (0.2, _pct_change(closes, 252)),
    ]
    if any(r is None for _, r in legs):
        return None
    return sum(w * r for w, r in legs)  # type: ignore[operator]


def _percentile_rank(value: float, population: list[float]) -> float:
    """Fraction of population strictly below ``value`` plus half of those equal,
    in ``[0.0, 1.0]``. Empty population returns 0.5 (neutral)."""
    if not population:
        return 0.5
    below = sum(1 for x in population if x < value)
    equal = sum(1 for x in population if x == value)
    return (below + 0.5 * equal) / len(population)


@register_subscorer(category="technical", name="rs_percentile", max_points=_MAX_POINTS)
def rs_percentile(ctx: ScoringContext) -> SubScoreResult:
    if len(ctx.bars) < _NEED_BARS:
        return SubScoreResult(
            name="rs_percentile",
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

    candidate_closes = [float(b["c"]) for b in ctx.bars]
    candidate_ret = _weighted_return(candidate_closes)
    if candidate_ret is None:
        return SubScoreResult(
            name="rs_percentile",
            category="technical",
            points=0.0,
            max_points=_MAX_POINTS,
            status="skipped",
            evidence={"reason": "candidate_return_unavailable"},
        )

    universe = get_rs_universe_loader()()
    universe_returns: list[float] = []
    for _symbol, closes in universe:
        r = _weighted_return(list(closes))
        if r is not None:
            universe_returns.append(r)

    rank_frac = _percentile_rank(candidate_ret, universe_returns)
    rs_pct = int(round(rank_frac * 99))
    rs_pct = max(0, min(99, rs_pct))

    if rs_pct >= 90:
        points = 7.0
    elif rs_pct >= 80:
        points = 5.0
    elif rs_pct >= 65:
        points = 3.0
    else:
        points = 0.0

    return SubScoreResult(
        name="rs_percentile",
        category="technical",
        points=points,
        max_points=_MAX_POINTS,
        status="scored",
        evidence={
            "rs_percentile": rs_pct,
            "weighted_return": candidate_ret,
            "universe_size": len(universe_returns),
        },
    )
