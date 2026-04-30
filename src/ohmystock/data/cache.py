"""SQLite cache for daily OHLCV bars.

Spec: openspec/changes/market-data-fetch-cache/specs/market-data-cache/spec.md
"""

from __future__ import annotations

import sqlite3
from typing import Iterable

from ohmystock.data.sources.base import BarRow


_DDL_BARS_DAILY = """
CREATE TABLE IF NOT EXISTS bars_daily (
    symbol     TEXT    NOT NULL,
    date       TEXT    NOT NULL,
    o          REAL    NOT NULL,
    h          REAL    NOT NULL,
    l          REAL    NOT NULL,
    c          REAL    NOT NULL,
    v          INTEGER NOT NULL,
    amount     INTEGER NOT NULL,
    source     TEXT    NOT NULL,
    fetched_at TEXT    NOT NULL,
    PRIMARY KEY (symbol, date)
)
""".strip()


def init_market_data_schema(conn: sqlite3.Connection) -> None:
    """Create `bars_daily` if absent. Idempotent."""
    with conn:
        conn.execute(_DDL_BARS_DAILY)


def insert_bars(
    conn: sqlite3.Connection,
    symbol: str,
    rows: Iterable[BarRow],
    source: str,
    fetched_at: str,
) -> int:
    """Batch-insert rows for one symbol. Caller supplies source + fetched_at.

    Returns the count of rows attempted (some may be ignored by PK conflict).
    """
    payload = [
        (
            symbol,
            r["ts"],
            float(r["o"]),
            float(r["h"]),
            float(r["l"]),
            float(r["c"]),
            int(r["v"]),
            int(r["amount"]),
            source,
            fetched_at,
        )
        for r in rows
    ]
    if not payload:
        return 0
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO bars_daily "
            "(symbol, date, o, h, l, c, v, amount, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )
    return len(payload)


def select_bars(
    conn: sqlite3.Connection, symbol: str, start: str, end: str
) -> list[BarRow]:
    """Return cached bars for symbol within [start, end] inclusive, sorted ascending."""
    cursor = conn.execute(
        "SELECT date, o, h, l, c, v, amount FROM bars_daily "
        "WHERE symbol = ? AND date >= ? AND date <= ? "
        "ORDER BY date ASC",
        (symbol, start, end),
    )
    return [
        BarRow(ts=row[0], o=row[1], h=row[2], l=row[3], c=row[4], v=row[5], amount=row[6])
        for row in cursor.fetchall()
    ]
