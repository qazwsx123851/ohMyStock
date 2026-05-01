"""vcp_pivot — technical sub-scorer (8 pts, real implementation).

Pragmatic VCP / cup-handle / platform classifier emitting
``evidence["vcp_quality"] ∈ {none, forming, textbook, breakout}`` and
``evidence["pivot_price"]`` per design §D3.

Spec: openspec/changes/phase-2b-sepa-subscorers/specs/phase-2b-scoring-engine/spec.md
("vcp_pivot sub-scorer (real implementation)" requirement).
"""

from __future__ import annotations

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer


_NEED_BARS = 60
_MAX_POINTS = 8.0
_BREAKOUT_VOL_RATIO = 1.4
_TEXTBOOK_RANGE_PCT = 0.10
_FORMING_RANGE_PCT = 0.15
_TEXTBOOK_MIN_CONTRACTIONS = 2


def _count_lower_high_contractions(highs: list[float]) -> int:
    """Count strict lower-high "swings" within the supplied window.

    A swing high is a bar whose high is the local maximum within a 5-bar
    window centred on it. Contractions = pairs of consecutive swing highs
    where the later one is strictly lower.
    """
    if len(highs) < 5:
        return 0
    swings: list[float] = []
    for i in range(2, len(highs) - 2):
        h = highs[i]
        if (
            h > highs[i - 1]
            and h > highs[i - 2]
            and h > highs[i + 1]
            and h > highs[i + 2]
        ):
            swings.append(h)
    contractions = 0
    for i in range(1, len(swings)):
        if swings[i] < swings[i - 1]:
            contractions += 1
    return contractions


@register_subscorer(category="technical", name="vcp_pivot", max_points=_MAX_POINTS)
def vcp_pivot(ctx: ScoringContext) -> SubScoreResult:
    if len(ctx.bars) < _NEED_BARS:
        return SubScoreResult(
            name="vcp_pivot",
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
    volumes = [float(b["v"]) for b in bars]

    base_highs = highs[-20:]
    base_lows = lows[-20:]
    base_low = min(base_lows)
    base_high = max(base_highs)
    range_pct = (base_high - base_low) / base_low if base_low > 0 else float("inf")

    prior_19_highs = highs[-20:-1]
    prior_19_max = max(prior_19_highs) if prior_19_highs else float("-inf")
    last_close = closes[-1]
    last_volume = volumes[-1]

    # 20-DMA volume = average of the prior 20 bars (exclude today to avoid
    # self-bias on the breakout day).
    prior_20_vols = volumes[-21:-1]
    if len(prior_20_vols) == 20 and sum(prior_20_vols) > 0:
        avg_vol = sum(prior_20_vols) / 20
        volume_ratio: float | None = last_volume / avg_vol if avg_vol > 0 else None
    else:
        volume_ratio = None

    contractions = _count_lower_high_contractions(highs[-60:-20])

    is_breakout = (
        last_close > prior_19_max
        and volume_ratio is not None
        and volume_ratio >= _BREAKOUT_VOL_RATIO
    )

    if is_breakout:
        vcp_quality = "breakout"
        pivot_price: float | None = float(prior_19_max)
        points = 8.0
    elif (
        range_pct < _TEXTBOOK_RANGE_PCT
        and contractions >= _TEXTBOOK_MIN_CONTRACTIONS
    ):
        vcp_quality = "textbook"
        pivot_price = float(base_high)
        points = 6.0
    elif range_pct < _FORMING_RANGE_PCT:
        vcp_quality = "forming"
        pivot_price = None
        points = 3.0
    else:
        vcp_quality = "none"
        pivot_price = None
        points = 0.0

    return SubScoreResult(
        name="vcp_pivot",
        category="technical",
        points=points,
        max_points=_MAX_POINTS,
        status="scored",
        evidence={
            "vcp_quality": vcp_quality,
            "pivot_price": pivot_price,
            "range_pct": range_pct,
            "volume_ratio": volume_ratio,
            "contractions": contractions,
        },
    )
