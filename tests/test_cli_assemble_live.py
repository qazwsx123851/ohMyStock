"""End-to-end CLI tests for assemble-entry-input with live providers.

Spec: openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from ohmystock.cli import app
from ohmystock.scoring import Phase2BCandidate
from ohmystock.swarm import (
    CandidateLiveSnapshot,
    LiveProviderError,
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


def _fake_snapshot(symbol: str, asof: str) -> CandidateLiveSnapshot:
    return CandidateLiveSnapshot(
        current_price=845.0,
        ema20_distance_pct=3.2,
        atr_14_pct=2.4,
        distance_from_52w_high_pct=4.1,
        distance_from_52w_low_pct=41.6,
    )


class _MarketProvider:
    def __init__(
        self, *, risk_off: bool, diagnostics: dict[str, str] | None = None
    ) -> None:
        self._risk_off = risk_off
        self.last_diagnostics = diagnostics or {}

    def get(self) -> MarketSnapshot:
        return MarketSnapshot(20000.0, 0.5, self._risk_off, -1.8)


class _PortfolioProvider:
    def __init__(self, *, sectors: list[str]) -> None:
        self._sectors = sectors

    def get(self) -> PortfolioSnapshot:
        positions = [
            PortfolioPosition(f"23{idx:02d}", sector, 18.0)
            for idx, sector in enumerate(self._sectors)
        ]
        return PortfolioSnapshot(
            positions=positions,
            total_exposure_pct=18.0 * len(positions),
        )


class _Journal:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def recent_winrate(self, n: int = 20) -> float:
        return 0.55

    def consecutive_loss(self) -> int:
        return 1


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    market: _MarketProvider,
    portfolio: _PortfolioProvider,
    candidate_snapshot=_fake_snapshot,
) -> None:
    from ohmystock.cli import _assemble as cli_assemble

    monkeypatch.setattr(
        cli_assemble, "LiveMarketSnapshotProvider", lambda asof: market
    )
    monkeypatch.setattr(
        cli_assemble, "LivePortfolioSnapshotProvider", lambda asof: portfolio
    )
    monkeypatch.setattr(cli_assemble, "LiveJournalStatsProvider", _Journal)
    monkeypatch.setattr(
        cli_assemble, "live_candidate_snapshot", candidate_snapshot
    )
    monkeypatch.setattr(
        cli_assemble,
        "_candidates_via_score_watchlist",
        lambda asof, symbol: [_candidate()],
    )


def test_cli_e2e_with_seeded_data_returns_exit_0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(
        monkeypatch,
        market=_MarketProvider(risk_off=False),
        portfolio=_PortfolioProvider(sectors=["半導體"]),
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
    assert payload["input_schema_version"] == "v3.1"
    assert payload["decision_id"] == "dec_2026-04-30T14-30-00_2330"
    assert payload["candidate"]["current_price"] == 845.0


def test_cli_stale_data_returns_exit_5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_stale(symbol: str, asof: str) -> CandidateLiveSnapshot:
        raise LiveProviderError(
            code="STALE_DATA", message="taiex bars >5 business days old"
        )

    _patch(
        monkeypatch,
        market=_MarketProvider(risk_off=False),
        portfolio=_PortfolioProvider(sectors=["半導體"]),
        candidate_snapshot=_raise_stale,
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
    assert result.exit_code == 5
    assert "STALE_DATA" in result.output


def test_cli_data_unavailable_returns_exit_4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(symbol: str, asof: str) -> CandidateLiveSnapshot:
        raise LiveProviderError(code="DATA_UNAVAILABLE", message="no cache")

    _patch(
        monkeypatch,
        market=_MarketProvider(risk_off=False),
        portfolio=_PortfolioProvider(sectors=["半導體"]),
        candidate_snapshot=_raise,
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
    assert result.exit_code == 4
    assert "DATA_UNAVAILABLE" in result.output


def test_cli_unwired_signals_warning_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(
        monkeypatch,
        market=_MarketProvider(
            risk_off=False,
            diagnostics={"spy_5d_return": "unknown", "vix": "unknown"},
        ),
        portfolio=_PortfolioProvider(sectors=["半導體"]),
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
    assert "warning:" in result.output
    assert "spy_5d_return" in result.output


def test_cli_unclassified_sector_warning_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(
        monkeypatch,
        market=_MarketProvider(risk_off=False),
        portfolio=_PortfolioProvider(sectors=["未分類"]),
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
    assert "warning:" in result.output
    assert "未分類" in result.output
