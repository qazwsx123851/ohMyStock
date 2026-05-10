"""End-to-end golden test for the Phase 5 pipeline.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
Requirement: 5 節點按順序呼叫且每節 output 落檔 / data_loader 重跑 byte-identical
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from ohmystock.review import FakeReviewLLM, run_review

from tests.review.conftest import StaticMarketData, insert_entry, insert_exit


_TPE = timezone(timedelta(hours=8))
_NOW = datetime(2026, 4, 30, 19, 30, tzinfo=_TPE)


def _critique_with_high() -> str:
    return (
        "### 高警示\n\n"
        "1. VCP 命中率僅 37.5% — 見 metrics.json#/by_pattern/VCP。\n\n"
        "### 中警示\n\n(無)\n\n### 觀察項\n\n(無)\n"
    )


def _proposal() -> dict:
    return {
        "topic": "vcp-volume-threshold",
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


def _make_factory():
    fakes = {
        "attributor": FakeReviewLLM(
            responses=[
                {
                    "items": [
                        {
                            "decision_id": "dec-1",
                            "category": "thesis_held",
                            "evidence": "rule path",
                        }
                    ]
                }
            ],
            model="fake://attributor",
        ),
        "critic": FakeReviewLLM(
            responses=[_critique_with_high()], model="fake://critic"
        ),
        "proposer": FakeReviewLLM(
            responses=[{"proposals": [_proposal()]}], model="fake://proposer"
        ),
    }

    def factory(node: str):
        return fakes[node]

    return factory, fakes


def _seed_journal(conn, market_data: StaticMarketData) -> None:
    insert_entry(
        conn,
        decision_id="dec-1",
        symbol="2330",
        created_at="2026-04-15T14:00:00+08:00",
        actual_entry_price=100.0,
        cited_skills=["technical/breakout"],
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
    market_data.responses[("2330", "2026-04-22")] = [105.0] * 21


def test_pipeline_writes_six_files_and_index(journal_conn, tmp_path) -> None:
    out_dir = tmp_path / "reviews"
    proposals_dir = tmp_path / "proposals"
    cheatsheet = tmp_path / "cheatsheet.md"
    cheatsheet.write_text("cheatsheet text", encoding="utf-8")
    md = StaticMarketData()
    _seed_journal(journal_conn, md)
    factory, _ = _make_factory()

    result = run_review(
        date(2026, 4, 1),
        date(2026, 4, 30),
        journal_conn,
        out_dir=out_dir,
        proposals_dir=proposals_dir,
        market_data_loader=md,
        cheatsheet_path=cheatsheet,
        llm_factory=factory,
        now=_NOW,
    )

    review_dir = out_dir / "manual-2026-04-01-to-2026-04-30"
    assert review_dir.is_dir()
    for name in (
        "data.json",
        "attribution.json",
        "metrics.json",
        "critique.md",
        "report.md",
        "proposals_created.md",
    ):
        assert (review_dir / name).exists(), f"missing {name}"

    assert (proposals_dir / "2026-04-30-vcp-volume-threshold.md").exists()

    index = json.loads((out_dir / "_index.json").read_text(encoding="utf-8"))
    assert len(index["reviews"]) == 1
    assert index["reviews"][0]["review_id"] == "manual-2026-04-01-to-2026-04-30"

    assert result.trade_count == 1
    assert result.proposals_created == 1
    assert "2026-04-30-vcp-volume-threshold.md" in result.proposals_files


def test_data_and_metrics_byte_identical_across_runs(journal_conn, tmp_path) -> None:
    out_dir1 = tmp_path / "r1"
    out_dir2 = tmp_path / "r2"
    cheatsheet = tmp_path / "cheatsheet.md"
    cheatsheet.write_text("cheatsheet", encoding="utf-8")
    md = StaticMarketData()
    _seed_journal(journal_conn, md)

    for out_dir in (out_dir1, out_dir2):
        factory, _ = _make_factory()
        run_review(
            date(2026, 4, 1),
            date(2026, 4, 30),
            journal_conn,
            out_dir=out_dir,
            proposals_dir=tmp_path / f"prop-{out_dir.name}",
            market_data_loader=md,
            cheatsheet_path=cheatsheet,
            llm_factory=factory,
            now=_NOW,
        )

    rid = "manual-2026-04-01-to-2026-04-30"
    for filename in ("data.json", "metrics.json"):
        b1 = (out_dir1 / rid / filename).read_bytes()
        b2 = (out_dir2 / rid / filename).read_bytes()
        assert b1 == b2, f"{filename} should be byte-identical across runs"
