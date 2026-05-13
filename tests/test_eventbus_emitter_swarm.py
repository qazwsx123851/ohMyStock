"""Bus-resilience tests for the swarm runner emitter.

Spec: openspec/changes/admin-swarm-endpoints-and-pages/specs/eventbus-emitters/spec.md
      § "Swarm runner emitter"
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from ohmystock.eventbus import bus
from ohmystock.review.pipeline import ReviewResult
from ohmystock.swarm_runs import runner as runner_mod
from ohmystock.swarm_runs.runner import run_swarm
from ohmystock.swarm_runs.storage import init_schema


def _good_review_result() -> ReviewResult:
    return ReviewResult(
        review_id="manual-2026-04-01-to-2026-04-30",
        period_from=date(2026, 4, 1),
        period_to=date(2026, 4, 30),
        trade_count=0,
        proposals_created=0,
        proposals_files=[],
        total_input_tokens=0,
        total_output_tokens=0,
        total_cost_usd=0.0,
        out_dir="/tmp/r",
        proposals_dir="/tmp/p",
        dry_run=True,
    )


def _params() -> dict[str, Any]:
    return {
        "period_from": "2026-04-01",
        "period_to": "2026-04-30",
        "limit_trades": None,
        "dry_run": True,
        "force": False,
    }


def test_bus_emit_failure_does_not_break_runner_main_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef")
    monkeypatch.setattr(
        runner_mod, "run_review", lambda **kw: _good_review_result()
    )

    async def _raise_boom(event):  # type: ignore[no-untyped-def]
        raise RuntimeError("bus down")

    monkeypatch.setattr(bus, "emit", _raise_boom)

    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    out_dir = tmp_path / "reviews"
    out_dir.mkdir()
    proposals_dir = tmp_path / "proposals"
    proposals_dir.mkdir()
    cheatsheet = tmp_path / "cheat.md"
    cheatsheet.write_text("x", encoding="utf-8")

    result = asyncio.run(
        run_swarm(
            "phase5-review",
            _params(),
            db_conn=conn,
            out_dir=out_dir,
            proposals_dir=proposals_dir,
            market_data_loader=lambda *a, **k: [],
            cheatsheet_path=cheatsheet,
        )
    )
    assert result.status == "completed"
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM swarm_runs WHERE status='completed'"
        ).fetchone()[0]
        == 1
    )
