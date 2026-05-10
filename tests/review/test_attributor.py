"""Coverage for review.nodes.attributor.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
Requirement: attributor 採 rule-first + LLM fallback 分類
"""

from __future__ import annotations

from datetime import date

import pytest

from ohmystock.review.llm_client import FakeReviewLLM
from ohmystock.review.models import (
    DataLoaderOutput,
    DataLoaderStats,
    Period,
    TradeRow,
)
from ohmystock.review.nodes.attributor import (
    AttributorOutputParseError,
    run_attributor,
)


def _trade(
    *,
    decision_id: str,
    exit_tag: str,
    pnl_pct: float = 6.0,
    post_exit_return_5d: float | None = 0.0,
    post_exit_return_10d: float | None = 0.0,
    post_exit_return_20d: float | None = 0.0,
    data_missing: bool = False,
) -> TradeRow:
    return TradeRow(
        decision_id=decision_id,
        symbol="2330",
        entry_ts="2026-04-15T14:00:00+08:00",
        exit_ts="2026-04-22T13:30:00+08:00",
        entry_price=100.0,
        exit_price=100.0 * (1 + pnl_pct / 100),
        pnl_pct=pnl_pct,
        hold_days=5,
        exit_tag=exit_tag,
        thesis_held=None,
        post_exit_return_5d=post_exit_return_5d,
        post_exit_return_10d=post_exit_return_10d,
        post_exit_return_20d=post_exit_return_20d,
        entry_thesis="t",
        cited_skills=["technical/breakout"],
        risk_flags_at_entry=[],
        confidence=0.75,
        sector="半導體",
        data_missing=data_missing,
    )


def _data_output(trades: list[TradeRow]) -> DataLoaderOutput:
    return DataLoaderOutput(
        period=Period.model_validate({"from": date(2026, 4, 1), "to": date(2026, 4, 30)}),
        trades=trades,
        rejected=[],
        expired=[],
        stats=DataLoaderStats(
            total_entries=len(trades),
            total_rejects=0,
            total_expires=0,
            expire_rate=0.0,
        ),
    )


def _llm_response(items: list[dict]) -> FakeReviewLLM:
    return FakeReviewLLM(responses=[{"items": items}], model="fake://attributor")


def test_time_stop_wrong_rule_path(journal_conn) -> None:
    trades = [
        _trade(
            decision_id="dec-ts-wrong",
            exit_tag="time_stop",
            pnl_pct=-1.0,
            post_exit_return_5d=0.062,
        ),
    ]
    llm = _llm_response(
        [{"decision_id": "dec-ts-wrong", "category": "thesis_held", "evidence": "ev"}]
    )
    out = run_attributor(
        _data_output(trades),
        llm=llm,
        db_conn=journal_conn,
        review_id="manual-x",
    )
    assert out.attribution[0].category == "time_stop_wrong"
    assert out.attribution[0].rule_based is True


def test_time_stop_correct_rule_path(journal_conn) -> None:
    trades = [
        _trade(
            decision_id="dec-ts-ok",
            exit_tag="time_stop",
            pnl_pct=-2.0,
            post_exit_return_5d=0.01,
        )
    ]
    llm = _llm_response(
        [{"decision_id": "dec-ts-ok", "category": "thesis_held", "evidence": "ev"}]
    )
    out = run_attributor(
        _data_output(trades), llm=llm, db_conn=journal_conn, review_id="r"
    )
    assert out.attribution[0].category == "time_stop_correct"


def test_stop_saved_rule_path(journal_conn) -> None:
    trades = [
        _trade(
            decision_id="dec-ss",
            exit_tag="hit_stop_loss",
            pnl_pct=-5.0,
            post_exit_return_10d=-0.083,
        )
    ]
    llm = _llm_response(
        [{"decision_id": "dec-ss", "category": "thesis_held", "evidence": "ev"}]
    )
    out = run_attributor(
        _data_output(trades), llm=llm, db_conn=journal_conn, review_id="r"
    )
    assert out.attribution[0].category == "stop_saved"


def test_thesis_invalid_loss_rule_path(journal_conn) -> None:
    trades = [
        _trade(
            decision_id="dec-ti",
            exit_tag="thesis_invalid",
            pnl_pct=-3.0,
        )
    ]
    llm = _llm_response(
        [{"decision_id": "dec-ti", "category": "stop_saved", "evidence": "ev"}]
    )
    out = run_attributor(
        _data_output(trades), llm=llm, db_conn=journal_conn, review_id="r"
    )
    assert out.attribution[0].category == "thesis_failed_loss"


def test_discretionary_falls_to_llm(journal_conn) -> None:
    trades = [_trade(decision_id="dec-d", exit_tag="discretionary", pnl_pct=2.0)]
    llm = _llm_response(
        [
            {
                "decision_id": "dec-d",
                "category": "thesis_failed_but_profit",
                "evidence": "ev",
            }
        ]
    )
    out = run_attributor(
        _data_output(trades), llm=llm, db_conn=journal_conn, review_id="r"
    )
    assert out.attribution[0].category == "thesis_failed_but_profit"
    assert out.attribution[0].rule_based is False


def test_data_missing_forces_llm_even_for_rule_tag(journal_conn) -> None:
    trades = [
        _trade(
            decision_id="dec-dm",
            exit_tag="hit_t1",
            pnl_pct=6.0,
            data_missing=True,
        )
    ]
    llm = _llm_response(
        [{"decision_id": "dec-dm", "category": "thesis_held", "evidence": "ev"}]
    )
    out = run_attributor(
        _data_output(trades), llm=llm, db_conn=journal_conn, review_id="r"
    )
    assert out.attribution[0].rule_based is False


def test_invalid_category_raises(journal_conn) -> None:
    trades = [_trade(decision_id="dec-x", exit_tag="discretionary")]
    llm = FakeReviewLLM(
        responses=[
            {
                "items": [
                    {"decision_id": "dec-x", "category": "BOGUS", "evidence": "e"}
                ]
            }
        ]
    )
    with pytest.raises(AttributorOutputParseError):
        run_attributor(
            _data_output(trades),
            llm=llm,
            db_conn=journal_conn,
            review_id="r",
        )


def test_empty_trades_skips_llm(journal_conn) -> None:
    llm = FakeReviewLLM(responses=[])
    out = run_attributor(
        _data_output([]), llm=llm, db_conn=journal_conn, review_id="r"
    )
    assert out.attribution == []
    assert out.category_distribution.thesis_held == 0
    assert llm.calls == []
