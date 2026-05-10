"""Coverage for dry_run semantics on the Phase 5 pipeline.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
Requirement: dry_run 不落任何檔案
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from ohmystock.review import FakeReviewLLM, run_review

from tests.review.conftest import StaticMarketData, insert_entry, insert_exit


_TPE = timezone(timedelta(hours=8))
_NOW = datetime(2026, 4, 30, 19, 30, tzinfo=_TPE)


def _factory():
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
        "critic": FakeReviewLLM(
            responses=[
                "### 高警示\n\n(無)\n\n### 中警示\n\n(無)\n\n### 觀察項\n\n(無)\n"
            ]
        ),
        "proposer": FakeReviewLLM(responses=[]),
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


def test_dry_run_writes_no_files_or_index(journal_conn, tmp_path) -> None:
    md = StaticMarketData()
    _seed(journal_conn, md)
    cheatsheet = tmp_path / "cheatsheet.md"
    cheatsheet.write_text("cheatsheet", encoding="utf-8")
    out_dir = tmp_path / "reviews"
    proposals_dir = tmp_path / "proposals"

    result = run_review(
        date(2026, 4, 1),
        date(2026, 4, 30),
        journal_conn,
        out_dir=out_dir,
        proposals_dir=proposals_dir,
        market_data_loader=md,
        cheatsheet_path=cheatsheet,
        llm_factory=_factory(),
        now=_NOW,
        dry_run=True,
    )

    assert not (out_dir / "manual-2026-04-01-to-2026-04-30").exists()
    assert not (out_dir / "_index.json").exists()
    assert not proposals_dir.exists() or list(proposals_dir.iterdir()) == []

    rows = journal_conn.execute("SELECT COUNT(*) FROM llm_costs").fetchone()
    assert rows[0] == 0

    assert result.dry_run is True
    assert result.proposals_created == 0
    assert result.proposals_files == []
    assert result.total_input_tokens > 0
    assert result.total_output_tokens > 0
