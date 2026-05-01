"""Portfolio reconstruction from the trade journal as of ``asof``.

For each open position (entry without a matching exit on the same
``decision_id``) we look up the most recent cached daily close ≤
``asof`` and compute ``exposure_pct = qty * close / equity * 100``.
Sector is resolved from the screener universe; missing symbols default
to ``"未分類"`` (no raise).

Spec: openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ohmystock.config import Settings
from ohmystock.journal.repository import open_positions
from ohmystock.swarm._adapters import (
    PortfolioPosition,
    PortfolioSnapshot,
)
from ohmystock.swarm._errors import LiveProviderError


_LOTS_TO_SHARES = 1000


def reconstruct_portfolio(
    asof: str,
    *,
    conn: sqlite3.Connection | None = None,
    sector_lookup: dict[str, str] | None = None,
    starting_equity: float | None = None,
) -> PortfolioSnapshot:
    """Build a ``PortfolioSnapshot`` from the journal as of ``asof``.

    Raises ``LiveProviderError(DATA_UNAVAILABLE)`` if the journal SQLite
    cannot be opened. When ``conn`` is provided, the caller owns its
    lifecycle (we do not close it).
    """
    owns_conn = False
    if conn is None:
        conn = _open_journal_conn()
        owns_conn = True

    try:
        positions = open_positions(conn, asof)
        if not positions:
            return PortfolioSnapshot()

        if starting_equity is None:
            starting_equity = float(Settings().starting_equity_twd)
        if starting_equity <= 0:
            return PortfolioSnapshot()

        if sector_lookup is None:
            sector_lookup = _load_sector_lookup(conn, asof)

        result: list[PortfolioPosition] = []
        total_exposure = 0.0
        for pos in positions:
            close = _latest_close_on_or_before(conn, pos.symbol, asof)
            if close is None:
                close = pos.entry_price
            shares = pos.qty_lots * _LOTS_TO_SHARES
            exposure = (shares * close / starting_equity) * 100.0
            sector = sector_lookup.get(pos.symbol) or pos.sector or "未分類"
            if not sector:
                sector = "未分類"
            result.append(
                PortfolioPosition(
                    symbol=pos.symbol,
                    sector=sector,
                    exposure_pct=exposure,
                )
            )
            total_exposure += exposure

        return PortfolioSnapshot(
            positions=result,
            total_exposure_pct=total_exposure,
        )
    finally:
        if owns_conn:
            conn.close()


def _open_journal_conn() -> sqlite3.Connection:
    path = Path(Settings().ohmystock_db_path).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(str(path))
    except (sqlite3.Error, OSError) as exc:
        raise LiveProviderError(
            code="DATA_UNAVAILABLE",
            message=f"cannot open journal db at {path}: {exc}",
        ) from exc


def _latest_close_on_or_before(
    conn: sqlite3.Connection, symbol: str, asof: str
) -> float | None:
    try:
        row = conn.execute(
            "SELECT c FROM bars_daily WHERE symbol = ? AND date <= ? "
            "ORDER BY date DESC LIMIT 1",
            (symbol, asof),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return float(row[0]) if row else None


def _load_sector_lookup(
    conn: sqlite3.Connection, asof: str
) -> dict[str, str]:
    try:
        anchor_row = conn.execute(
            "SELECT MAX(asof_date) FROM universe_daily WHERE asof_date <= ?",
            (asof,),
        ).fetchone()
    except sqlite3.OperationalError:
        return {}
    if not anchor_row or not anchor_row[0]:
        return {}
    asof_used = anchor_row[0]
    rows = conn.execute(
        "SELECT symbol, industry FROM universe_daily WHERE asof_date = ?",
        (asof_used,),
    ).fetchall()
    return {sym: ind or "未分類" for sym, ind in rows}
