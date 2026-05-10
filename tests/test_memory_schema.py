"""Tests for ``ohmystock.memory.schema.init_schema``.

Spec: openspec/changes/web-admin-memory-page-and-store/specs/memory-store/spec.md
"""

from __future__ import annotations

import sqlite3

import pytest

from ohmystock.memory import init_schema
from ohmystock.memory import schema as memory_schema


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    try:
        yield c
    finally:
        c.close()


def test_init_schema_creates_tables_indexes_triggers(conn: sqlite3.Connection) -> None:
    init_schema(conn)

    table_names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('memory_rows', 'memory_rows_fts')"
        ).fetchall()
    }
    assert table_names == {"memory_rows", "memory_rows_fts"}

    trigger_names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    }
    assert {"memory_rows_ai", "memory_rows_au", "memory_rows_ad"} <= trigger_names

    index_names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='memory_rows'"
        ).fetchall()
    }
    assert "idx_memory_rows_kind_created_at" in index_names
    assert "idx_memory_rows_created_at" in index_names


def test_init_schema_is_idempotent(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    conn.execute(
        "INSERT INTO memory_rows(kind, content, created_at) VALUES (?, ?, ?)",
        ("note", "hello", "2026-05-09T10:00:00+08:00"),
    )
    conn.commit()

    init_schema(conn)

    count = conn.execute("SELECT COUNT(*) FROM memory_rows").fetchone()[0]
    assert count == 1


def test_kind_check_rejects_unknown(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO memory_rows(kind, content, tags, source, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("random", "x", "[]", None, "2026-05-09T10:00:00+08:00"),
        )


def test_tags_default_is_empty_json_array(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    conn.execute(
        "INSERT INTO memory_rows(kind, content, created_at) VALUES (?, ?, ?)",
        ("note", "hello", "2026-05-09T10:00:00+08:00"),
    )
    conn.commit()
    tags = conn.execute(
        "SELECT tags FROM memory_rows WHERE id = last_insert_rowid()"
    ).fetchone()[0]
    assert tags == "[]"


def test_fts_trigger_syncs_insert(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    conn.execute(
        "INSERT INTO memory_rows(kind, content, created_at) VALUES (?, ?, ?)",
        ("note", "VCP breakout 杯柄突破", "2026-05-09T10:00:00+08:00"),
    )
    conn.commit()
    rows = conn.execute(
        "SELECT rowid FROM memory_rows_fts WHERE memory_rows_fts MATCH ?",
        ("breakout",),
    ).fetchall()
    assert len(rows) == 1


def test_fts_trigger_syncs_update(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    conn.execute(
        "INSERT INTO memory_rows(kind, content, created_at) VALUES (?, ?, ?)",
        ("note", "foo", "2026-05-09T10:00:00+08:00"),
    )
    conn.commit()
    rowid = conn.execute("SELECT id FROM memory_rows").fetchone()[0]

    conn.execute("UPDATE memory_rows SET content = ? WHERE id = ?", ("bar", rowid))
    conn.commit()

    bar_hits = conn.execute(
        "SELECT rowid FROM memory_rows_fts WHERE memory_rows_fts MATCH ?", ("bar",)
    ).fetchall()
    foo_hits = conn.execute(
        "SELECT rowid FROM memory_rows_fts WHERE memory_rows_fts MATCH ?", ("foo",)
    ).fetchall()
    assert [r[0] for r in bar_hits] == [rowid]
    assert foo_hits == []


def test_fts_trigger_syncs_delete(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    conn.execute(
        "INSERT INTO memory_rows(kind, content, created_at) VALUES (?, ?, ?)",
        ("note", "zzz unique token", "2026-05-09T10:00:00+08:00"),
    )
    conn.commit()
    rowid = conn.execute("SELECT id FROM memory_rows").fetchone()[0]

    conn.execute("DELETE FROM memory_rows WHERE id = ?", (rowid,))
    conn.commit()

    hits = conn.execute(
        "SELECT rowid FROM memory_rows_fts WHERE memory_rows_fts MATCH ?", ("zzz",)
    ).fetchall()
    assert hits == []


def test_init_schema_raises_when_fts5_unavailable(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_probe(_: sqlite3.Connection) -> None:
        raise RuntimeError("FTS5 unavailable on this SQLite build. Original error: x")

    monkeypatch.setattr(memory_schema, "_probe_fts5", _fail_probe)
    with pytest.raises(RuntimeError, match="FTS5"):
        init_schema(conn)
