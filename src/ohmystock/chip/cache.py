"""SQLite cache + aggregation helpers for chip-side data.

Spec: openspec/changes/chip-data-skill/specs/chip-data-skill/spec.md
"""

from __future__ import annotations

import sqlite3
from typing import Any, Iterable

# `Foreign_` covers `Foreign_Investor` and `Foreign_Dealer_Self`.
# `Dealer_` covers `Dealer_self` and `Dealer_Hedging`.
_FOREIGN_PREFIX = "Foreign_"
_INVEST_TRUST_NAME = "Investment_Trust"
_DEALER_PREFIX = "Dealer_"


_DDL_THREE_MAJOR = """
CREATE TABLE IF NOT EXISTS chip_three_major_daily (
    symbol           TEXT    NOT NULL,
    date             TEXT    NOT NULL,
    foreign_net      INTEGER NOT NULL,
    invest_trust_net INTEGER NOT NULL,
    prop_dealer_net  INTEGER NOT NULL,
    source           TEXT    NOT NULL,
    fetched_at       TEXT    NOT NULL,
    PRIMARY KEY (symbol, date)
)
""".strip()


_DDL_MARGIN_SHORT = """
CREATE TABLE IF NOT EXISTS chip_margin_short_daily (
    symbol                TEXT    NOT NULL,
    date                  TEXT    NOT NULL,
    margin_balance        INTEGER NOT NULL,
    margin_change         INTEGER NOT NULL,
    short_balance         INTEGER NOT NULL,
    short_change          INTEGER NOT NULL,
    short_to_margin_ratio REAL    NOT NULL,
    source                TEXT    NOT NULL,
    fetched_at            TEXT    NOT NULL,
    PRIMARY KEY (symbol, date)
)
""".strip()


def init_chip_schema(conn: sqlite3.Connection) -> None:
    """Create both chip cache tables. Idempotent. Single transaction."""
    with conn:
        conn.execute(_DDL_THREE_MAJOR)
        conn.execute(_DDL_MARGIN_SHORT)


def aggregate_three_major(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse FinMind institutional rows into one row per (symbol, date).

    Input: dicts with at least ``date``, ``stock_id``, ``name``, ``buy``, ``sell``.
    Output: dicts ``{symbol, date, foreign_net, invest_trust_net, prop_dealer_net}``,
    sorted by (symbol, date) ascending. Net = buy - sell, in shares.
    """
    buckets: dict[tuple[str, str], dict[str, int]] = {}
    for row in raw_rows:
        symbol = str(row["stock_id"])
        date = str(row["date"])
        name = str(row.get("name", ""))
        net = int(row.get("buy", 0)) - int(row.get("sell", 0))
        slot = buckets.setdefault(
            (symbol, date),
            {"foreign_net": 0, "invest_trust_net": 0, "prop_dealer_net": 0},
        )
        if name.startswith(_FOREIGN_PREFIX):
            slot["foreign_net"] += net
        elif name == _INVEST_TRUST_NAME:
            slot["invest_trust_net"] += net
        elif name.startswith(_DEALER_PREFIX):
            slot["prop_dealer_net"] += net
        # Unknown ``name`` values are silently skipped — defensive against
        # FinMind adding new leg labels we don't yet recognise.

    out: list[dict[str, Any]] = []
    for (symbol, date) in sorted(buckets):
        out.append({"symbol": symbol, "date": date, **buckets[(symbol, date)]})
    return out


def insert_three_major_rows(
    conn: sqlite3.Connection,
    normalised_rows: Iterable[dict[str, Any]],
    source: str,
    fetched_at: str,
) -> int:
    payload = [
        (
            r["symbol"],
            r["date"],
            int(r["foreign_net"]),
            int(r["invest_trust_net"]),
            int(r["prop_dealer_net"]),
            source,
            fetched_at,
        )
        for r in normalised_rows
    ]
    if not payload:
        return 0
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO chip_three_major_daily "
            "(symbol, date, foreign_net, invest_trust_net, prop_dealer_net, "
            "source, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            payload,
        )
    return len(payload)


def select_three_major_rows(
    conn: sqlite3.Connection, symbol: str, start: str, end: str
) -> list[dict[str, Any]]:
    cursor = conn.execute(
        "SELECT date, foreign_net, invest_trust_net, prop_dealer_net "
        "FROM chip_three_major_daily "
        "WHERE symbol = ? AND date >= ? AND date <= ? "
        "ORDER BY date ASC",
        (symbol, start, end),
    )
    return [
        {
            "date": row[0],
            "foreign_net": row[1],
            "invest_trust_net": row[2],
            "prop_dealer_net": row[3],
        }
        for row in cursor.fetchall()
    ]


def insert_margin_short_rows(
    conn: sqlite3.Connection,
    raw_rows: Iterable[dict[str, Any]],
    source: str,
    fetched_at: str,
) -> int:
    """Insert FinMind margin-short rows. Computes short_to_margin_ratio at write."""
    payload = []
    for r in raw_rows:
        symbol = str(r["stock_id"])
        date = str(r["date"])
        margin_balance = int(r.get("MarginPurchaseTodayBalance", 0))
        margin_change = margin_balance - int(
            r.get("MarginPurchaseYesterdayBalance", margin_balance)
        )
        short_balance = int(r.get("ShortSaleTodayBalance", 0))
        short_change = short_balance - int(
            r.get("ShortSaleYesterdayBalance", short_balance)
        )
        ratio = (
            round(short_balance / margin_balance * 100.0, 4)
            if margin_balance > 0
            else 0.0
        )
        payload.append(
            (
                symbol,
                date,
                margin_balance,
                margin_change,
                short_balance,
                short_change,
                ratio,
                source,
                fetched_at,
            )
        )
    if not payload:
        return 0
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO chip_margin_short_daily "
            "(symbol, date, margin_balance, margin_change, short_balance, "
            "short_change, short_to_margin_ratio, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )
    return len(payload)


def select_margin_short_rows(
    conn: sqlite3.Connection, symbol: str, start: str, end: str
) -> list[dict[str, Any]]:
    cursor = conn.execute(
        "SELECT date, margin_balance, margin_change, short_balance, short_change, "
        "short_to_margin_ratio FROM chip_margin_short_daily "
        "WHERE symbol = ? AND date >= ? AND date <= ? "
        "ORDER BY date ASC",
        (symbol, start, end),
    )
    return [
        {
            "date": row[0],
            "margin_balance": row[1],
            "margin_change": row[2],
            "short_balance": row[3],
            "short_change": row[4],
            "short_to_margin_ratio": row[5],
        }
        for row in cursor.fetchall()
    ]
