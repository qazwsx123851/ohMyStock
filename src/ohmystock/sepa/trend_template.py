"""8-condition Mark Minervini Trend Template evaluator (pure function).

Spec: openspec/changes/sepa-trend-template-and-stage/specs/sepa-trend-template/spec.md
"""

from __future__ import annotations

from ohmystock.data.sources.base import BarRow
from ohmystock.indicators.core import sma
from ohmystock.sepa.types import (
    HIGH_52W_DISCOUNT,
    LOW_52W_PREMIUM,
    MA200_SLOPE_WINDOW,
    MIN_HISTORY,
    RS_THRESHOLD,
    ConditionOutcome,
    InsufficientHistoryError,
    TrendTemplateResult,
)


def _validate_history(bars: list[BarRow]) -> None:
    if len(bars) < MIN_HISTORY:
        raise InsufficientHistoryError(
            f"need {MIN_HISTORY} bars, got {len(bars)}"
        )


def _compute_ma_stack(
    closes: list[float],
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    return (sma(closes, 50), sma(closes, 150), sma(closes, 200))


def _ma200_rising(
    ma200_series: list[float | None],
    window: int = MA200_SLOPE_WINDOW,
) -> tuple[bool, str]:
    n = len(ma200_series)
    start = n - window
    for i in range(start, n):
        prev = ma200_series[i - 1]
        curr = ma200_series[i]
        if prev is None or curr is None:
            return (False, f"MA200 undefined at index {i - 1} or {i}")
        if curr < prev:
            return (
                False,
                f"MA200 dipped at session offset -{n - 1 - i}: "
                f"{curr:.4f} < {prev:.4f}",
            )
    return (
        True,
        f"MA200 monotonically non-decreasing over last {window} sessions",
    )


def evaluate_trend_template(
    bars: list[BarRow],
    rs_percentile: float | None,
) -> TrendTemplateResult:
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

    c1 = ConditionOutcome(
        name="close > MA50",
        passed=last_close > ma50_last,
        detail=f"close={last_close:.4f}, MA50={ma50_last:.4f}",
    )
    c2 = ConditionOutcome(
        name="MA50 > MA150",
        passed=ma50_last > ma150_last,
        detail=f"MA50={ma50_last:.4f}, MA150={ma150_last:.4f}",
    )
    c3 = ConditionOutcome(
        name="MA150 > MA200",
        passed=ma150_last > ma200_last,
        detail=f"MA150={ma150_last:.4f}, MA200={ma200_last:.4f}",
    )
    c4 = ConditionOutcome(
        name="close > MA150",
        passed=last_close > ma150_last,
        detail=f"close={last_close:.4f}, MA150={ma150_last:.4f}",
    )
    c5 = ConditionOutcome(
        name="close > MA200",
        passed=last_close > ma200_last,
        detail=f"close={last_close:.4f}, MA200={ma200_last:.4f}",
    )

    rising_ok, rising_detail = _ma200_rising(ma200)
    c6 = ConditionOutcome(
        name="MA200 monotonically non-decreasing for last 20 sessions",
        passed=rising_ok,
        detail=rising_detail,
    )

    window = bars[-MIN_HISTORY:]
    high_52w = max(b["h"] for b in window)
    low_52w = min(b["l"] for b in window)

    high_threshold = high_52w * HIGH_52W_DISCOUNT
    discount_pct = 0.0 if high_52w == 0 else (high_52w - last_close) / high_52w * 100.0
    c7 = ConditionOutcome(
        name="close >= 52W high * 0.75 (within 25% of 52W high)",
        passed=last_close >= high_threshold,
        detail=(
            f"close={last_close:.4f}, 52W_high={high_52w:.4f}, "
            f"discount={discount_pct:.2f}%, threshold={high_threshold:.4f}"
        ),
    )

    low_threshold = low_52w * LOW_52W_PREMIUM
    if rs_percentile is None:
        c8 = ConditionOutcome(
            name="close >= 52W low * 1.30 AND RS Percentile >= 65",
            passed=None,
            detail="rs_percentile not provided",
        )
    else:
        low_pass = last_close >= low_threshold
        rs_pass = rs_percentile >= RS_THRESHOLD
        c8 = ConditionOutcome(
            name="close >= 52W low * 1.30 AND RS Percentile >= 65",
            passed=low_pass and rs_pass,
            detail=(
                f"close={last_close:.4f}, 52W_low={low_52w:.4f}, "
                f"low_threshold={low_threshold:.4f}, low_pass={low_pass}; "
                f"rs_percentile={rs_percentile:.2f}, "
                f"rs_threshold={RS_THRESHOLD:.2f}, rs_pass={rs_pass}"
            ),
        )

    conditions = {
        "c1": c1,
        "c2": c2,
        "c3": c3,
        "c4": c4,
        "c5": c5,
        "c6": c6,
        "c7": c7,
        "c8": c8,
    }
    overall_passed = all(o.passed is True for o in conditions.values())
    return TrendTemplateResult(
        passed=overall_passed,
        conditions=conditions,
        rs_percentile=rs_percentile,
    )
