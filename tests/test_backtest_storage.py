"""Unit tests for ``ohmystock.backtest.storage``.

Spec: openspec/changes/web-admin-backtest-pages/specs/admin-backtest-endpoints/spec.md
"""

from __future__ import annotations

import json
import sqlite3

from ohmystock.backtest.storage import (
    BacktestJobRow,
    init_schema,
    insert_job,
    select_by_id,
    select_recent,
)


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(":memory:")


def _row(
    *,
    id: str,
    created_at: str,
    status: str = "completed",
    result: dict | None = None,
) -> BacktestJobRow:
    payload = result if result is not None else {
        "metrics": {"cagr": 0.1, "sharpe": 1.0},
        "equity_curve": [{"date": "2024-01-02", "equity": 1_000_000.0}],
        "trades": [],
    }
    return BacktestJobRow(
        id=id,
        strategy="sma_cross",
        period_from="2024-01-01",
        period_to="2024-12-31",
        custom_symbols_json=json.dumps(["2330"]),
        initial_capital=1_000_000.0,
        status=status,
        elapsed_ms=123,
        result_json=json.dumps(payload),
        created_at=created_at,
    )


def test_init_schema_creates_table_and_index() -> None:
    conn = _conn()
    init_schema(conn)
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    indexes = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "backtest_jobs" in tables
    assert "idx_backtest_jobs_created_at" in indexes


def test_init_schema_is_idempotent() -> None:
    conn = _conn()
    init_schema(conn)
    init_schema(conn)
    init_schema(conn)
    cols = [
        r[1]
        for r in conn.execute("PRAGMA table_info(backtest_jobs)").fetchall()
    ]
    assert cols == [
        "id",
        "strategy",
        "period_from",
        "period_to",
        "custom_symbols_json",
        "initial_capital",
        "status",
        "elapsed_ms",
        "result_json",
        "created_at",
    ]


def test_insert_and_select_round_trip_preserves_payload() -> None:
    conn = _conn()
    init_schema(conn)
    payload = {
        "metrics": {"cagr": 0.18, "sharpe": 1.42, "max_drawdown": -0.083},
        "equity_curve": [
            {"date": "2024-01-02", "equity": 1_000_000.0},
            {"date": "2024-01-03", "equity": 1_005_000.0},
        ],
        "trades": [
            {
                "symbol": "2330",
                "side": "buy",
                "qty": 1000,
                "fill_price": 600.0,
                "status": "filled",
            }
        ],
    }
    insert_job(
        conn,
        _row(id="row-a", created_at="2026-05-08T10:00:00+08:00", result=payload),
    )

    fetched = select_by_id(conn, "row-a")
    assert fetched is not None
    assert fetched["id"] == "row-a"
    assert fetched["status"] == "completed"
    decoded = json.loads(fetched["result_json"])
    assert decoded == payload
    assert decoded["equity_curve"][1]["equity"] == 1_005_000.0
    assert decoded["trades"][0]["symbol"] == "2330"


def test_select_recent_orders_by_created_at_desc() -> None:
    conn = _conn()
    init_schema(conn)
    insert_job(conn, _row(id="r1", created_at="2026-05-01T10:00:00+08:00"))
    insert_job(conn, _row(id="r3", created_at="2026-05-08T10:00:00+08:00"))
    insert_job(conn, _row(id="r2", created_at="2026-05-04T10:00:00+08:00"))

    rows = select_recent(conn, limit=10)
    assert [r["id"] for r in rows] == ["r3", "r2", "r1"]


def test_select_recent_respects_limit() -> None:
    conn = _conn()
    init_schema(conn)
    for i in range(5):
        insert_job(
            conn,
            _row(id=f"r{i}", created_at=f"2026-05-0{i + 1}T10:00:00+08:00"),
        )
    rows = select_recent(conn, limit=3)
    assert len(rows) == 3
    assert rows[0]["id"] == "r4"


def test_select_by_id_returns_none_when_missing() -> None:
    conn = _conn()
    init_schema(conn)
    assert select_by_id(conn, "does-not-exist") is None


def test_failed_status_persists() -> None:
    conn = _conn()
    init_schema(conn)
    insert_job(
        conn,
        _row(
            id="failed-1",
            created_at="2026-05-08T10:00:00+08:00",
            status="failed",
            result={"error": {"code": "INVALID_INPUT", "message": "warmup"}},
        ),
    )
    fetched = select_by_id(conn, "failed-1")
    assert fetched is not None
    assert fetched["status"] == "failed"
    assert json.loads(fetched["result_json"])["error"]["code"] == "INVALID_INPUT"
