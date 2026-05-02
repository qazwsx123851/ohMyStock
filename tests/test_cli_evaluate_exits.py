"""CLI tests for ``ohmystock evaluate-exits``.

Spec: openspec/changes/exit-engine-v0/specs/cli-and-config/spec.md

Each test isolates the journal DB via monkeypatched OHMYSTOCK_DB_PATH +
tmp_path, seeds a confirmed entry directly, then invokes the CLI.
``evaluate_open_positions`` is monkeypatched per scenario to drive deterministic
``ExitResult`` lists / errors without touching live providers.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ohmystock.cli import app
from ohmystock.exit_engine import ExitDecision, ExitEngineError, ExitResult
from ohmystock.journal.schema import init_schema


runner = CliRunner()


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "journal.db"
    monkeypatch.setenv("OHMYSTOCK_DB_PATH", str(db_path))
    return db_path


def _seed_confirmed(
    db_path: Path,
    *,
    decision_id: str = "dec_2026-04-30T10-00-00_2330",
    symbol: str = "2330",
    actual_entry_price: float = 832.0,
    stop_loss_price: float = 784.58,
    expected_holding_days: int = 10,
    human_confirmed_at: str = "2026-04-30T10:00:00+08:00",
    atr_at_entry: float = 23.712,
) -> str:
    conn = sqlite3.connect(str(db_path))
    init_schema(conn)
    payload = {
        "decision_status": "confirmed",
        "actual_entry_price": actual_entry_price,
        "actual_qty": 1000,
        "stop_loss_price": stop_loss_price,
        "atr_at_entry": atr_at_entry,
        "expected_holding_days": expected_holding_days,
        "human_confirmed_by": "mark",
        "human_confirmed_at": human_confirmed_at,
        "atr_14_pct": 2.85,
        "current_price": actual_entry_price,
        "final_sizing_pct": 16.5,
    }
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        (
            decision_id,
            symbol,
            human_confirmed_at,
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()
    return decision_id


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------


def test_evaluate_exits_help_shows_flags_and_lifecycle_literals() -> None:
    result = runner.invoke(app, ["evaluate-exits", "--help"])
    assert result.exit_code == 0
    for needle in [
        "--asof",
        "--symbol",
        "--price",
        "--db",
        "--json",
        "kind=exit",
        "closed",
        "hit_stop_loss",
        "hit_t1",
        "time_stop",
    ]:
        assert needle in result.output, f"help output missing {needle!r}"


def test_root_help_lists_evaluate_exits_subcommand() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "evaluate-exits" in result.output


# ---------------------------------------------------------------------------
# Usage errors
# ---------------------------------------------------------------------------


def test_evaluate_exits_missing_asof_exit_2() -> None:
    result = runner.invoke(app, ["evaluate-exits"])
    assert result.exit_code == 2


def test_evaluate_exits_invalid_asof_exit_2(isolated_db: Path) -> None:
    result = runner.invoke(app, ["evaluate-exits", "--asof", "not-a-date"])
    assert result.exit_code == 2
    combined = (result.stderr or "") + result.output
    assert "asof" in combined or "date" in combined


def test_evaluate_exits_price_without_symbol_exit_2(isolated_db: Path) -> None:
    result = runner.invoke(
        app, ["evaluate-exits", "--asof", "2026-05-07", "--price", "900.0"]
    )
    assert result.exit_code == 2
    combined = (result.stderr or "") + result.output
    assert "--price" in combined and "--symbol" in combined


# ---------------------------------------------------------------------------
# Success paths (monkeypatch evaluate_open_positions)
# ---------------------------------------------------------------------------


def test_evaluate_exits_hit_t1_success_exit_0(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decision_id = _seed_confirmed(isolated_db)

    def _fake_eval(conn, *, market_data, asof, clock, symbol_filter=None):
        return [
            ExitResult(
                decision_id=decision_id,
                action="closed",
                decision=ExitDecision(
                    exit_tag="hit_t1",
                    exit_reason="close 900.0 ≥ T1 881.92",
                    actual_exit_price=900.0,
                    pnl_pct=8.17,
                    hold_days=5,
                ),
            )
        ]

    monkeypatch.setattr(
        "ohmystock.cli._evaluate_exits.evaluate_open_positions", _fake_eval
    )
    result = runner.invoke(
        app,
        [
            "evaluate-exits",
            "--asof",
            "2026-05-07",
            "--symbol",
            "2330",
            "--price",
            "900.0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert decision_id in result.output
    assert "hit_t1" in result.output
    assert "closed" in result.output
    assert "8.17" in result.output


def test_evaluate_exits_zero_closed_exit_0(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "ohmystock.cli._evaluate_exits.evaluate_open_positions",
        lambda *a, **kw: [],
    )
    result = runner.invoke(app, ["evaluate-exits", "--asof", "2026-05-07"])
    assert result.exit_code == 0
    assert "0 closed" in result.output


def test_evaluate_exits_mixed_closed_and_held_exit_0(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = ExitResult(
        decision_id="dec_closed",
        action="closed",
        decision=ExitDecision(
            exit_tag="hit_t1",
            exit_reason="...",
            actual_exit_price=900.0,
            pnl_pct=8.17,
            hold_days=5,
        ),
    )
    held = ExitResult(decision_id="dec_held", action="held", decision=None)
    monkeypatch.setattr(
        "ohmystock.cli._evaluate_exits.evaluate_open_positions",
        lambda *a, **kw: [closed, held],
    )
    result = runner.invoke(app, ["evaluate-exits", "--asof", "2026-05-07"])
    assert result.exit_code == 0
    assert "1 closed, 1 held" in result.output
    assert "dec_closed" in result.output
    assert "dec_held" in result.output


def test_evaluate_exits_market_data_unavailable_exit_3(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(*a, **kw):
        raise ExitEngineError(
            "market_data_unavailable",
            "lookup failed",
            failed_symbols=["2317"],
        )

    monkeypatch.setattr(
        "ohmystock.cli._evaluate_exits.evaluate_open_positions", _raise
    )
    result = runner.invoke(app, ["evaluate-exits", "--asof", "2026-05-07"])
    assert result.exit_code == 3
    combined = (result.stderr or "") + result.output
    assert "market_data_unavailable" in combined
    assert "2317" in combined


def test_evaluate_exits_json_output(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decision_id = _seed_confirmed(isolated_db)
    monkeypatch.setattr(
        "ohmystock.cli._evaluate_exits.evaluate_open_positions",
        lambda *a, **kw: [
            ExitResult(
                decision_id=decision_id,
                action="closed",
                decision=ExitDecision(
                    exit_tag="hit_t1",
                    exit_reason="...",
                    actual_exit_price=900.0,
                    pnl_pct=8.17,
                    hold_days=5,
                ),
            )
        ],
    )
    result = runner.invoke(
        app,
        [
            "evaluate-exits",
            "--asof",
            "2026-05-07",
            "--symbol",
            "2330",
            "--price",
            "900.0",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["asof"] == "2026-05-07"
    assert payload["exit_code"] == 0
    assert isinstance(payload["evaluated"], list)
    row = payload["evaluated"][0]
    assert row["decision_id"] == decision_id
    assert row["action"] == "closed"
    assert row["exit_tag"] == "hit_t1"
    assert row["actual_exit_price"] == 900.0
    assert row["pnl_pct"] == 8.17
    assert row["hold_days"] == 5
