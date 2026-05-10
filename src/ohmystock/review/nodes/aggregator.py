"""Phase 5 aggregator node — pure-data, no LLM.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
SSOT: docs/post-trade-review-rubric.md §3
"""

from __future__ import annotations

from collections import Counter, defaultdict

from ohmystock.review.models import (
    AttributionOutput,
    DataLoaderOutput,
    ExitTagMetrics,
    GroupMetrics,
    MetricsOutput,
    OverallMetrics,
    RejectionLayerMetrics,
    TradeRow,
)


_CONFIDENCE_BUCKETS: list[tuple[str, float, float]] = [
    ("0.6-0.7", 0.6, 0.7),
    ("0.7-0.8", 0.7, 0.8),
    ("0.8-0.9", 0.8, 0.9),
    ("0.9-1.0", 0.9, 1.0001),
]
_REJECTION_LAYERS: tuple[str, ...] = ("pre_check", "llm", "risk_gate", "human")
_PCT_DECIMALS = 4


def run_aggregator(
    data_output: DataLoaderOutput,
    attribution_output: AttributionOutput | None = None,
) -> MetricsOutput:
    """Compute the 7-dimension metrics payload.

    ``attribution_output`` is accepted for future use; v0 only reads
    ``data_output``.
    """

    trades = list(data_output.trades)

    overall = _compute_overall(trades)
    by_skill = _group_by_skill(trades)
    by_pattern: dict[str, GroupMetrics] = {}
    by_exit_tag = _group_by_exit_tag(trades)
    by_confidence = _group_by_confidence(trades)
    by_sector = _group_by_sector(trades)
    rejection_breakdown = _compute_rejection_breakdown(data_output)

    return MetricsOutput(
        overall=overall,
        by_skill=by_skill,
        by_pattern=by_pattern,
        by_exit_tag=by_exit_tag,
        by_confidence=by_confidence,
        by_sector=by_sector,
        rejection_breakdown=rejection_breakdown,
    )


def _compute_overall(trades: list[TradeRow]) -> OverallMetrics:
    n = len(trades)
    if n == 0:
        return OverallMetrics(
            total_trades=0,
            win_rate=0.0,
            profit_factor=0.0,
            expectancy_pct=0.0,
            max_drawdown_pct=0.0,
            max_consecutive_loss=0,
            avg_hold_days=0.0,
        )

    pnls = [t.pnl_pct for t in trades if t.pnl_pct is not None]
    if not pnls:
        return OverallMetrics(
            total_trades=n,
            win_rate=0.0,
            profit_factor=0.0,
            expectancy_pct=0.0,
            max_drawdown_pct=0.0,
            max_consecutive_loss=0,
            avg_hold_days=0.0,
        )

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_rate = round(len(wins) / len(pnls), _PCT_DECIMALS)

    sum_pos = sum(wins)
    sum_neg_abs = abs(sum(losses))
    profit_factor = round(sum_pos / sum_neg_abs, 2) if sum_neg_abs > 0 else 0.0
    expectancy_pct = round(sum(pnls) / len(pnls), _PCT_DECIMALS)

    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cum += p
        if cum > peak:
            peak = cum
        dd = cum - peak
        if dd < max_dd:
            max_dd = dd
    max_drawdown_pct = round(max_dd, _PCT_DECIMALS)

    max_consecutive_loss = 0
    cur = 0
    for p in pnls:
        if p <= 0:
            cur += 1
            if cur > max_consecutive_loss:
                max_consecutive_loss = cur
        else:
            cur = 0

    holds = [t.hold_days for t in trades if t.hold_days is not None]
    avg_hold_days = round(sum(holds) / len(holds), _PCT_DECIMALS) if holds else 0.0

    return OverallMetrics(
        total_trades=n,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy_pct=expectancy_pct,
        max_drawdown_pct=max_drawdown_pct,
        max_consecutive_loss=max_consecutive_loss,
        avg_hold_days=avg_hold_days,
    )


def _group_by_skill(trades: list[TradeRow]) -> dict[str, GroupMetrics]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        if t.pnl_pct is None:
            continue
        for skill in t.cited_skills:
            buckets[skill].append(t.pnl_pct)
    return {k: _group_metrics(v) for k, v in sorted(buckets.items())}


def _group_by_exit_tag(trades: list[TradeRow]) -> dict[str, ExitTagMetrics]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        if t.exit_tag is None or t.pnl_pct is None:
            continue
        buckets[t.exit_tag].append(t.pnl_pct)
    return {
        k: ExitTagMetrics(
            count=len(v),
            avg_pnl=round(sum(v) / len(v), _PCT_DECIMALS),
        )
        for k, v in sorted(buckets.items())
    }


def _group_by_confidence(trades: list[TradeRow]) -> dict[str, GroupMetrics]:
    out: dict[str, GroupMetrics] = {}
    for label, lo, hi in _CONFIDENCE_BUCKETS:
        bucket = [
            t.pnl_pct
            for t in trades
            if t.pnl_pct is not None
            and t.confidence is not None
            and lo <= t.confidence < hi
        ]
        out[label] = (
            _group_metrics(bucket)
            if bucket
            else GroupMetrics(n=0, win_rate=0.0, expectancy=0.0)
        )
    return out


def _group_by_sector(trades: list[TradeRow]) -> dict[str, GroupMetrics]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        if t.sector is None or t.pnl_pct is None:
            continue
        buckets[t.sector].append(t.pnl_pct)
    return {k: _group_metrics(v) for k, v in sorted(buckets.items())}


def _group_metrics(pnls: list[float]) -> GroupMetrics:
    n = len(pnls)
    wins = [p for p in pnls if p > 0]
    win_rate = round(len(wins) / n, _PCT_DECIMALS) if n > 0 else 0.0
    expectancy = round(sum(pnls) / n, _PCT_DECIMALS) if n > 0 else 0.0
    return GroupMetrics(n=n, win_rate=win_rate, expectancy=expectancy)


def _compute_rejection_breakdown(
    data_output: DataLoaderOutput,
) -> dict[str, RejectionLayerMetrics]:
    by_layer: dict[str, list[str]] = defaultdict(list)
    for r in data_output.rejected:
        by_layer[r.reject_layer].append(r.reject_reason)

    out: dict[str, RejectionLayerMetrics] = {}
    for layer in _REJECTION_LAYERS:
        reasons = by_layer.get(layer, [])
        top_reason: str | None = (
            Counter(reasons).most_common(1)[0][0] if reasons else None
        )
        out[layer] = RejectionLayerMetrics(count=len(reasons), top_reason=top_reason)
    return out
