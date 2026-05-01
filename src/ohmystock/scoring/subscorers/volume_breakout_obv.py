"""volume_breakout_obv — technical sub-scorer (5 pts, all-or-nothing).

Awards 5 points when today's close breaks above the prior 20-day high AND
volume ≥ 1.4× the 20-day average AND 5-day OBV slope is positive.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("volume_breakout_obv sub-scorer" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer


_NEED_BARS = 21
_MAX_POINTS = 5.0
_VOLUME_RATIO_THRESHOLD = 1.4


def _obv_series(closes: list[float], volumes: list[int]) -> list[float]:
    obv = [0.0]
    for i in range(1, len(closes)):
        prev_c = closes[i - 1]
        c = closes[i]
        v = float(volumes[i])
        if c > prev_c:
            obv.append(obv[-1] + v)
        elif c < prev_c:
            obv.append(obv[-1] - v)
        else:
            obv.append(obv[-1])
    return obv


@register_subscorer(category="technical", name="volume_breakout_obv", max_points=_MAX_POINTS)
def volume_breakout_obv(ctx: ScoringContext) -> SubScoreResult:
    if len(ctx.bars) < _NEED_BARS:
        return SubScoreResult(
            name="volume_breakout_obv",
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
    volumes = [int(b["v"]) for b in bars]

    high_20d_prior = max(highs[-21:-1])
    close = closes[-1]
    vol_today = volumes[-1]
    avg_vol_20d = sum(volumes[-21:-1]) / 20.0
    volume_ratio = vol_today / avg_vol_20d if avg_vol_20d > 0 else 0.0

    obv = _obv_series(closes, volumes)
    obv_slope_5d = obv[-1] - obv[-6]

    breakout = close > high_20d_prior
    vol_ok = volume_ratio >= _VOLUME_RATIO_THRESHOLD
    obv_ok = obv_slope_5d > 0

    conds = [breakout, vol_ok, obv_ok]
    passed = sum(1 for c in conds if c)
    points = _MAX_POINTS if passed == 3 else 0.0

    return SubScoreResult(
        name="volume_breakout_obv",
        category="technical",
        points=points,
        max_points=_MAX_POINTS,
        status="scored",
        evidence={
            "breakout": bool(breakout),
            "volume_ratio": volume_ratio,
            "obv_slope_5d": obv_slope_5d,
            "conditions_passed": passed,
            "close": close,
            "high_20d_prior": high_20d_prior,
            "vol_today": vol_today,
            "avg_vol_20d": avg_vol_20d,
        },
    )
