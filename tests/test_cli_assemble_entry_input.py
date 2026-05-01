"""CLI tests for ``oms assemble-entry-input``.

Tests use the internal ``_run_assemble`` helper with injected fakes;
the typer-level test exercises argument parsing and exit codes via
``set_candidate_loader``.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ohmystock.cli import app
from ohmystock.cli._assemble import _run_assemble
from ohmystock.scoring import (
    Phase2BCandidate,
    reset_candidate_loader,
    set_candidate_loader,
)
from ohmystock.swarm import (
    AssemblerInputError,
    MarketSnapshot,
    PortfolioPosition,
    PortfolioSnapshot,
)


runner = CliRunner()


def _candidate(symbol: str = "2330", score: float = 78.0) -> Phase2BCandidate:
    return Phase2BCandidate(
        symbol=symbol,
        asof_date="2026-04-30",
        final_score=score,
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


class _FakeMarket:
    def get(self) -> MarketSnapshot:
        return MarketSnapshot(20000.0, 0.5, False, -1.8)


class _FakePortfolio:
    def get(self) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            positions=[PortfolioPosition("2454", "半導體", 18.0)],
            total_exposure_pct=18.0,
        )


class _FakeJournal:
    def recent_winrate(self, n: int = 20) -> float:
        return 0.55

    def consecutive_loss(self) -> int:
        return 1


def test_run_assemble_with_fakes_succeeds() -> None:
    obj = _run_assemble(
        symbol="2330",
        asof="2026-04-30",
        trigger_at="2026-04-30T14:30:00+08:00",
        candidates=[_candidate()],
        market_provider=_FakeMarket(),
        portfolio_provider=_FakePortfolio(),
        journal_provider=_FakeJournal(),
        candidate_name="台積電",
        candidate_sector="半導體",
        current_price=845.0,
        ema20_distance_pct=3.2,
        atr_14_pct=2.4,
        distance_from_52w_high_pct=4.1,
        distance_from_52w_low_pct=41.6,
    )
    assert obj.candidate.symbol == "2330"
    assert obj.input_schema_version == "v3.1"


def test_run_assemble_unknown_symbol_raises() -> None:
    with pytest.raises(AssemblerInputError, match="no qualifying"):
        _run_assemble(
            symbol="9999",
            asof="2026-04-30",
            trigger_at="2026-04-30T14:30:00+08:00",
            candidates=[_candidate("2330")],
            market_provider=_FakeMarket(),
            portfolio_provider=_FakePortfolio(),
            journal_provider=_FakeJournal(),
        )


def test_run_assemble_below_threshold_raises() -> None:
    with pytest.raises(AssemblerInputError, match="no qualifying"):
        _run_assemble(
            symbol="2330",
            asof="2026-04-30",
            trigger_at="2026-04-30T14:30:00+08:00",
            candidates=[_candidate(score=60.0)],
            market_provider=_FakeMarket(),
            portfolio_provider=_FakePortfolio(),
            journal_provider=_FakeJournal(),
        )


def test_cli_help_lists_assemble_entry_input() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "assemble-entry-input" in result.output


def test_cli_below_threshold_exits_non_zero(monkeypatch) -> None:
    from ohmystock.cli import _assemble as cli_assemble

    monkeypatch.setattr(
        cli_assemble,
        "_candidates_via_score_watchlist",
        lambda asof, symbol: [_candidate(score=64.9)],
    )

    result = runner.invoke(
        app,
        [
            "assemble-entry-input",
            "2330",
            "--asof",
            "2026-04-30",
            "--trigger-at",
            "2026-04-30T14:30:00+08:00",
        ],
    )
    assert result.exit_code == 2


def test_cli_writes_to_out_path(monkeypatch, tmp_path: Path) -> None:
    from ohmystock.cli import _assemble as cli_assemble

    monkeypatch.setattr(cli_assemble, "LiveMarketSnapshotProvider", _FakeMarket)
    monkeypatch.setattr(cli_assemble, "LivePortfolioSnapshotProvider", _FakePortfolio)
    monkeypatch.setattr(cli_assemble, "LiveJournalStatsProvider", _FakeJournal)
    monkeypatch.setattr(
        cli_assemble,
        "_candidates_via_score_watchlist",
        lambda asof, symbol: [_candidate()],
    )

    out = tmp_path / "result.json"
    result = runner.invoke(
        app,
        [
            "assemble-entry-input",
            "2330",
            "--asof",
            "2026-04-30",
            "--trigger-at",
            "2026-04-30T14:30:00+08:00",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["input_schema_version"] == "v3.1"
    assert payload["candidate"]["symbol"] == "2330"


def test_cli_emits_to_stdout_when_no_out(monkeypatch) -> None:
    from ohmystock.cli import _assemble as cli_assemble

    monkeypatch.setattr(cli_assemble, "LiveMarketSnapshotProvider", _FakeMarket)
    monkeypatch.setattr(cli_assemble, "LivePortfolioSnapshotProvider", _FakePortfolio)
    monkeypatch.setattr(cli_assemble, "LiveJournalStatsProvider", _FakeJournal)
    monkeypatch.setattr(
        cli_assemble,
        "_candidates_via_score_watchlist",
        lambda asof, symbol: [_candidate()],
    )

    result = runner.invoke(
        app,
        [
            "assemble-entry-input",
            "2330",
            "--asof",
            "2026-04-30",
            "--trigger-at",
            "2026-04-30T14:30:00+08:00",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["candidate"]["symbol"] == "2330"
