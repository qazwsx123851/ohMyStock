"""CLI tests for ``ohmystock confirm``.

Spec: openspec/changes/confirm-gate-v0/specs/cli-and-config/spec.md

Each test isolates the journal DB via monkeypatched OHMYSTOCK_DB_PATH +
tmp_path, seeds a pending entry directly, then invokes the CLI.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ohmystock.cli import app
from ohmystock.journal.schema import init_schema


runner = CliRunner()


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "journal.db"
    monkeypatch.setenv("OHMYSTOCK_DB_PATH", str(db_path))
    monkeypatch.delenv("OHMYSTOCK_AUTO_EXECUTE", raising=False)
    return db_path


def _seed_pending(
    db_path: Path,
    *,
    decision_id: str = "dec_2026-05-02T10-00-00_2330",
    symbol: str = "2330",
    created_at: str = "2026-05-02T10:00:00+08:00",
    final_sizing_pct: float = 16.5,
    current_price: float = 832.0,
) -> str:
    conn = sqlite3.connect(str(db_path))
    init_schema(conn)
    payload = {
        "decision_status": "pending_confirm",
        "final_sizing_pct": final_sizing_pct,
        "current_price": current_price,
        "actual_entry_price": None,
        "actual_qty": None,
        "human_confirmed_by": None,
        "human_confirmed_at": None,
    }
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        (decision_id, symbol, created_at, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    return decision_id


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------


def test_confirm_help_lists_flags_and_lifecycle_literals() -> None:
    result = runner.invoke(app, ["confirm", "--help"])
    assert result.exit_code == 0
    for needle in [
        "--list",
        "--reject",
        "--sweep-expired",
        "--user",
        "--reason",
        "--timeout-minutes",
        "--default-capital-twd",
        "--json",
        "pending_confirm",
        "expire",
    ]:
        assert needle in result.output, f"help output missing {needle!r}"


def test_root_help_lists_confirm_subcommand() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "confirm" in result.output


# ---------------------------------------------------------------------------
# --list
# ---------------------------------------------------------------------------


def test_confirm_list_with_pending_row_exit_0(isolated_db: Path) -> None:
    decision_id = _seed_pending(isolated_db)
    result = runner.invoke(app, ["confirm", "--list"])
    assert result.exit_code == 0, result.output
    assert decision_id in result.output
    assert "2330" in result.output
    assert "832" in result.output


def test_confirm_list_empty_exit_0(isolated_db: Path) -> None:
    result = runner.invoke(app, ["confirm", "--list"])
    assert result.exit_code == 0
    assert "no pending_confirm" in result.output


# ---------------------------------------------------------------------------
# <decision_id> confirm
# ---------------------------------------------------------------------------


def test_confirm_decision_id_success_exit_0(isolated_db: Path) -> None:
    decision_id = _seed_pending(isolated_db)
    result = runner.invoke(app, ["confirm", decision_id, "--user", "mark@local"])
    assert result.exit_code == 0, result.output
    assert decision_id in result.output
    assert "2330" in result.output
    assert "1000" in result.output  # qty
    assert "832.0" in result.output  # fill_price
    assert "confirmed" in result.output


def test_confirm_decision_id_not_found_exit_2(isolated_db: Path) -> None:
    result = runner.invoke(app, ["confirm", "dec_does_not_exist"])
    assert result.exit_code == 2
    assert "not_found" in (result.stderr or result.output)


def test_confirm_already_confirmed_exit_2(isolated_db: Path) -> None:
    decision_id = _seed_pending(isolated_db)
    runner.invoke(app, ["confirm", decision_id, "--user", "mark"])
    result = runner.invoke(app, ["confirm", decision_id, "--user", "mark"])
    assert result.exit_code == 2
    assert "not_pending" in (result.stderr or result.output)


# ---------------------------------------------------------------------------
# <decision_id> --reject
# ---------------------------------------------------------------------------


def test_confirm_reject_exit_1(isolated_db: Path) -> None:
    decision_id = _seed_pending(isolated_db)
    result = runner.invoke(
        app,
        [
            "confirm",
            decision_id,
            "--reject",
            "--reason",
            "盤勢不對",
            "--user",
            "mark",
        ],
    )
    assert result.exit_code == 1, result.output
    assert decision_id in result.output
    assert "rejected" in result.output
    assert "盤勢不對" in result.output


def test_confirm_reject_without_decision_id_exit_2(isolated_db: Path) -> None:
    result = runner.invoke(app, ["confirm", "--reject"])
    # Mutually-exclusive guard fires first (mode_count=0) → exit 2
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# --sweep-expired
# ---------------------------------------------------------------------------


def test_confirm_sweep_expired_exit_0(isolated_db: Path) -> None:
    # Seed a row that is definitely older than timeout.
    _seed_pending(isolated_db, created_at="2020-01-01T00:00:00+08:00")
    result = runner.invoke(app, ["confirm", "--sweep-expired"])
    assert result.exit_code == 0, result.output
    assert "1 expired" in result.output


def test_confirm_sweep_expired_zero_rows_exit_0(isolated_db: Path) -> None:
    result = runner.invoke(app, ["confirm", "--sweep-expired"])
    assert result.exit_code == 0
    assert "0 expired" in result.output


# ---------------------------------------------------------------------------
# Mutual exclusion
# ---------------------------------------------------------------------------


def test_confirm_list_with_decision_id_exit_2(isolated_db: Path) -> None:
    decision_id = _seed_pending(isolated_db)
    result = runner.invoke(app, ["confirm", decision_id, "--list"])
    assert result.exit_code == 2
    assert "mutually exclusive" in (result.stderr or result.output)


def test_confirm_no_action_exit_2(isolated_db: Path) -> None:
    """No <decision_id>, no --list, no --sweep-expired → mode_count=0 → exit 2."""
    result = runner.invoke(app, ["confirm"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# OHMYSTOCK_AUTO_EXECUTE=true warning
# ---------------------------------------------------------------------------


def test_confirm_auto_execute_true_emits_warning_but_runs(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE", "true")
    decision_id = _seed_pending(isolated_db)
    result = runner.invoke(
        app,
        ["confirm", decision_id, "--user", "mark"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    combined = (result.stderr or "") + result.output
    assert "auto mode requires the Phase 3.5 breaker" in combined
    assert "confirmed" in result.output


# ---------------------------------------------------------------------------
# --json output
# ---------------------------------------------------------------------------


def test_confirm_json_output_for_confirm(isolated_db: Path) -> None:
    decision_id = _seed_pending(isolated_db)
    result = runner.invoke(
        app, ["confirm", decision_id, "--user", "mark@local", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["action"] == "confirm"
    assert payload["decision_id"] == decision_id
    assert payload["status"] == "confirmed"
    assert payload["exit_code"] == 0
    fill = payload["fill"]
    assert fill["fill_price"] == 832.0
    assert fill["filled_qty"] == 1000
    assert fill["fill_ts"].endswith("+08:00")


def test_confirm_json_output_for_list(isolated_db: Path) -> None:
    _seed_pending(isolated_db)
    result = runner.invoke(app, ["confirm", "--list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "list"
    assert len(payload["pending"]) == 1
    assert payload["pending"][0]["symbol"] == "2330"
