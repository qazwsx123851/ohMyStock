"""``memory_rows`` schema migration (SQLite + FTS5 + 3 triggers).

Spec: openspec/changes/web-admin-memory-page-and-store/specs/memory-store/spec.md

Provides idempotent ``init_schema(conn)`` that creates:

* ``memory_rows`` main table — 6 columns + ``kind`` CHECK + ``tags`` JSON default.
* Two indexes: ``idx_memory_rows_kind_created_at`` and ``idx_memory_rows_created_at``.
* ``memory_rows_fts`` FTS5 external-content virtual table over ``content``.
* ``memory_rows_ai / _au / _ad`` triggers that keep the FTS5 index in sync
  with INSERT / UPDATE / DELETE on ``memory_rows`` (mirrors
  ``journal_entries_fts``).

All DDL uses ``IF NOT EXISTS``; the function commits in a single
transaction. ``_probe_fts5`` raises ``RuntimeError`` if the SQLite build
lacks FTS5, mirroring ``journal/schema.py``.
"""

from __future__ import annotations

import sqlite3


_KIND_CHECK = "kind IN ('note','lesson','proposal','review_summary')"

_DDL_MEMORY_ROWS = f"""
CREATE TABLE IF NOT EXISTS memory_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK({_KIND_CHECK}),
    content TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    source TEXT,
    created_at TEXT NOT NULL
)
"""

_DDL_INDEX_KIND_CREATED_AT = (
    "CREATE INDEX IF NOT EXISTS idx_memory_rows_kind_created_at "
    "ON memory_rows(kind, created_at)"
)

_DDL_INDEX_CREATED_AT = (
    "CREATE INDEX IF NOT EXISTS idx_memory_rows_created_at "
    "ON memory_rows(created_at)"
)

_DDL_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS memory_rows_fts USING fts5(
    content,
    content='memory_rows',
    content_rowid='id'
)
"""

_DDL_TRIGGER_AI = """
CREATE TRIGGER IF NOT EXISTS memory_rows_ai
AFTER INSERT ON memory_rows BEGIN
    INSERT INTO memory_rows_fts(rowid, content) VALUES (NEW.id, NEW.content);
END
"""

_DDL_TRIGGER_AD = """
CREATE TRIGGER IF NOT EXISTS memory_rows_ad
AFTER DELETE ON memory_rows BEGIN
    INSERT INTO memory_rows_fts(memory_rows_fts, rowid, content)
    VALUES ('delete', OLD.id, OLD.content);
END
"""

_DDL_TRIGGER_AU = """
CREATE TRIGGER IF NOT EXISTS memory_rows_au
AFTER UPDATE ON memory_rows BEGIN
    INSERT INTO memory_rows_fts(memory_rows_fts, rowid, content)
    VALUES ('delete', OLD.id, OLD.content);
    INSERT INTO memory_rows_fts(rowid, content) VALUES (NEW.id, NEW.content);
END
"""


def _probe_fts5(conn: sqlite3.Connection) -> None:
    """Raise ``RuntimeError`` mentioning ``"FTS5"`` if unavailable."""

    try:
        conn.execute("CREATE VIRTUAL TABLE _memory_fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE _memory_fts5_probe")
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            f"FTS5 unavailable on this SQLite build. Original error: {exc}"
        ) from exc


def init_schema(conn: sqlite3.Connection) -> None:
    """Create ``memory_rows`` table / indexes / FTS5 / triggers idempotently.

    Raises ``RuntimeError`` if the SQLite build lacks FTS5.
    """

    _probe_fts5(conn)
    with conn:
        conn.execute(_DDL_MEMORY_ROWS)
        conn.execute(_DDL_INDEX_KIND_CREATED_AT)
        conn.execute(_DDL_INDEX_CREATED_AT)
        conn.execute(_DDL_FTS)
        conn.execute(_DDL_TRIGGER_AI)
        conn.execute(_DDL_TRIGGER_AD)
        conn.execute(_DDL_TRIGGER_AU)
