"""SQLite cache + aggregation helpers for TW universe snapshots.

Spec: openspec/changes/screener-tw-universe/specs/screener-tw-universe/spec.md
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any, Iterable


_TYPE_TO_MARKET = {"twse": "TWSE", "tpex": "OTC"}


_DDL_UNIVERSE_DAILY = """
CREATE TABLE IF NOT EXISTS universe_daily (
    asof_date     TEXT    NOT NULL,
    symbol        TEXT    NOT NULL,
    market        TEXT    NOT NULL,
    name          TEXT    NOT NULL,
    industry      TEXT    NOT NULL DEFAULT '',
    is_warning    INTEGER NOT NULL DEFAULT 0,
    is_disposal   INTEGER NOT NULL DEFAULT 0,
    is_fully_paid INTEGER NOT NULL DEFAULT 0,
    is_ky         INTEGER NOT NULL DEFAULT 0,
    source        TEXT    NOT NULL,
    fetched_at    TEXT    NOT NULL,
    PRIMARY KEY (asof_date, symbol)
)
""".strip()


def init_universe_schema(conn: sqlite3.Connection) -> None:
    """Create `universe_daily` if absent. Idempotent."""
    with conn:
        conn.execute(_DDL_UNIVERSE_DAILY)


def aggregate_universe_rows(
    raw_rows: list[dict[str, Any]], asof_date: str
) -> list[dict[str, Any]]:
    """Normalise FinMind TaiwanStockInfo rows into cache-shaped dicts.

    - Maps `type` `twse`/`tpex` -> `market` `'TWSE'`/`'OTC'`.
    - Derives `is_ky` from `stock_id` ending in `"KY"` (case-sensitive).
    - `is_warning` / `is_disposal` / `is_fully_paid` always `0` (no source yet).
    - Skips rows whose `type` isn't recognised.
    - Sorts output by symbol ascending.
    """
    out: list[dict[str, Any]] = []
    for row in raw_rows:
        raw_type = str(row.get("type", "")).lower()
        market = _TYPE_TO_MARKET.get(raw_type)
        if market is None:
            continue
        symbol = str(row["stock_id"])
        out.append(
            {
                "asof_date": asof_date,
                "symbol": symbol,
                "market": market,
                "name": str(row.get("stock_name", "")),
                "industry": str(row.get("industry_category", "")),
                "is_warning": 0,
                "is_disposal": 0,
                "is_fully_paid": 0,
                "is_ky": 1 if symbol.endswith("KY") else 0,
            }
        )
    out.sort(key=lambda r: r["symbol"])
    return out


def insert_universe_rows(
    conn: sqlite3.Connection,
    normalised_rows: Iterable[dict[str, Any]],
    source: str,
    fetched_at: str,
) -> int:
    payload = [
        (
            r["asof_date"],
            r["symbol"],
            r["market"],
            r["name"],
            r.get("industry", ""),
            int(r.get("is_warning", 0)),
            int(r.get("is_disposal", 0)),
            int(r.get("is_fully_paid", 0)),
            int(r.get("is_ky", 0)),
            source,
            fetched_at,
        )
        for r in normalised_rows
    ]
    if not payload:
        return 0
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO universe_daily "
            "(asof_date, symbol, market, name, industry, is_warning, is_disposal, "
            "is_fully_paid, is_ky, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )
    return len(payload)


def select_universe_rows(
    conn: sqlite3.Connection,
    asof_date: str,
    market_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Return rows for `asof_date`, optionally filtered to one `market`.

    `market_filter` accepted values: `'TWSE'`, `'OTC'`, or `None` for both.
    Rows are ordered by symbol ascending.
    """
    sql = (
        "SELECT asof_date, symbol, market, name, industry, "
        "is_warning, is_disposal, is_fully_paid, is_ky "
        "FROM universe_daily WHERE asof_date = ?"
    )
    params: list[Any] = [asof_date]
    if market_filter is not None:
        sql += " AND market = ?"
        params.append(market_filter)
    sql += " ORDER BY symbol ASC"
    cursor = conn.execute(sql, params)
    return [
        {
            "asof_date": r[0],
            "symbol": r[1],
            "market": r[2],
            "name": r[3],
            "industry": r[4],
            "is_warning": r[5],
            "is_disposal": r[6],
            "is_fully_paid": r[7],
            "is_ky": r[8],
        }
        for r in cursor.fetchall()
    ]


def latest_asof_within(
    conn: sqlite3.Connection, target_date: str, lookback_days: int = 30
) -> str | None:
    """Most recent `asof_date` <= `target_date` within `lookback_days`, else None."""
    upper = datetime.strptime(target_date, "%Y-%m-%d").date()
    lower = upper - timedelta(days=lookback_days)
    row = conn.execute(
        "SELECT MAX(asof_date) FROM universe_daily "
        "WHERE asof_date <= ? AND asof_date >= ?",
        (upper.isoformat(), lower.isoformat()),
    ).fetchone()
    return row[0] if row and row[0] is not None else None
