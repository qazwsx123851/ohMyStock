"""Trade Journal schema migration.

Spec: openspec/changes/external-connectors-and-cost/specs/trade-journal-schema/spec.md

Provides idempotent ``init_schema(conn)`` that creates:

- ``journal_entries`` main table (6 columns + indexes + ``kind`` CHECK)
- ``journal_entries_fts`` FTS5 external-content virtual table over
  ``entry_thesis / llm_reasoning / exit_reason`` extracted from ``payload_json``
- ``journal_entries_ai / _au / _ad`` triggers to keep FTS5 in sync
- ``llm_costs`` table (7 columns + ``created_at`` index)

All DDL uses ``IF NOT EXISTS``; the function commits in a single transaction.
"""

from __future__ import annotations

import sqlite3

_DDL_JOURNAL_ENTRIES = """
CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('entry','exit','reject','expire')),
    symbol TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
)
"""

_DDL_INDEX_DECISION_ID = (
    "CREATE INDEX IF NOT EXISTS idx_journal_entries_decision_id "
    "ON journal_entries(decision_id)"
)

_DDL_INDEX_KIND_CREATED_AT = (
    "CREATE INDEX IF NOT EXISTS idx_journal_entries_kind_created_at "
    "ON journal_entries(kind, created_at)"
)

_DDL_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS journal_entries_fts USING fts5(
    entry_thesis,
    llm_reasoning,
    exit_reason,
    content='journal_entries',
    content_rowid='id'
)
"""

_DDL_TRIGGER_AI = """
CREATE TRIGGER IF NOT EXISTS journal_entries_ai
AFTER INSERT ON journal_entries BEGIN
    INSERT INTO journal_entries_fts(rowid, entry_thesis, llm_reasoning, exit_reason)
    VALUES (
        NEW.id,
        COALESCE(json_extract(NEW.payload_json, '$.entry_thesis'), ''),
        COALESCE(json_extract(NEW.payload_json, '$.llm_reasoning'), ''),
        COALESCE(json_extract(NEW.payload_json, '$.exit_reason'), '')
    );
END
"""

_DDL_TRIGGER_AD = """
CREATE TRIGGER IF NOT EXISTS journal_entries_ad
AFTER DELETE ON journal_entries BEGIN
    INSERT INTO journal_entries_fts(journal_entries_fts, rowid, entry_thesis, llm_reasoning, exit_reason)
    VALUES (
        'delete',
        OLD.id,
        COALESCE(json_extract(OLD.payload_json, '$.entry_thesis'), ''),
        COALESCE(json_extract(OLD.payload_json, '$.llm_reasoning'), ''),
        COALESCE(json_extract(OLD.payload_json, '$.exit_reason'), '')
    );
END
"""

_DDL_TRIGGER_AU = """
CREATE TRIGGER IF NOT EXISTS journal_entries_au
AFTER UPDATE ON journal_entries BEGIN
    INSERT INTO journal_entries_fts(journal_entries_fts, rowid, entry_thesis, llm_reasoning, exit_reason)
    VALUES (
        'delete',
        OLD.id,
        COALESCE(json_extract(OLD.payload_json, '$.entry_thesis'), ''),
        COALESCE(json_extract(OLD.payload_json, '$.llm_reasoning'), ''),
        COALESCE(json_extract(OLD.payload_json, '$.exit_reason'), '')
    );
    INSERT INTO journal_entries_fts(rowid, entry_thesis, llm_reasoning, exit_reason)
    VALUES (
        NEW.id,
        COALESCE(json_extract(NEW.payload_json, '$.entry_thesis'), ''),
        COALESCE(json_extract(NEW.payload_json, '$.llm_reasoning'), ''),
        COALESCE(json_extract(NEW.payload_json, '$.exit_reason'), '')
    );
END
"""

_DDL_LLM_COSTS = """
CREATE TABLE IF NOT EXISTS llm_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    created_at TEXT NOT NULL
)
"""

_DDL_INDEX_LLM_COSTS_CREATED_AT = (
    "CREATE INDEX IF NOT EXISTS idx_llm_costs_created_at "
    "ON llm_costs(created_at)"
)


def _probe_fts5(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("CREATE VIRTUAL TABLE _fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE _fts5_probe")
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            f"FTS5 unavailable on this SQLite build. Original error: {exc}"
        ) from exc


def init_schema(conn: sqlite3.Connection) -> None:
    """Create Trade Journal tables / indexes / triggers idempotently.

    Raises RuntimeError if the SQLite build lacks FTS5.
    """
    _probe_fts5(conn)
    with conn:
        conn.execute(_DDL_JOURNAL_ENTRIES)
        conn.execute(_DDL_INDEX_DECISION_ID)
        conn.execute(_DDL_INDEX_KIND_CREATED_AT)
        conn.execute(_DDL_FTS)
        conn.execute(_DDL_TRIGGER_AI)
        conn.execute(_DDL_TRIGGER_AD)
        conn.execute(_DDL_TRIGGER_AU)
        conn.execute(_DDL_LLM_COSTS)
        conn.execute(_DDL_INDEX_LLM_COSTS_CREATED_AT)
