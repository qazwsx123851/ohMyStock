"""`ohmystock score watchlist` CLI subcommand — typer.testing coverage.

Spec: openspec/changes/phase-2b-deferred-cli/specs/cli-and-config/spec.md
("`ohmystock score watchlist` 子命令" requirement).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

from ohmystock.cli import app


runner = CliRunner()


def _candidate(
    symbol: str,
    final_score: float,
    *,
    tech: float = 0.0,
    chip: float = 0.0,
    fund: float = 0.0,
    sent: float = 0.0,
    classification: str = "green",
    risk_off: bool = False,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "asof_date": "2026-04-30",
        "final_score": final_score,
        "tech_subtotal": tech,
        "chip_subtotal": chip,
        "fund_subtotal": fund,
        "sent_subtotal": sent,
        "classification": classification,
        "risk_off_applied": risk_off,
        "subscores": [],
    }


def _envelope(*candidates: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "elapsed_ms": 12,
        "data": {"asof_date": "2026-04-30", "candidates": list(candidates)},
        "error": None,
    }


def test_help_lists_required_flags() -> None:
    result = runner.invoke(app, ["score", "watchlist", "--help"])
    assert result.exit_code == 0, result.stdout
    for flag in ("--asof", "--symbols", "--top-n", "--json"):
        assert flag in result.stdout, f"missing flag {flag} in --help"


def test_csv_success_path(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _envelope(
        _candidate(
            "2330",
            78.0,
            tech=30.0,
            chip=18.0,
            fund=25.0,
            sent=5.0,
            classification="green",
            risk_off=False,
        )
    )
    monkeypatch.setattr(
        "ohmystock.cli._score.score_watchlist",
        lambda **kwargs: env,
    )

    result = runner.invoke(app, ["score", "watchlist", "--asof", "2026-04-30", "--symbols", "2330"])
    assert result.exit_code == 0, result.stdout + result.stderr
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "symbol,final_score,classification,risk_off_applied,tech,chip,fund,sent"
    assert lines[1] == "2330,78.0,green,false,30.0,18.0,25.0,5.0"


def test_json_success_path(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _envelope(_candidate("2330", 78.0, tech=30.0, chip=18.0, fund=25.0, sent=5.0))
    monkeypatch.setattr(
        "ohmystock.cli._score.score_watchlist",
        lambda **kwargs: env,
    )

    result = runner.invoke(
        app,
        ["score", "watchlist", "--asof", "2026-04-30", "--symbols", "2330", "--json"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == env


def test_top_n_truncates_after_sort(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _envelope(
        _candidate("2330", 70.0),
        _candidate("2317", 80.0),
    )
    monkeypatch.setattr(
        "ohmystock.cli._score.score_watchlist",
        lambda **kwargs: env,
    )

    result = runner.invoke(
        app,
        [
            "score",
            "watchlist",
            "--asof",
            "2026-04-30",
            "--symbols",
            "2330,2317",
            "--top-n",
            "1",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 2  # header + one data row
    assert lines[1].startswith("2317,80.0,")
    assert "2330" not in result.stdout


def test_sort_descending_with_symbol_tie_break(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _envelope(
        _candidate("2317", 80.0),
        _candidate("2330", 80.0),
        _candidate("1101", 60.0),
    )
    monkeypatch.setattr(
        "ohmystock.cli._score.score_watchlist",
        lambda **kwargs: env,
    )

    result = runner.invoke(
        app,
        [
            "score",
            "watchlist",
            "--asof",
            "2026-04-30",
            "--symbols",
            "1101,2317,2330",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    lines = result.stdout.strip().splitlines()
    assert lines[1].startswith("2317,80.0,")
    assert lines[2].startswith("2330,80.0,")
    assert lines[3].startswith("1101,60.0,")


def test_validation_error_to_stderr_exit_1() -> None:
    # Real score_watchlist (no monkeypatch) — invalid asof format.
    result = runner.invoke(
        app,
        ["score", "watchlist", "--asof", "2026/04/30", "--symbols", "2330"],
    )
    assert result.exit_code == 1
    assert "INVALID_INPUT" in result.stderr
    assert result.stdout == ""


def test_missing_required_flags() -> None:
    result = runner.invoke(app, ["score", "watchlist"])
    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert "--asof" in combined or "--symbols" in combined
