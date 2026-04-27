"""SQLite connection factory with FTS5 probe and WAL journal.

First call probes for FTS5 support (raises RuntimeError if the underlying
sqlite3 build lacks it) and caches the result. Each call returns a fresh
sqlite3.Connection bound to Settings().ohmystock_db_path with WAL +
foreign_keys enabled.

Spec: openspec/changes/fastapi-bootstrap/specs/backend-api-and-eventbus/spec.md
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from ohmystock.config import Settings

_FTS5_OK: bool = False


@lru_cache(maxsize=1)
def _get_settings() -> Settings:
    return Settings()


def _probe_fts5() -> None:
    global _FTS5_OK
    if _FTS5_OK:
        return
    probe = sqlite3.connect(":memory:")
    try:
        probe.execute("CREATE VIRTUAL TABLE _fts_probe USING fts5(x)")
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            "SQLite build lacks FTS5; install a Python build with FTS5 "
            f"enabled or use pysqlite3-binary. Original error: {exc}"
        ) from exc
    finally:
        probe.close()
    _FTS5_OK = True


def get_connection() -> sqlite3.Connection:
    _probe_fts5()
    path = Path(_get_settings().ohmystock_db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
