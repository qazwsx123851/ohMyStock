"""SQLite persistence for backtest jobs.

One row per ``run_backtest`` invocation: input echoed verbatim plus the
engine's ``data`` envelope serialised to JSON. ``status`` is ``completed``
when the engine returned ``ok=true``, ``failed`` when it returned
``ok=false`` (HTTP is still 200 — the row exists either way).

Spec: openspec/changes/web-admin-backtest-pages/specs/admin-backtest-endpoints/spec.md
"""

from __future__ import annotations

import sqlite3
from typing import Any, TypedDict


_DDL_BACKTEST_JOBS = """
CREATE TABLE IF NOT EXISTS backtest_jobs (
    id                    TEXT    PRIMARY KEY,
    strategy              TEXT    NOT NULL,
    period_from           TEXT    NOT NULL,
    period_to             TEXT    NOT NULL,
    custom_symbols_json   TEXT    NOT NULL,
    initial_capital       REAL    NOT NULL,
    status                TEXT    NOT NULL CHECK(status IN ('completed','failed')),
    elapsed_ms            INTEGER NOT NULL,
    result_json           TEXT    NOT NULL,
    created_at            TEXT    NOT NULL
)
""".strip()

_DDL_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_backtest_jobs_created_at "
    "ON backtest_jobs(created_at)"
)


class BacktestJobRow(TypedDict):
    id: str
    strategy: str
    period_from: str
    period_to: str
    custom_symbols_json: str
    initial_capital: float
    status: str
    elapsed_ms: int
    result_json: str
    created_at: str


def init_schema(conn: sqlite3.Connection) -> None:
    """Create ``backtest_jobs`` and its index. Idempotent."""
    with conn:
        conn.execute(_DDL_BACKTEST_JOBS)
        conn.execute(_DDL_INDEX)


def insert_job(conn: sqlite3.Connection, row: BacktestJobRow) -> None:
    """Insert one job row. Caller owns the id and timestamps."""
    with conn:
        conn.execute(
            "INSERT INTO backtest_jobs "
            "(id, strategy, period_from, period_to, custom_symbols_json, "
            "initial_capital, status, elapsed_ms, result_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["id"],
                row["strategy"],
                row["period_from"],
                row["period_to"],
                row["custom_symbols_json"],
                float(row["initial_capital"]),
                row["status"],
                int(row["elapsed_ms"]),
                row["result_json"],
                row["created_at"],
            ),
        )


def _row_to_dict(r: tuple[Any, ...]) -> BacktestJobRow:
    return BacktestJobRow(
        id=str(r[0]),
        strategy=str(r[1]),
        period_from=str(r[2]),
        period_to=str(r[3]),
        custom_symbols_json=str(r[4]),
        initial_capital=float(r[5]),
        status=str(r[6]),
        elapsed_ms=int(r[7]),
        result_json=str(r[8]),
        created_at=str(r[9]),
    )


def select_recent(
    conn: sqlite3.Connection, limit: int
) -> list[BacktestJobRow]:
    """Return up to ``limit`` rows ordered by ``created_at DESC``."""
    cursor = conn.execute(
        "SELECT id, strategy, period_from, period_to, custom_symbols_json, "
        "initial_capital, status, elapsed_ms, result_json, created_at "
        "FROM backtest_jobs ORDER BY created_at DESC LIMIT ?",
        (int(limit),),
    )
    return [_row_to_dict(r) for r in cursor.fetchall()]


def select_by_id(
    conn: sqlite3.Connection, job_id: str
) -> BacktestJobRow | None:
    """Return a single row by primary key, or ``None`` if absent."""
    row = conn.execute(
        "SELECT id, strategy, period_from, period_to, custom_symbols_json, "
        "initial_capital, status, elapsed_ms, result_json, created_at "
        "FROM backtest_jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)
