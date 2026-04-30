"""Point-in-time Stage 1/2/3/4 classifier on daily bars (pure function).

Spec: openspec/changes/sepa-trend-template-and-stage/specs/sepa-stage-classification/spec.md
"""

from __future__ import annotations

from typing import Literal

from ohmystock.data.sources.base import BarRow
from ohmystock.sepa.trend_template import (
    _compute_ma_stack,
    _ma200_rising,
    _validate_history,
)
from ohmystock.sepa.types import (
    STAGE_3_RANGE_THRESHOLD,
    STAGE_RANGE_WINDOW,
    StageResult,
)


def _is_stage_4(
    last_close: float,
    ma50_last: float,
    ma150_last: float,
    ma200_last: float,
    ma200_series: list[float | None],
) -> tuple[bool, str]:
    mean_inverted = ma50_last < ma150_last < ma200_last
    close_below_ma50 = last_close < ma50_last
    rising_ok, _ = _ma200_rising(ma200_series)
    not_rising = not rising_ok
    matched = mean_inverted and close_below_ma50 and not_rising
    if matched:
        reason = (
            "Stage 4: MA50<MA150<MA200 "
            f"({ma50_last:.4f} < {ma150_last:.4f} < {ma200_last:.4f}); "
            f"close<MA50 ({last_close:.4f} < {ma50_last:.4f}); "
            "MA200 not rising over last 20 sessions"
        )
    else:
        reason = (
            f"not Stage 4: mean_inverted={mean_inverted}, "
            f"close_below_ma50={close_below_ma50}, ma200_not_rising={not_rising}"
        )
    return (matched, reason)


def _is_stage_2_or_3(
    last_close: float,
    ma50_last: float,
    ma150_last: float,
    ma200_last: float,
    ma200_series: list[float | None],
    bars: list[BarRow],
) -> tuple[Literal[2, 3] | None, str]:
    mean_stacked = last_close > ma50_last > ma150_last > ma200_last
    rising_ok, rising_detail = _ma200_rising(ma200_series)
    if not (mean_stacked and rising_ok):
        return (None, "")

    recent = bars[-STAGE_RANGE_WINDOW:]
    range_high = max(b["h"] for b in recent)
    range_low = min(b["l"] for b in recent)
    if last_close == 0:
        return (None, "")
    range_pct = (range_high - range_low) / last_close

    if range_pct > STAGE_3_RANGE_THRESHOLD:
        return (
            3,
            (
                f"Stage 3: mean stacked + MA200 rising, but {STAGE_RANGE_WINDOW}-day "
                f"high-low range = {range_pct * 100:.2f}% of close "
                f"(> {STAGE_3_RANGE_THRESHOLD * 100:.0f}% threshold); "
                f"high={range_high:.4f}, low={range_low:.4f}, close={last_close:.4f}"
            ),
        )
    return (
        2,
        (
            f"Stage 2: close>MA50>MA150>MA200 "
            f"({last_close:.4f} > {ma50_last:.4f} > {ma150_last:.4f} > {ma200_last:.4f}); "
            f"{rising_detail}; {STAGE_RANGE_WINDOW}-day range = "
            f"{range_pct * 100:.2f}% of close"
        ),
    )


def classify_stage(bars: list[BarRow]) -> StageResult:
    _validate_history(bars)

    closes = [b["c"] for b in bars]
    last_close = closes[-1]

    ma50, ma150, ma200 = _compute_ma_stack(closes)
    ma50_last = ma50[-1]
    ma150_last = ma150[-1]
    ma200_last = ma200[-1]
    assert ma50_last is not None
    assert ma150_last is not None
    assert ma200_last is not None

    matched_4, reason_4 = _is_stage_4(
        last_close, ma50_last, ma150_last, ma200_last, ma200
    )
    if matched_4:
        return StageResult(stage=4, reason=reason_4)

    stage_23, reason_23 = _is_stage_2_or_3(
        last_close, ma50_last, ma150_last, ma200_last, ma200, bars
    )
    if stage_23 == 2:
        return StageResult(stage=2, reason=reason_23)
    if stage_23 == 3:
        return StageResult(stage=3, reason=reason_23)

    return StageResult(
        stage=1,
        reason="Stage 1: no Stage 2/3/4 pattern detected (basing or neutral)",
    )


def is_stage_4_reject(bars: list[BarRow]) -> bool:
    return classify_stage(bars).stage == 4
