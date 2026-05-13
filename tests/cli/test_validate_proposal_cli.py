"""Integration tests for ``ohmystock validate-proposal``.

Spec: openspec/changes/wfa-validation-engine/specs/wfa-validation-engine/spec.md
(Requirement "CLI validate-proposal subcommand")
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from ohmystock.cli import app
from ohmystock.cli import _validate_proposal as cli_module
from ohmystock.data.sources.base import BarRow
from ohmystock.proposal import (
    ProposalDraft,
    transition_proposal,
    write_proposal,
)
from ohmystock.validation import wfa as wfa_module


_TPE = timezone(timedelta(hours=8))
_RUNNER = CliRunner()
_PERIOD = "from=2025-01-02,to=2025-12-30"


def _synthetic_bars(n_days: int = 253, base_price: float = 100.0) -> list[BarRow]:
    rows: list[BarRow] = []
    current = date(2025, 1, 2)
    i = 0
    while len(rows) < n_days:
        if current.weekday() < 5:
            price = base_price + i * 0.5
            rows.append(
                BarRow(
                    ts=current.isoformat(),
                    o=price,
                    h=price,
                    l=price,
                    c=price,
                    v=1_000_000,
                    amount=int(price * 1_000_000),
                )
            )
            i += 1
        current = current + timedelta(days=1)
    return rows


def _draft(topic: str = "vcp-volume-threshold") -> ProposalDraft:
    return ProposalDraft(
        topic=topic,
        target_section="cheatsheet §6.4",
        created_by="wfa-cli-test",
        created_at=datetime(2026, 4, 30, 19, 30, tzinfo=_TPE),
        review_id="manual-2026-04-01-to-2026-04-30",
        priority="high",
        description="VCP 量能 1.5 → 1.3。",
        motivation="metrics.json#/by_pattern/VCP n=8 win_rate=0.375。",
        diff_draft="```diff\n- a\n+ b\n```",
        expected_impact="vcp.py。",
        risk_assessment="風險:過嚴漏 VCP。",
        validation_plan="WFA 5+1。",
        expected_improvement="0.565 → 0.60。",
    )


def _write_validating_proposal(proposals_dir: Path) -> Path:
    proposals_dir.mkdir(parents=True, exist_ok=True)
    path = write_proposal(_draft(), proposals_dir)
    return transition_proposal(path, "validating", actor="setup")


def _patch_cli_seams(
    monkeypatch: pytest.MonkeyPatch,
    proposals_dir: Path,
    bars: dict[str, list[BarRow]] | None = None,
) -> None:
    """Override the two CLI factories so tests never touch SQLite/cwd."""
    monkeypatch.setattr(
        cli_module,
        "_PROPOSALS_ROOT_FACTORY",
        lambda: proposals_dir,
    )

    def loader(symbol: str, _start: str, _end: str) -> list[BarRow]:
        if bars is None:
            return []
        return bars.get(symbol, [])

    monkeypatch.setattr(
        cli_module,
        "_MARKET_DATA_LOADER_FACTORY",
        lambda: loader,
    )


# ---- 10.2: happy-path pass exits 0 ----------------------------------------


def test_cli_happy_path_pass_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposals_dir = tmp_path / "proposals"
    proposal_path = _write_validating_proposal(proposals_dir)
    slug = proposal_path.stem
    _patch_cli_seams(monkeypatch, proposals_dir, {"2330": _synthetic_bars()})

    result = _RUNNER.invoke(
        app,
        [
            "validate-proposal",
            slug,
            "--strategy",
            "sma_cross",
            "--period",
            _PERIOD,
            "--param",
            "fast=10",
            "--universe",
            "2330",
            "--initial-capital",
            "1000000",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "verdict=pass" in result.stdout
    assert slug in result.stdout
    moved = proposals_dir / "PENDING_REVIEW" / f"{slug}.md"
    assert moved.is_file()
    assert "status: approved" in moved.read_text(encoding="utf-8")


# ---- 10.3: fail exits 1 ---------------------------------------------------


def test_cli_fail_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposals_dir = tmp_path / "proposals"
    proposal_path = _write_validating_proposal(proposals_dir)
    slug = proposal_path.stem
    _patch_cli_seams(monkeypatch, proposals_dir, {"2330": _synthetic_bars()})

    call_state = {"i": 0}

    def fake_run_one(
        strategy: Any, _bars: Any, _period: Any, _capital: Any
    ) -> dict[str, float]:
        del strategy
        idx = call_state["i"] % 4
        call_state["i"] += 1
        if idx == 2:
            return {"sharpe": 2.0, "max_drawdown": -0.05, "win_rate": 0.5}
        if idx == 3:
            return {"sharpe": 0.5, "max_drawdown": -0.05, "win_rate": 0.5}
        return {"sharpe": 1.0, "max_drawdown": -0.05, "win_rate": 0.5}

    monkeypatch.setattr(wfa_module, "_run_one", fake_run_one)

    result = _RUNNER.invoke(
        app,
        [
            "validate-proposal",
            slug,
            "--strategy",
            "sma_cross",
            "--period",
            _PERIOD,
            "--param",
            "fast=10",
            "--universe",
            "2330",
            "--initial-capital",
            "1000000",
        ],
    )

    assert result.exit_code == 1, result.stdout
    assert "verdict=fail" in result.stdout
    assert (proposals_dir / "rejected" / f"{slug}.md").is_file()


# ---- 10.4: dry-run always exits 0, no write, no transition ----------------


def test_cli_dry_run_always_exits_0_no_write_no_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposals_dir = tmp_path / "proposals"
    proposal_path = _write_validating_proposal(proposals_dir)
    slug = proposal_path.stem
    _patch_cli_seams(monkeypatch, proposals_dir, {"2330": _synthetic_bars()})

    result = _RUNNER.invoke(
        app,
        [
            "validate-proposal",
            slug,
            "--strategy",
            "sma_cross",
            "--period",
            _PERIOD,
            "--param",
            "fast=10",
            "--universe",
            "2330",
            "--initial-capital",
            "1000000",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "dry_run=true" in result.stdout
    assert proposal_path.is_file()
    assert "status: validating" in proposal_path.read_text(encoding="utf-8")
    assert not (proposals_dir / f"{slug}.validation.json").exists()


# ---- 10.5: status guard short-circuits ------------------------------------


def test_cli_status_not_validating_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposals_dir = tmp_path / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    proposal_path = write_proposal(_draft(), proposals_dir)  # status=pending
    slug = proposal_path.stem
    _patch_cli_seams(monkeypatch, proposals_dir, {"2330": _synthetic_bars()})

    result = _RUNNER.invoke(
        app,
        [
            "validate-proposal",
            slug,
            "--strategy",
            "sma_cross",
            "--period",
            _PERIOD,
        ],
    )

    assert result.exit_code == 2, result.stdout
    assert "must be 'validating'" in result.stdout


# ---- 10.6: unknown strategy exits 2 ---------------------------------------


def test_cli_unknown_strategy_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposals_dir = tmp_path / "proposals"
    proposal_path = _write_validating_proposal(proposals_dir)
    slug = proposal_path.stem
    _patch_cli_seams(monkeypatch, proposals_dir, {"2330": _synthetic_bars()})

    result = _RUNNER.invoke(
        app,
        [
            "validate-proposal",
            slug,
            "--strategy",
            "made_up",
            "--period",
            _PERIOD,
        ],
    )

    assert result.exit_code == 2, result.stdout
    assert "unknown_strategy" in result.stdout
    assert "made_up" in result.stdout


# ---- 10.7: unparseable param exits 2 --------------------------------------


def test_cli_unparseable_param_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposals_dir = tmp_path / "proposals"
    proposal_path = _write_validating_proposal(proposals_dir)
    slug = proposal_path.stem
    _patch_cli_seams(monkeypatch, proposals_dir, {"2330": _synthetic_bars()})

    result = _RUNNER.invoke(
        app,
        [
            "validate-proposal",
            slug,
            "--strategy",
            "sma_cross",
            "--period",
            _PERIOD,
            "--param",
            "foo=bar%bad",
        ],
    )

    assert result.exit_code == 2, result.stdout
    assert "unparseable_param" in result.stdout


# ---- 10.8: proposal not found exits 2 -------------------------------------


def test_cli_proposal_not_found_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposals_dir = tmp_path / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    _patch_cli_seams(monkeypatch, proposals_dir, {"2330": _synthetic_bars()})

    result = _RUNNER.invoke(
        app,
        [
            "validate-proposal",
            "does-not-exist",
            "--strategy",
            "sma_cross",
            "--period",
            _PERIOD,
        ],
    )

    assert result.exit_code == 2, result.stdout
    assert "proposal not found" in result.stdout
