"""Coverage for force-overwrite semantics on the Phase 5 pipeline.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
Requirement: --force 覆寫 reviews/<period>/ 既有檔案
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from ohmystock.review import FakeReviewLLM, ReviewAlreadyExistsError, run_review

from tests.review.conftest import StaticMarketData, insert_entry, insert_exit


_TPE = timezone(timedelta(hours=8))
_NOW = datetime(2026, 4, 30, 19, 30, tzinfo=_TPE)


def _critique_with_high() -> str:
    return (
        "### 高警示\n\n"
        "1. VCP 命中率僅 37.5% — 見 metrics.json#/by_pattern/VCP。\n\n"
        "### 中警示\n\n(無)\n\n### 觀察項\n\n(無)\n"
    )


def _proposal(topic: str = "vcp-volume-threshold") -> dict:
    return {
        "topic": topic,
        "target_section": "cheatsheet §6.4",
        "priority": "high",
        "description": "VCP 量能 1.5 → 1.3。",
        "motivation": "metrics.json#/by_pattern/VCP n=8 win_rate=0.375。",
        "diff_draft": "```diff\n- a\n+ b\n```",
        "expected_impact": "vcp.py。",
        "risk_assessment": "風險:過嚴漏 VCP。",
        "validation_plan": "WFA 5+1。",
        "expected_improvement": "0.565 → 0.60。",
    }


def _factory(proposal_topic: str = "vcp-volume-threshold"):
    fakes = {
        "attributor": FakeReviewLLM(
            responses=[
                {
                    "items": [
                        {
                            "decision_id": "dec-1",
                            "category": "thesis_held",
                            "evidence": "ev",
                        }
                    ]
                }
            ]
        ),
        "critic": FakeReviewLLM(responses=[_critique_with_high()]),
        "proposer": FakeReviewLLM(
            responses=[{"proposals": [_proposal(proposal_topic)]}]
        ),
    }

    def factory(node: str):
        return fakes[node]

    return factory


def _seed(conn, md: StaticMarketData) -> None:
    insert_entry(
        conn,
        decision_id="dec-1",
        symbol="2330",
        created_at="2026-04-15T14:00:00+08:00",
        actual_entry_price=100.0,
    )
    insert_exit(
        conn,
        decision_id="dec-1",
        symbol="2330",
        created_at="2026-04-22T13:30:00+08:00",
        actual_exit_price=106.0,
        exit_tag="hit_t1",
        pnl_pct=6.0,
    )
    md.responses[("2330", "2026-04-22")] = [105.0] * 21


def _common_run_kwargs(tmp_path, md, factory):
    cheatsheet = tmp_path / "cheatsheet.md"
    cheatsheet.write_text("cheatsheet", encoding="utf-8")
    return dict(
        out_dir=tmp_path / "reviews",
        proposals_dir=tmp_path / "proposals",
        market_data_loader=md,
        cheatsheet_path=cheatsheet,
        llm_factory=factory,
        now=_NOW,
    )


def test_default_refuses_to_overwrite(journal_conn, tmp_path) -> None:
    md = StaticMarketData()
    _seed(journal_conn, md)

    run_review(
        date(2026, 4, 1),
        date(2026, 4, 30),
        journal_conn,
        **_common_run_kwargs(tmp_path, md, _factory()),
    )

    with pytest.raises(ReviewAlreadyExistsError):
        run_review(
            date(2026, 4, 1),
            date(2026, 4, 30),
            journal_conn,
            **_common_run_kwargs(tmp_path, md, _factory()),
        )


def test_force_overwrites_review_but_not_proposals(journal_conn, tmp_path) -> None:
    md = StaticMarketData()
    _seed(journal_conn, md)
    kwargs = _common_run_kwargs(tmp_path, md, _factory())

    run_review(date(2026, 4, 1), date(2026, 4, 30), journal_conn, **kwargs)

    proposal_path = tmp_path / "proposals" / "2026-04-30-vcp-volume-threshold.md"
    proposal_path.write_text("HUMAN EDIT", encoding="utf-8")

    md2 = StaticMarketData()
    _seed(journal_conn, md2)
    kwargs2 = _common_run_kwargs(tmp_path, md2, _factory())
    kwargs2["force"] = True

    result = run_review(
        date(2026, 4, 1), date(2026, 4, 30), journal_conn, **kwargs2
    )

    assert proposal_path.read_text(encoding="utf-8") == "HUMAN EDIT"
    suffixed = tmp_path / "proposals" / "2026-04-30-vcp-volume-threshold-2.md"
    assert suffixed.exists()
    assert "2026-04-30-vcp-volume-threshold-2.md" in result.proposals_files
