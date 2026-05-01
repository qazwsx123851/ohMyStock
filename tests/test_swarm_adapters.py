"""Tests for swarm adapter Protocols + live-stub providers.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

import pytest

from ohmystock.swarm import (
    JournalStatsProvider,
    LiveJournalStatsProvider,
    LiveMarketSnapshotProvider,
    LivePortfolioSnapshotProvider,
    MarketSnapshot,
    MarketSnapshotProvider,
    PortfolioPosition,
    PortfolioSnapshot,
    PortfolioSnapshotProvider,
)


def test_market_snapshot_is_frozen() -> None:
    snap = MarketSnapshot(
        taiex_close=20000.0,
        taiex_change_pct=0.5,
        risk_off=False,
        monthly_pnl_pct=-1.8,
    )
    with pytest.raises(Exception):
        snap.taiex_close = 1.0  # type: ignore[misc]


def test_portfolio_snapshot_default_empty() -> None:
    snap = PortfolioSnapshot()
    assert snap.positions == []
    assert snap.total_exposure_pct == 0.0


def test_portfolio_position_round_trip() -> None:
    pos = PortfolioPosition(symbol="2454", sector="半導體", exposure_pct=18.0)
    assert pos.symbol == "2454"
    assert pos.sector == "半導體"
    assert pos.exposure_pct == 18.0


def test_live_market_provider_requires_asof() -> None:
    # Constructor now mandates asof — passing none should TypeError.
    with pytest.raises(TypeError):
        LiveMarketSnapshotProvider()  # type: ignore[call-arg]


def test_live_portfolio_provider_requires_asof() -> None:
    with pytest.raises(TypeError):
        LivePortfolioSnapshotProvider()  # type: ignore[call-arg]


def test_live_journal_provider_requires_asof() -> None:
    with pytest.raises(TypeError):
        LiveJournalStatsProvider()  # type: ignore[call-arg]


def test_market_provider_protocol_accepts_fakes() -> None:
    class FakeMarket:
        def get(self) -> MarketSnapshot:
            return MarketSnapshot(
                taiex_close=20000.0,
                taiex_change_pct=0.5,
                risk_off=False,
                monthly_pnl_pct=-1.8,
            )

    fake: MarketSnapshotProvider = FakeMarket()
    assert isinstance(fake, MarketSnapshotProvider)
    snap = fake.get()
    assert snap.taiex_close == 20000.0


def test_portfolio_provider_protocol_accepts_fakes() -> None:
    class FakePortfolio:
        def get(self) -> PortfolioSnapshot:
            return PortfolioSnapshot(
                positions=[PortfolioPosition("2454", "半導體", 18.0)],
                total_exposure_pct=18.0,
            )

    fake: PortfolioSnapshotProvider = FakePortfolio()
    assert isinstance(fake, PortfolioSnapshotProvider)
    snap = fake.get()
    assert snap.positions[0].symbol == "2454"


def test_journal_provider_protocol_accepts_fakes() -> None:
    class FakeJournal:
        def recent_winrate(self, n: int = 20) -> float:
            return 0.55

        def consecutive_loss(self) -> int:
            return 1

    fake: JournalStatsProvider = FakeJournal()
    assert isinstance(fake, JournalStatsProvider)
    assert fake.recent_winrate() == 0.55
    assert fake.consecutive_loss() == 1
