"""Coverage for review.nodes.critic.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
Requirement: critic 寫 critique.md 並引用 metrics.json JSON pointer
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ohmystock.review.llm_client import FakeReviewLLM
from ohmystock.review.models import (
    GroupMetrics,
    MetricsOutput,
    OverallMetrics,
    RejectionLayerMetrics,
)
from ohmystock.review.nodes.critic import (
    CriticTokenBudgetExceededError,
    run_critic,
)


def _metrics(total_trades: int = 23) -> MetricsOutput:
    return MetricsOutput(
        overall=OverallMetrics(
            total_trades=total_trades,
            win_rate=0.5652,
            profit_factor=1.84,
            expectancy_pct=4.2,
            max_drawdown_pct=-3.8,
            max_consecutive_loss=2,
            avg_hold_days=6.2,
        ),
        by_skill={
            "technical/breakout": GroupMetrics(n=12, win_rate=0.5833, expectancy=5.1),
        },
        by_pattern={
            "VCP": GroupMetrics(n=8, win_rate=0.375, expectancy=-0.4),
        },
        by_exit_tag={},
        by_confidence={},
        by_sector={},
        rejection_breakdown={
            "pre_check": RejectionLayerMetrics(count=0, top_reason=None),
            "llm": RejectionLayerMetrics(count=0, top_reason=None),
            "risk_gate": RejectionLayerMetrics(count=0, top_reason=None),
            "human": RejectionLayerMetrics(count=0, top_reason=None),
        },
    )


def _cheatsheet(tmp_path: Path, content: str = "cheatsheet content\n") -> Path:
    p = tmp_path / "workflow-cheatsheet.md"
    p.write_text(content, encoding="utf-8")
    return p


def test_empty_metrics_returns_canned_critique_without_llm(journal_conn, tmp_path) -> None:
    llm = FakeReviewLLM(responses=[])
    out = run_critic(
        _metrics(total_trades=0),
        llm=llm,
        db_conn=journal_conn,
        review_id="r",
        cheatsheet_path=_cheatsheet(tmp_path),
    )
    assert "本期無交易" in out
    assert llm.calls == []


def test_jsonpointer_passes_through(journal_conn, tmp_path) -> None:
    canned = (
        "### 高警示\n\n1. VCP 命中率僅 37.5% — 見 metrics.json#/by_pattern/VCP\n\n"
        "### 中警示\n\n(無)\n\n### 觀察項\n\n(無)\n"
    )
    llm = FakeReviewLLM(responses=[canned], model="fake://critic")
    out = run_critic(
        _metrics(),
        llm=llm,
        db_conn=journal_conn,
        review_id="manual-2026-04-01-to-2026-04-30",
        cheatsheet_path=_cheatsheet(tmp_path),
    )
    assert "metrics.json#/by_pattern/VCP" in out
    rows = journal_conn.execute(
        "SELECT decision_id, model FROM llm_costs"
    ).fetchall()
    assert rows == [("manual-2026-04-01-to-2026-04-30", "fake://critic")]


def test_cache_blocks_include_cheatsheet(journal_conn, tmp_path) -> None:
    cheatsheet_text = "WORKFLOW CHEATSHEET BODY"
    llm = FakeReviewLLM(responses=["body"])
    run_critic(
        _metrics(),
        llm=llm,
        db_conn=journal_conn,
        review_id="r",
        cheatsheet_path=_cheatsheet(tmp_path, cheatsheet_text),
    )
    assert llm.calls[0]["cache_blocks"] == [cheatsheet_text]


def test_token_budget_exceeded_raises(journal_conn, tmp_path) -> None:
    huge = "x" * (80_000 * 3 + 10)
    llm = FakeReviewLLM(responses=["should not run"])
    with pytest.raises(CriticTokenBudgetExceededError):
        run_critic(
            _metrics(),
            llm=llm,
            db_conn=journal_conn,
            review_id="r",
            cheatsheet_path=_cheatsheet(tmp_path, huge),
        )
    assert llm.calls == []
