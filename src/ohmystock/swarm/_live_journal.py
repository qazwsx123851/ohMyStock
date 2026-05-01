"""Recent winrate + consecutive-loss helpers from the trade journal.

Spec: openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations

import sqlite3

from ohmystock.journal.repository import closed_trades_desc


def compute_recent_winrate(
    conn: sqlite3.Connection, asof: str, n: int
) -> float:
    """Fraction (0.0–1.0) of profitable closed trades among the most
    recent ``n`` closed trades with ``exit.created_at <= asof``.

    Returns ``0.0`` when zero closed trades exist; otherwise the ratio
    is computed over what actually exists (≤ n).
    """
    if n <= 0:
        return 0.0
    trades = closed_trades_desc(conn, asof, limit=n)
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.pnl_pct > 0)
    return wins / len(trades)


def compute_consecutive_loss(conn: sqlite3.Connection, asof: str) -> int:
    """Count the most-recent consecutive losing closed trades.

    A trade is "losing" when ``pnl_pct <= 0``. The streak ends at the
    first profitable trade or when no more closed trades remain.
    Returns ``0`` when zero closed trades exist.
    """
    trades = closed_trades_desc(conn, asof)
    streak = 0
    for t in trades:
        if t.pnl_pct <= 0:
            streak += 1
        else:
            break
    return streak
