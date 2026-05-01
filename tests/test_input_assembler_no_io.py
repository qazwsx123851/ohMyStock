"""No-I/O test for the swarm input assembler.

Monkeypatches socket / httpx / sqlite3 to raise on use; the assembler must
still complete because it operates only on pre-built snapshots.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

import socket
import sqlite3

import httpx
import pytest

from ohmystock.scoring.models import Phase2BCandidate
from ohmystock.swarm import (
    MarketSnapshot,
    PortfolioPosition,
    PortfolioSnapshot,
    RulesDigest,
    build_entry_decision_input,
)


class _FakeJournal:
    def recent_winrate(self, n: int = 20) -> float:
        return 0.55

    def consecutive_loss(self) -> int:
        return 1


@pytest.fixture
def block_io(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("I/O is forbidden in this test")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(httpx, "Client", _boom)
    monkeypatch.setattr(sqlite3, "connect", _boom)
    yield


def test_assemble_succeeds_with_io_blocked(block_io) -> None:
    candidate = Phase2BCandidate(
        symbol="2330",
        asof_date="2026-04-30",
        final_score=78.0,
        tech_subtotal=32.0,
        chip_subtotal=18.0,
        fund_subtotal=22.0,
        sent_subtotal=6.0,
        classification="green",
        risk_off_applied=False,
        subscores=[],
        stage=2,
        rs_percentile=87,
        trend_template_passed=8,
        vcp_quality="breakout",
        pivot_price=832.0,
    )
    obj = build_entry_decision_input(
        candidate=candidate,
        candidate_name="台積電",
        candidate_sector="半導體",
        current_price=845.0,
        ema20_distance_pct=3.2,
        atr_14_pct=2.4,
        distance_from_52w_high_pct=4.1,
        distance_from_52w_low_pct=41.6,
        market=MarketSnapshot(
            taiex_close=20000.0,
            taiex_change_pct=0.5,
            risk_off=False,
            monthly_pnl_pct=-1.8,
        ),
        portfolio=PortfolioSnapshot(
            positions=[PortfolioPosition("2454", "半導體", 18.0)],
            total_exposure_pct=18.0,
        ),
        journal_stats=_FakeJournal(),
        rules_digest=RulesDigest(
            must_have=["a", "b", "c"],
            bonus_items=["1", "2", "3", "4", "5", "6", "7", "8"],
        ),
        available_tools=[],
        available_skills=[],
        trigger_at="2026-04-30T14:30:00+08:00",
    )
    assert obj.candidate.symbol == "2330"
    assert obj.input_schema_version == "v3.1"
