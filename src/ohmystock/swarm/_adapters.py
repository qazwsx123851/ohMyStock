"""Adapter Protocols + dataclasses for the swarm input assembler.

The pure assembler does NOT perform I/O. Callers (the runner, the CLI)
build snapshots via these adapters and pass the resulting data objects in.
This file defines:

- The ``MarketSnapshot`` / ``PortfolioSnapshot`` data classes the assembler
  consumes.
- ``MarketSnapshotProvider`` / ``PortfolioSnapshotProvider`` /
  ``JournalStatsProvider`` Protocols so tests can swap fakes.
- ``Live*`` runtime implementations that read from cached daily bars,
  the trade journal, and the screener universe. Each takes an ``asof``
  string in its constructor and raises ``LiveProviderError`` (typed
  code) on data-source failure.

Specs:
- openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
- openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from ohmystock.config import Settings
from ohmystock.swarm._errors import LiveProviderError


@dataclass(frozen=True)
class PortfolioPosition:
    symbol: str
    sector: str
    exposure_pct: float


@dataclass(frozen=True)
class MarketSnapshot:
    taiex_close: float
    taiex_change_pct: float
    risk_off: bool
    monthly_pnl_pct: float


@dataclass(frozen=True)
class PortfolioSnapshot:
    positions: list[PortfolioPosition] = field(default_factory=list)
    total_exposure_pct: float = 0.0


@runtime_checkable
class MarketSnapshotProvider(Protocol):
    def get(self) -> MarketSnapshot:
        ...


@runtime_checkable
class PortfolioSnapshotProvider(Protocol):
    def get(self) -> PortfolioSnapshot:
        ...


@runtime_checkable
class JournalStatsProvider(Protocol):
    def recent_winrate(self, n: int = 20) -> float:
        ...

    def consecutive_loss(self) -> int:
        ...


def _open_journal_conn() -> sqlite3.Connection:
    """Open the shared SQLite DB (bars_daily + journal_entries + universe_daily).

    Raises ``LiveProviderError(DATA_UNAVAILABLE)`` when the path cannot be
    opened — this is the failure surface the live providers expose to the
    CLI per ``openspec/specs/live-providers/spec.md``.
    """
    path = Path(Settings().ohmystock_db_path).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(str(path))
    except (sqlite3.Error, OSError) as exc:
        raise LiveProviderError(
            code="DATA_UNAVAILABLE",
            message=f"cannot open journal db at {path}: {exc}",
        ) from exc


class LiveMarketSnapshotProvider:
    """TAIEX-derived ``MarketSnapshot`` provider (v1: TAIEX-only Risk-Off).

    ``get()`` delegates to ``compute_taiex_snapshot`` which reads cached
    daily bars and the trade-journal SQLite. Unwired Risk-Off signals
    (SPY / VIX / FX / TAIFEX) are recorded on ``last_diagnostics`` after
    each call so the CLI can emit a `warning:` line.
    """

    def __init__(self, asof: str) -> None:
        self._asof = asof
        self.last_diagnostics: dict[str, str] = {}

    def get(self) -> MarketSnapshot:
        from ohmystock.swarm._live_market import compute_taiex_snapshot

        try:
            conn: sqlite3.Connection | None = _open_journal_conn()
        except LiveProviderError:
            conn = None
        try:
            snap, diagnostics = compute_taiex_snapshot(self._asof, conn=conn)
        finally:
            if conn is not None:
                conn.close()
        self.last_diagnostics = diagnostics
        return snap


class LivePortfolioSnapshotProvider:
    """Portfolio reconstruction from the trade journal as of ``asof``.

    Open positions are entries (with ``actual_entry_price`` / ``actual_qty``)
    that have no matching exit on the same ``decision_id`` by ``asof``.
    Sector is resolved against the screener universe; missing symbols
    default to ``"未分類"`` (no raise).
    """

    def __init__(self, asof: str) -> None:
        self._asof = asof

    def get(self) -> PortfolioSnapshot:
        from ohmystock.swarm._live_portfolio import reconstruct_portfolio

        return reconstruct_portfolio(self._asof)


class LiveJournalStatsProvider:
    """Recent winrate + consecutive-loss streak from the trade journal."""

    def __init__(self, asof: str) -> None:
        self._asof = asof

    def recent_winrate(self, n: int = 20) -> float:
        from ohmystock.swarm._live_journal import compute_recent_winrate

        conn = _open_journal_conn()
        try:
            return compute_recent_winrate(conn, self._asof, n)
        finally:
            conn.close()

    def consecutive_loss(self) -> int:
        from ohmystock.swarm._live_journal import compute_consecutive_loss

        conn = _open_journal_conn()
        try:
            return compute_consecutive_loss(conn, self._asof)
        finally:
            conn.close()
