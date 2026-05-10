"""Coverage for review.nodes.aggregator.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
Requirement: aggregator 算 7 維度 metrics deterministic
"""

from __future__ import annotations

from datetime import date

from ohmystock.review.models import (
    AttributionOutput,
    CategoryDistribution,
    DataLoaderOutput,
    DataLoaderStats,
    Period,
    RejectRow,
    TradeRow,
)
from ohmystock.review.nodes.aggregator import run_aggregator


def _trade(
    *,
    decision_id: str,
    pnl_pct: float,
    cited_skills: list[str] | None = None,
    exit_tag: str = "hit_t1",
    confidence: float = 0.75,
    sector: str | None = "半導體",
    hold_days: int = 5,
) -> TradeRow:
    return TradeRow(
        decision_id=decision_id,
        symbol="2330",
        entry_ts="2026-04-15T14:00:00+08:00",
        exit_ts="2026-04-22T13:30:00+08:00",
        entry_price=100.0,
        exit_price=100.0 * (1 + pnl_pct / 100),
        pnl_pct=pnl_pct,
        hold_days=hold_days,
        exit_tag=exit_tag,
        thesis_held=None,
        post_exit_return_5d=0.0,
        post_exit_return_10d=0.0,
        post_exit_return_20d=0.0,
        entry_thesis="t",
        cited_skills=cited_skills or ["technical/breakout"],
        risk_flags_at_entry=[],
        confidence=confidence,
        sector=sector,
        data_missing=False,
    )


def _data_output(
    trades: list[TradeRow], rejects: list[RejectRow] | None = None
) -> DataLoaderOutput:
    return DataLoaderOutput(
        period=Period.model_validate({"from": date(2026, 4, 1), "to": date(2026, 4, 30)}),
        trades=trades,
        rejected=rejects or [],
        expired=[],
        stats=DataLoaderStats(
            total_entries=len(trades),
            total_rejects=len(rejects or []),
            total_expires=0,
            expire_rate=0.0,
        ),
    )


def _attribution_output() -> AttributionOutput:
    return AttributionOutput(
        review_id="manual-2026-04-01-to-2026-04-30",
        attribution=[],
        category_distribution=CategoryDistribution(),
    )


def test_overall_win_rate_matches_spec_scenario() -> None:
    trades: list[TradeRow] = []
    for i in range(13):
        trades.append(_trade(decision_id=f"w-{i}", pnl_pct=6.5))
    for i in range(10):
        trades.append(_trade(decision_id=f"l-{i}", pnl_pct=-4.59))

    metrics = run_aggregator(_data_output(trades), _attribution_output())
    assert metrics.overall.total_trades == 23
    assert metrics.overall.win_rate == 0.5652


def test_profit_factor_basic() -> None:
    trades = [_trade(decision_id=f"w-{i}", pnl_pct=84.5 / 13) for i in range(13)]
    trades += [_trade(decision_id=f"l-{i}", pnl_pct=-45.9 / 10) for i in range(10)]
    metrics = run_aggregator(_data_output(trades), _attribution_output())
    assert metrics.overall.profit_factor == 1.84


def test_empty_trades_no_zero_division() -> None:
    metrics = run_aggregator(_data_output([]), _attribution_output())
    assert metrics.overall.total_trades == 0
    assert metrics.overall.win_rate == 0.0
    assert metrics.overall.profit_factor == 0.0
    assert metrics.overall.expectancy_pct == 0.0
    assert metrics.overall.max_drawdown_pct == 0.0
    assert metrics.overall.max_consecutive_loss == 0
    assert metrics.overall.avg_hold_days == 0.0
    assert "pre_check" in metrics.rejection_breakdown
    assert metrics.rejection_breakdown["pre_check"].count == 0
    assert metrics.rejection_breakdown["pre_check"].top_reason is None


def test_rejection_breakdown_always_four_layers() -> None:
    rejects = [
        RejectRow(
            decision_id="r1",
            symbol="9999",
            created_at="2026-04-10T09:00:00+08:00",
            reject_layer="pre_check",
            reject_reason="同產業已有 2 檔",
        ),
        RejectRow(
            decision_id="r2",
            symbol="8888",
            created_at="2026-04-11T09:00:00+08:00",
            reject_layer="llm",
            reject_reason="confidence < 0.6",
        ),
    ]
    metrics = run_aggregator(_data_output([], rejects), _attribution_output())
    keys = set(metrics.rejection_breakdown.keys())
    assert keys == {"pre_check", "llm", "risk_gate", "human"}
    assert metrics.rejection_breakdown["pre_check"].count == 1
    assert metrics.rejection_breakdown["pre_check"].top_reason == "同產業已有 2 檔"
    assert metrics.rejection_breakdown["risk_gate"].count == 0
    assert metrics.rejection_breakdown["human"].count == 0


def test_by_skill_uses_cited_skills() -> None:
    trades = [
        _trade(decision_id="w1", pnl_pct=6.0, cited_skills=["technical/breakout"]),
        _trade(decision_id="l1", pnl_pct=-4.0, cited_skills=["technical/breakout"]),
        _trade(decision_id="w2", pnl_pct=8.0, cited_skills=["chip/foreign-net-buy"]),
    ]
    metrics = run_aggregator(_data_output(trades), _attribution_output())
    assert metrics.by_skill["technical/breakout"].n == 2
    assert metrics.by_skill["technical/breakout"].win_rate == 0.5
    assert metrics.by_skill["chip/foreign-net-buy"].n == 1
    assert metrics.by_skill["chip/foreign-net-buy"].win_rate == 1.0


def test_by_confidence_buckets_present_even_when_empty() -> None:
    trades = [_trade(decision_id="w1", pnl_pct=6.0, confidence=0.85)]
    metrics = run_aggregator(_data_output(trades), _attribution_output())
    assert set(metrics.by_confidence.keys()) == {
        "0.6-0.7",
        "0.7-0.8",
        "0.8-0.9",
        "0.9-1.0",
    }
    assert metrics.by_confidence["0.8-0.9"].n == 1
    assert metrics.by_confidence["0.6-0.7"].n == 0
