"""SQLite persistence for swarm runs.

One row per ``run_swarm`` invocation: ``params`` echoed verbatim plus the
runner's serialised ``result`` (node_outputs / failed_node / error / etc.).
``status`` is ``completed`` when the runner returned with all nodes done,
``failed`` when any node raised — the row exists either way.

Mirrors the success pattern of ``ohmystock.backtest.storage`` (per design.md
Decision D2 & D4).

Spec: openspec/changes/admin-swarm-endpoints-and-pages/specs/swarm-runs/spec.md
"""

from __future__ import annotations

import sqlite3
from typing import Any, TypedDict


_DDL_SWARM_RUNS = """
CREATE TABLE IF NOT EXISTS swarm_runs (
    id            TEXT    PRIMARY KEY,
    preset        TEXT    NOT NULL,
    status        TEXT    NOT NULL CHECK(status IN ('completed','failed')),
    params_json   TEXT    NOT NULL,
    result_json   TEXT    NOT NULL,
    elapsed_ms    INTEGER NOT NULL,
    created_at    TEXT    NOT NULL
)
""".strip()

_DDL_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_swarm_runs_created_at "
    "ON swarm_runs(created_at)"
)


class SwarmRunRowDict(TypedDict):
    id: str
    preset: str
    status: str
    params_json: str
    result_json: str
    elapsed_ms: int
    created_at: str


def init_schema(conn: sqlite3.Connection) -> None:
    """Create ``swarm_runs`` and its index. Idempotent."""
    with conn:
        conn.execute(_DDL_SWARM_RUNS)
        conn.execute(_DDL_INDEX)


def insert_run(conn: sqlite3.Connection, row: SwarmRunRowDict) -> None:
    """Insert one swarm run row. Caller owns the id and timestamps."""
    with conn:
        conn.execute(
            "INSERT INTO swarm_runs "
            "(id, preset, status, params_json, result_json, elapsed_ms, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                row["id"],
                row["preset"],
                row["status"],
                row["params_json"],
                row["result_json"],
                int(row["elapsed_ms"]),
                row["created_at"],
            ),
        )


def _row_to_dict(r: tuple[Any, ...]) -> SwarmRunRowDict:
    return SwarmRunRowDict(
        id=str(r[0]),
        preset=str(r[1]),
        status=str(r[2]),
        params_json=str(r[3]),
        result_json=str(r[4]),
        elapsed_ms=int(r[5]),
        created_at=str(r[6]),
    )


def select_recent(
    conn: sqlite3.Connection, limit: int
) -> list[SwarmRunRowDict]:
    """Return up to ``limit`` rows ordered by ``created_at DESC, id DESC``."""
    cursor = conn.execute(
        "SELECT id, preset, status, params_json, result_json, elapsed_ms, "
        "created_at FROM swarm_runs "
        "ORDER BY created_at DESC, id DESC LIMIT ?",
        (int(limit),),
    )
    return [_row_to_dict(r) for r in cursor.fetchall()]


def select_by_id(
    conn: sqlite3.Connection, run_id: str
) -> SwarmRunRowDict | None:
    """Return a single row by primary key, or ``None`` if absent."""
    row = conn.execute(
        "SELECT id, preset, status, params_json, result_json, elapsed_ms, "
        "created_at FROM swarm_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)
