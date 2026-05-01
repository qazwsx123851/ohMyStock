"""Read-only query helpers over ``journal_entries`` for live providers.

Pairing strategy: entries and exits join by ``decision_id`` per
``docs/llm-decision-schema.md`` §4.5.2. One entry has 0 or 1 matching exits.

All functions are pure: they take a passed-in ``sqlite3.Connection`` and
perform no I/O outside it. Callers own the connection lifecycle.

Spec: openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class OpenPosition:
    decision_id: str
    symbol: str
    sector: str
    entry_price: float
    qty_lots: int
    entry_ts: str


@dataclass(frozen=True)
class ClosedTrade:
    decision_id: str
    symbol: str
    pnl_pct: float
    qty_lots: int
    entry_price: float
    entry_ts: str
    exit_ts: str


_LOTS_TO_SHARES = 1000


def open_positions(
    conn: sqlite3.Connection, asof: str
) -> list[OpenPosition]:
    """Entries (with ``created_at <= asof``) lacking a matching exit.

    "Matching exit" means a row with ``kind='exit'``, the same
    ``decision_id``, and ``created_at <= asof``. Returns positions sorted
    by entry ``created_at`` ascending.
    """
    rows = conn.execute(
        """
        SELECT
            e.decision_id,
            e.symbol,
            e.created_at,
            COALESCE(json_extract(e.payload_json, '$.sector'), '未分類') AS sector,
            json_extract(e.payload_json, '$.actual_entry_price') AS entry_price,
            json_extract(e.payload_json, '$.actual_qty') AS qty_lots
        FROM journal_entries e
        WHERE e.kind = 'entry'
          AND e.created_at <= ?
          AND NOT EXISTS (
              SELECT 1 FROM journal_entries x
              WHERE x.kind = 'exit'
                AND x.decision_id = e.decision_id
                AND x.created_at <= ?
          )
        ORDER BY e.created_at ASC
        """,
        (asof, asof),
    ).fetchall()

    positions: list[OpenPosition] = []
    for row in rows:
        decision_id, symbol, entry_ts, sector, entry_price, qty_lots = row
        if entry_price is None or qty_lots is None:
            # Skip entries that haven't been filled yet (no actual_entry_price /
            # actual_qty). They're decisions awaiting confirmation, not positions.
            continue
        positions.append(
            OpenPosition(
                decision_id=str(decision_id),
                symbol=str(symbol),
                sector=str(sector or "未分類"),
                entry_price=float(entry_price),
                qty_lots=int(qty_lots),
                entry_ts=str(entry_ts),
            )
        )
    return positions


def closed_trades_desc(
    conn: sqlite3.Connection,
    asof: str,
    limit: int | None = None,
) -> list[ClosedTrade]:
    """Closed trades (entry+exit pairs) with ``exit.created_at <= asof``,
    sorted by exit ``created_at`` descending. Optional ``limit`` caps result count.
    """
    sql = """
        SELECT
            x.decision_id,
            x.symbol,
            json_extract(x.payload_json, '$.pnl_pct') AS pnl_pct,
            x.created_at AS exit_ts,
            e.created_at AS entry_ts,
            json_extract(e.payload_json, '$.actual_entry_price') AS entry_price,
            json_extract(e.payload_json, '$.actual_qty') AS qty_lots
        FROM journal_entries x
        JOIN journal_entries e
          ON e.decision_id = x.decision_id AND e.kind = 'entry'
        WHERE x.kind = 'exit'
          AND x.created_at <= ?
        ORDER BY x.created_at DESC
    """
    params: tuple = (asof,)
    if limit is not None:
        sql += " LIMIT ?"
        params = (asof, int(limit))

    rows = conn.execute(sql, params).fetchall()

    out: list[ClosedTrade] = []
    for row in rows:
        decision_id, symbol, pnl_pct, exit_ts, entry_ts, entry_price, qty_lots = row
        if pnl_pct is None:
            # Skip rows with no recorded pnl_pct — they cannot contribute to
            # winrate or monthly-pnl computations.
            continue
        out.append(
            ClosedTrade(
                decision_id=str(decision_id),
                symbol=str(symbol),
                pnl_pct=float(pnl_pct),
                qty_lots=int(qty_lots) if qty_lots is not None else 0,
                entry_price=float(entry_price) if entry_price is not None else 0.0,
                entry_ts=str(entry_ts),
                exit_ts=str(exit_ts),
            )
        )
    return out


def monthly_realized_pnl_pct(
    conn: sqlite3.Connection,
    asof: str,
    starting_equity: float,
) -> float:
    """Month-to-date realized P&L from closed trades as a percentage of
    ``starting_equity``.

    "Month" = the calendar month of ``asof`` (``YYYY-MM`` prefix of
    ``created_at``). For each closed trade in that month with
    ``exit.created_at <= asof``, realized P&L in TWD is
    ``(pnl_pct / 100) * entry_price * qty_lots * 1000``. The sum is
    divided by ``starting_equity`` and multiplied by 100. Returns ``0.0``
    if no qualifying trades exist or if ``starting_equity <= 0``.
    """
    if starting_equity <= 0:
        return 0.0

    # YYYY-MM prefix; ISO-8601 with +08:00 means substr is timezone-correct
    # because all journal entries share the same offset.
    year_month = asof[:7]

    rows = conn.execute(
        """
        SELECT
            json_extract(x.payload_json, '$.pnl_pct') AS pnl_pct,
            json_extract(e.payload_json, '$.actual_entry_price') AS entry_price,
            json_extract(e.payload_json, '$.actual_qty') AS qty_lots
        FROM journal_entries x
        JOIN journal_entries e
          ON e.decision_id = x.decision_id AND e.kind = 'entry'
        WHERE x.kind = 'exit'
          AND x.created_at <= ?
          AND substr(x.created_at, 1, 7) = ?
        """,
        (asof, year_month),
    ).fetchall()

    total_pnl_twd = 0.0
    for pnl_pct, entry_price, qty_lots in rows:
        if pnl_pct is None or entry_price is None or qty_lots is None:
            continue
        notional = float(entry_price) * int(qty_lots) * _LOTS_TO_SHARES
        total_pnl_twd += (float(pnl_pct) / 100.0) * notional

    return (total_pnl_twd / float(starting_equity)) * 100.0
