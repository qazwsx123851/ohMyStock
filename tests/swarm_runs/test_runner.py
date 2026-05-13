"""Tests for ohmystock.swarm_runs.runner.run_swarm.

Spec: openspec/changes/admin-swarm-endpoints-and-pages/specs/swarm-runs/spec.md
      § "run_swarm 薄包裝 run_review 並 emit 5 個事件"
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import date, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from ohmystock.eventbus import bus
from ohmystock.review.pipeline import ReviewResult
from ohmystock.swarm_runs import runner as runner_mod
from ohmystock.swarm_runs.runner import SwarmRunnerError, run_swarm
from ohmystock.swarm_runs.storage import init_schema

_TPE = timezone(timedelta(hours=8))


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    return c


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    d = tmp_path / "reviews"
    d.mkdir()
    return d


@pytest.fixture
def proposals_dir(tmp_path: Path) -> Path:
    d = tmp_path / "proposals"
    d.mkdir()
    return d


@pytest.fixture
def cheatsheet_path(tmp_path: Path) -> Path:
    p = tmp_path / "cheatsheet.md"
    p.write_text("# cheatsheet", encoding="utf-8")
    return p


def _market_data_loader(symbol: str, start: date, end: date):  # type: ignore[no-untyped-def]
    return []


def _set_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef")


def _params() -> dict[str, Any]:
    return {
        "period_from": "2026-04-01",
        "period_to": "2026-04-30",
        "limit_trades": None,
        "dry_run": True,
        "force": False,
    }


def _drain_bus(spy_q) -> list[Any]:  # type: ignore[no-untyped-def]
    out = []
    while not spy_q.empty():
        out.append(spy_q.get_nowait())
    return out


def _good_review_result() -> ReviewResult:
    return ReviewResult(
        review_id="manual-2026-04-01-to-2026-04-30",
        period_from=date(2026, 4, 1),
        period_to=date(2026, 4, 30),
        trade_count=23,
        proposals_created=2,
        proposals_files=["2026-04-30-vcp.md", "2026-04-30-time-stop.md"],
        total_input_tokens=100,
        total_output_tokens=50,
        total_cost_usd=0.123456,
        out_dir="/tmp/reviews",
        proposals_dir="/tmp/proposals",
        dry_run=True,
    )


def test_happy_path_emits_12_events_and_writes_completed_row(
    conn: sqlite3.Connection,
    out_dir: Path,
    proposals_dir: Path,
    cheatsheet_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_api_key(monkeypatch)
    monkeypatch.setattr(
        runner_mod, "run_review", lambda **kw: _good_review_result()
    )
    spy_q = bus.subscribe()
    try:
        result = asyncio.run(
            run_swarm(
                "phase5-review",
                _params(),
                db_conn=conn,
                out_dir=out_dir,
                proposals_dir=proposals_dir,
                market_data_loader=_market_data_loader,
                cheatsheet_path=cheatsheet_path,
            )
        )
    finally:
        bus.unsubscribe(spy_q)

    assert result.status == "completed"
    assert result.run_id.startswith("swr_")
    assert len(result.run_id) == len("swr_") + 12

    events = _drain_bus(spy_q)
    types = [e.event_type for e in events]
    assert types == [
        "swarm_run_started",
        "swarm_node_started",  # data_loader
        "swarm_node_completed",  # data_loader
        "swarm_node_started",  # attributor
        "swarm_node_completed",
        "swarm_node_started",  # aggregator
        "swarm_node_completed",
        "swarm_node_started",  # critic
        "swarm_node_completed",
        "swarm_node_started",  # proposer
        "swarm_node_completed",
        "swarm_run_completed",
    ]
    assert all(e.payload["run_id"] == result.run_id for e in events)
    rows = conn.execute(
        "SELECT status FROM swarm_runs WHERE id = ?", (result.run_id,)
    ).fetchone()
    assert rows == ("completed",)


def test_mid_pipeline_failure_emits_run_failed_and_writes_failed_row(
    conn: sqlite3.Connection,
    out_dir: Path,
    proposals_dir: Path,
    cheatsheet_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_api_key(monkeypatch)

    review_dir = out_dir / "manual-2026-04-01-to-2026-04-30"
    review_dir.mkdir()
    (review_dir / "data.json").write_text("{}", encoding="utf-8")
    (review_dir / "attribution.json").write_text("{}", encoding="utf-8")

    def _boom(**kw):  # type: ignore[no-untyped-def]
        raise RuntimeError("aggregator boom")

    monkeypatch.setattr(runner_mod, "run_review", _boom)

    params = _params()
    params["dry_run"] = False

    spy_q = bus.subscribe()
    try:
        result = asyncio.run(
            run_swarm(
                "phase5-review",
                params,
                db_conn=conn,
                out_dir=out_dir,
                proposals_dir=proposals_dir,
                market_data_loader=_market_data_loader,
                cheatsheet_path=cheatsheet_path,
            )
        )
    finally:
        bus.unsubscribe(spy_q)

    assert result.status == "failed"
    assert result.result["failed_node"] == "aggregator"
    assert result.result["completed_nodes"] == ["data_loader", "attributor"]
    assert result.result["error"]["code"] == "RuntimeError"
    assert "aggregator boom" in result.result["error"]["message"]

    events = _drain_bus(spy_q)
    types = [e.event_type for e in events]
    assert types == [
        "swarm_run_started",
        "swarm_node_started",  # data_loader
        "swarm_node_completed",  # data_loader
        "swarm_node_started",  # attributor
        "swarm_node_completed",  # attributor
        "swarm_node_started",  # aggregator (failed)
        "swarm_run_failed",
    ]
    failed_event = events[-1]
    assert failed_event.payload["failed_node"] == "aggregator"

    row = conn.execute(
        "SELECT status, json_extract(result_json,'$.failed_node') "
        "FROM swarm_runs WHERE id = ?",
        (result.run_id,),
    ).fetchone()
    assert row == ("failed", "aggregator")


def test_missing_api_key_fail_fast_no_row_no_event(
    conn: sqlite3.Connection,
    out_dir: Path,
    proposals_dir: Path,
    cheatsheet_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    spy_q = bus.subscribe()
    try:
        with pytest.raises(SwarmRunnerError) as excinfo:
            asyncio.run(
                run_swarm(
                    "phase5-review",
                    _params(),
                    db_conn=conn,
                    out_dir=out_dir,
                    proposals_dir=proposals_dir,
                    market_data_loader=_market_data_loader,
                    cheatsheet_path=cheatsheet_path,
                )
            )
        assert str(excinfo.value).startswith("missing_api_key:")
    finally:
        bus.unsubscribe(spy_q)
    assert _drain_bus(spy_q) == []
    assert conn.execute("SELECT COUNT(*) FROM swarm_runs").fetchone()[0] == 0


def test_unknown_preset_raises_swarm_runner_error(
    conn: sqlite3.Connection,
    out_dir: Path,
    proposals_dir: Path,
    cheatsheet_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_api_key(monkeypatch)
    spy_q = bus.subscribe()
    try:
        with pytest.raises(SwarmRunnerError) as excinfo:
            asyncio.run(
                run_swarm(
                    "nonexistent",
                    {},
                    db_conn=conn,
                    out_dir=out_dir,
                    proposals_dir=proposals_dir,
                    market_data_loader=_market_data_loader,
                    cheatsheet_path=cheatsheet_path,
                )
            )
        assert str(excinfo.value).startswith("unknown_preset:")
    finally:
        bus.unsubscribe(spy_q)
    assert _drain_bus(spy_q) == []


def test_invalid_params_period_reversed(
    conn: sqlite3.Connection,
    out_dir: Path,
    proposals_dir: Path,
    cheatsheet_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_api_key(monkeypatch)
    bad = _params()
    bad["period_from"] = "2026-04-30"
    bad["period_to"] = "2026-04-01"
    with pytest.raises(SwarmRunnerError) as excinfo:
        asyncio.run(
            run_swarm(
                "phase5-review",
                bad,
                db_conn=conn,
                out_dir=out_dir,
                proposals_dir=proposals_dir,
                market_data_loader=_market_data_loader,
                cheatsheet_path=cheatsheet_path,
            )
        )
    assert str(excinfo.value).startswith("invalid_params:")
