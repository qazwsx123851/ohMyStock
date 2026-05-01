"""Adapter Protocols + dataclasses for the swarm input assembler.

The pure assembler does NOT perform I/O. Callers (the runner, the CLI)
build snapshots via these adapters and pass the resulting data objects in.
This file defines:

- The ``MarketSnapshot`` / ``PortfolioSnapshot`` data classes the assembler
  consumes.
- ``MarketSnapshotProvider`` / ``PortfolioSnapshotProvider`` /
  ``JournalStatsProvider`` Protocols so tests can swap fakes.
- ``Live*`` default implementations that raise ``NotImplementedError`` —
  they're stubs awaiting the upstream tool modules
  (``market_data_tool`` / ``portfolio_tool`` / ``chip_data_tool`` /
  ``trade_journal_tool``) which land in later phases. Once those tools
  exist, replace the bodies here.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


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


class LiveMarketSnapshotProvider:
    """Stub. Wraps ``market_data_tool.get_index('TAIEX')`` once that tool exists.

    Today this raises ``NotImplementedError`` — the upstream tool layer
    isn't yet built. Tests use fakes via the Protocol.
    """

    def get(self) -> MarketSnapshot:
        raise NotImplementedError(
            "LiveMarketSnapshotProvider requires market_data_tool.get_index('TAIEX') "
            "and strategies.risk_gate.evaluate_preview() — not yet wired."
        )


class LivePortfolioSnapshotProvider:
    """Stub. Wraps ``portfolio_tool.get_positions()`` + sector lookup."""

    def get(self) -> PortfolioSnapshot:
        raise NotImplementedError(
            "LivePortfolioSnapshotProvider requires portfolio_tool.get_positions() "
            "and chip_data_tool sector metadata — not yet wired."
        )


class LiveJournalStatsProvider:
    """Stub. Wraps ``trade_journal_tool.query`` for win-rate / streak helpers."""

    def recent_winrate(self, n: int = 20) -> float:
        raise NotImplementedError(
            "LiveJournalStatsProvider requires trade_journal_tool.query — not yet wired."
        )

    def consecutive_loss(self) -> int:
        raise NotImplementedError(
            "LiveJournalStatsProvider requires trade_journal_tool.query — not yet wired."
        )
