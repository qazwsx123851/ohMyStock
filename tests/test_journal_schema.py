"""Tests for ohmystock.journal.schema.init_schema.

Spec: openspec/changes/external-connectors-and-cost/specs/trade-journal-schema/spec.md
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from ohmystock.journal.schema import init_schema


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    try:
        yield c
    finally:
        c.close()


def test_init_schema_is_idempotent(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    init_schema(conn)

    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
        "('journal_entries', 'journal_entries_fts', 'llm_costs')"
    )
    names = {row[0] for row in cur.fetchall()}
    assert names == {"journal_entries", "journal_entries_fts", "llm_costs"}


def test_fts5_match_hits_entry_thesis(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "dec_001",
            "entry",
            "2330",
            "2026-04-29T11:00:00+08:00",
            '{"entry_thesis": "VCP breakout with strong volume"}',
        ),
    )
    conn.commit()

    cur = conn.execute(
        "SELECT rowid FROM journal_entries_fts WHERE journal_entries_fts MATCH ?",
        ("breakout",),
    )
    rows = cur.fetchall()
    assert len(rows) >= 1
    assert rows[0][0] == 1


def test_llm_costs_table_structure(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    cur = conn.execute("PRAGMA table_info(llm_costs)")
    columns = {row[1] for row in cur.fetchall()}
    assert columns == {
        "id",
        "decision_id",
        "model",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "created_at",
    }

    cur = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='index' AND tbl_name='llm_costs' AND sql LIKE '%created_at%'"
    )
    assert cur.fetchone() is not None


def test_kind_check_constraint_blocks_invalid(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "dec_x",
                "partial_fill",
                "2330",
                "2026-04-29T11:00:00+08:00",
                "{}",
            ),
        )


def test_expire_kind_is_allowed(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "dec_expired",
            "expire",
            "2330",
            "2026-04-29T11:00:00+08:00",
            '{"expire_reason": "confirm timeout"}',
        ),
    )
    row = conn.execute("SELECT kind FROM journal_entries WHERE decision_id = ?", ("dec_expired",)).fetchone()
    assert row == ("expire",)


def test_missing_fts5_raises_runtime_error() -> None:
    fake_conn = MagicMock(spec=sqlite3.Connection)
    fake_conn.execute.side_effect = sqlite3.OperationalError("no such module: fts5")

    with pytest.raises(RuntimeError, match="FTS5"):
        init_schema(fake_conn)
