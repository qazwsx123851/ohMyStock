"""Tests for ohmystock.swarm_runs.storage — SQLite schema + helpers.

Spec: openspec/changes/admin-swarm-endpoints-and-pages/specs/swarm-runs/spec.md
      § "swarm_runs SQLite 表 schema 與 idempotent 創建"
"""

from __future__ import annotations

import sqlite3

import pytest

from ohmystock.swarm_runs.storage import (
    SwarmRunRowDict,
    init_schema,
    insert_run,
    select_by_id,
    select_recent,
)


def _make_row(
    *,
    id: str = "swr_abc123def456",
    preset: str = "phase5-review",
    status: str = "completed",
    params_json: str = '{"period_from":"2026-04-01"}',
    result_json: str = '{"node_outputs":{}}',
    elapsed_ms: int = 1234,
    created_at: str = "2026-05-13T12:00:00+08:00",
) -> SwarmRunRowDict:
    return SwarmRunRowDict(
        id=id,
        preset=preset,
        status=status,
        params_json=params_json,
        result_json=result_json,
        elapsed_ms=elapsed_ms,
        created_at=created_at,
    )


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    return c


def test_init_schema_idempotent_and_seven_columns() -> None:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    init_schema(c)  # second call must not raise
    cols = c.execute("PRAGMA table_info(swarm_runs)").fetchall()
    assert len(cols) == 7
    assert {row[1] for row in cols} == {
        "id",
        "preset",
        "status",
        "params_json",
        "result_json",
        "elapsed_ms",
        "created_at",
    }


def test_status_check_constraint_rejects_pending(conn: sqlite3.Connection) -> None:
    bad = _make_row(status="pending")
    with pytest.raises(sqlite3.IntegrityError):
        insert_run(conn, bad)


def test_id_primary_key_unique(conn: sqlite3.Connection) -> None:
    insert_run(conn, _make_row())
    with pytest.raises(sqlite3.IntegrityError):
        insert_run(conn, _make_row())  # same id by default


def test_select_by_id_round_trip(conn: sqlite3.Connection) -> None:
    row = _make_row()
    insert_run(conn, row)
    fetched = select_by_id(conn, row["id"])
    assert fetched == row


def test_select_by_id_missing_returns_none(conn: sqlite3.Connection) -> None:
    assert select_by_id(conn, "swr_doesnotexist") is None


def test_select_recent_orders_desc_with_limit(conn: sqlite3.Connection) -> None:
    insert_run(conn, _make_row(id="swr_aaa", created_at="2026-05-10T00:00:00+08:00"))
    insert_run(conn, _make_row(id="swr_bbb", created_at="2026-05-12T00:00:00+08:00"))
    insert_run(conn, _make_row(id="swr_ccc", created_at="2026-05-11T00:00:00+08:00"))
    rows = select_recent(conn, limit=2)
    assert [r["id"] for r in rows] == ["swr_bbb", "swr_ccc"]
