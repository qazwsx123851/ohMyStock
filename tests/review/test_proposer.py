"""Coverage for review.nodes.proposer.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
Requirement: proposer 寫 0..N proposals 與 proposals_created.md
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ohmystock.review.llm_client import FakeReviewLLM
from ohmystock.review.models import (
    GroupMetrics,
    MetricsOutput,
    OverallMetrics,
    RejectionLayerMetrics,
)
from ohmystock.review.nodes.proposer import (
    ProposerOutputParseError,
    run_proposer,
)


_TPE = timezone(timedelta(hours=8))
_NOW = datetime(2026, 4, 30, 19, 30, tzinfo=_TPE)


def _metrics() -> MetricsOutput:
    return MetricsOutput(
        overall=OverallMetrics(
            total_trades=23,
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


def _critique_with_high_warning() -> str:
    return (
        "### 高警示\n\n"
        "1. VCP 命中率僅 37.5% — 見 metrics.json#/by_pattern/VCP。\n\n"
        "### 中警示\n\n(無)\n\n"
        "### 觀察項\n\n(無)\n"
    )


def _proposal_item(topic: str = "vcp-volume-threshold") -> dict:
    return {
        "topic": topic,
        "target_section": "cheatsheet §6.4",
        "priority": "high",
        "description": "VCP 量能門檻 1.5 → 1.3。",
        "motivation": "metrics.json#/by_pattern/VCP n=8 win_rate=0.375。",
        "diff_draft": "```diff\n- a\n+ b\n```",
        "expected_impact": "vcp.py。",
        "risk_assessment": "風險:過嚴漏 VCP。",
        "validation_plan": "WFA 5+1。",
        "expected_improvement": "0.565 → 0.60。",
    }


def test_zero_warnings_skips_llm(journal_conn, tmp_path) -> None:
    critique = (
        "### 高警示\n\n(無)\n\n"
        "### 中警示\n\n(無)\n\n"
        "### 觀察項\n\n半導體本月 win_rate 50%,樣本不足。\n"
    )
    llm = FakeReviewLLM(responses=[])
    out = run_proposer(
        critique,
        _metrics(),
        llm=llm,
        db_conn=journal_conn,
        review_id="r",
        proposals_dir=tmp_path,
        now=_NOW,
    )
    assert out.written_paths == []
    assert out.skipped == []
    assert "本期無提案" in out.proposals_created_md
    assert llm.calls == []
    assert list(tmp_path.iterdir()) == []


def test_writes_proposal_and_records_in_md(journal_conn, tmp_path) -> None:
    llm = FakeReviewLLM(
        responses=[{"proposals": [_proposal_item()]}], model="fake://proposer"
    )
    out = run_proposer(
        _critique_with_high_warning(),
        _metrics(),
        llm=llm,
        db_conn=journal_conn,
        review_id="manual-2026-04-01-to-2026-04-30",
        proposals_dir=tmp_path,
        now=_NOW,
    )
    assert len(out.written_paths) == 1
    written = out.written_paths[0]
    assert written.name == "2026-04-30-vcp-volume-threshold.md"
    body = written.read_text(encoding="utf-8")
    assert "status: pending" in body
    assert "## 1. 改動描述" in body
    assert out.skipped == []
    assert "[skipped: file exists]" not in out.proposals_created_md
    assert "vcp-volume-threshold" in out.proposals_created_md


def test_collision_marks_skipped_in_md(journal_conn, tmp_path) -> None:
    pre = tmp_path / "2026-04-30-vcp-volume-threshold.md"
    pre.write_text("placeholder", encoding="utf-8")

    llm = FakeReviewLLM(responses=[{"proposals": [_proposal_item()]}])
    out = run_proposer(
        _critique_with_high_warning(),
        _metrics(),
        llm=llm,
        db_conn=journal_conn,
        review_id="r",
        proposals_dir=tmp_path,
        now=_NOW,
    )
    assert len(out.written_paths) == 1
    assert out.written_paths[0].name == "2026-04-30-vcp-volume-threshold-2.md"
    assert out.skipped == ["2026-04-30-vcp-volume-threshold-2.md"]
    assert "[skipped: file exists]" in out.proposals_created_md
    assert pre.read_text(encoding="utf-8") == "placeholder"


def test_invalid_topic_raises(journal_conn, tmp_path) -> None:
    bad = _proposal_item(topic="VCP_volume_threshold")
    llm = FakeReviewLLM(responses=[{"proposals": [bad]}])
    with pytest.raises(ProposerOutputParseError):
        run_proposer(
            _critique_with_high_warning(),
            _metrics(),
            llm=llm,
            db_conn=journal_conn,
            review_id="r",
            proposals_dir=tmp_path,
            now=_NOW,
        )


def test_motivation_missing_pointer_raises(journal_conn, tmp_path) -> None:
    bad = _proposal_item()
    bad["motivation"] = "VCP 命中率太低,建議放寬。"
    llm = FakeReviewLLM(responses=[{"proposals": [bad]}])
    with pytest.raises(ProposerOutputParseError):
        run_proposer(
            _critique_with_high_warning(),
            _metrics(),
            llm=llm,
            db_conn=journal_conn,
            review_id="r",
            proposals_dir=tmp_path,
            now=_NOW,
        )
