"""E2E-only SQLite schema seeder.

Playwright's globalSetup runs this against a throwaway DB pointed to by
``OHMYSTOCK_DB_PATH`` (a temp file), so smoke pages query real tables instead
of hitting "no such table" 500s. Schema-only — inserts no rows; pages render
their empty states.

NEVER point OHMYSTOCK_DB_PATH at the real journal.db: this only creates tables
(all DDL is IF NOT EXISTS / idempotent), but the contract is temp-DB only.

Run: ``uv run python web-admin/e2e/seed_db.py``
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from ohmystock.backtest.storage import init_schema as init_backtest
from ohmystock.chat.storage import init_schema as init_chat
from ohmystock.data.disposition import init_schema as init_disposition
from ohmystock.journal.schema import init_schema as init_journal
from ohmystock.memory.schema import init_schema as init_memory
from ohmystock.sepa.rs import init_schema as init_rs
from ohmystock.swarm_runs.storage import init_schema as init_swarm_runs

_INITS = (
    init_journal,
    init_swarm_runs,
    init_memory,
    init_chat,
    init_backtest,
    init_disposition,
    init_rs,
)


def main() -> int:
    db_path = os.environ.get("OHMYSTOCK_DB_PATH")
    if not db_path:
        print("OHMYSTOCK_DB_PATH not set; refusing to seed", file=sys.stderr)
        return 1

    resolved = Path(db_path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(resolved))
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        for init in _INITS:
            init(conn)
        conn.commit()
    finally:
        conn.close()

    print(f"seeded schema into {resolved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
