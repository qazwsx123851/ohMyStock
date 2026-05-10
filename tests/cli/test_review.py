"""Coverage for ``ohmystock review``.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-cli/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ohmystock.cli import _review as cli_review
from ohmystock.cli import app
from ohmystock.journal.schema import init_schema
from ohmystock.review import FakeReviewLLM


_RUNNER = CliRunner()


@pytest.fixture()
def empty_db(tmp_path: Path, monkeypatch) -> Path:
    db_path = tmp_path / "journal.db"
    conn = sqlite3.connect(str(db_path))
    try:
        init_schema(conn)
    finally:
        conn.close()
    monkeypatch.setenv("OHMYSTOCK_DB_PATH", str(db_path))
    return db_path


@pytest.fixture()
def fake_llm_factory(monkeypatch):
    fakes = {
        "attributor": FakeReviewLLM(responses=[{"items": []}]),
        "critic": FakeReviewLLM(
            responses=[
                "### 高警示\n\n(無)\n\n### 中警示\n\n(無)\n\n### 觀察項\n\n(無)\n"
            ]
        ),
        "proposer": FakeReviewLLM(responses=[]),
    }

    def factory(node: str):
        return fakes[node]

    monkeypatch.setattr(cli_review, "_LLM_FACTORY_OVERRIDE", factory)
    return fakes


@pytest.fixture()
def cheatsheet_in_cwd(tmp_path: Path, monkeypatch):
    cwd_dir = tmp_path / "cwd"
    docs = cwd_dir / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "workflow-cheatsheet.md").write_text("cheatsheet", encoding="utf-8")
    monkeypatch.chdir(cwd_dir)
    return cwd_dir


def test_help_lists_all_eight_flags() -> None:
    result = _RUNNER.invoke(app, ["review", "--help"])
    assert result.exit_code == 0
    for flag in [
        "--from",
        "--to",
        "--out-dir",
        "--proposals-dir",
        "--limit-trades",
        "--dry-run",
        "--force",
        "--json",
    ]:
        assert flag in result.output


def test_missing_from_returns_exit_code_2(empty_db, cheatsheet_in_cwd) -> None:
    result = _RUNNER.invoke(app, ["review", "--to", "2026-04-30"])
    assert result.exit_code == 2


def test_invalid_iso_date_returns_exit_code_2(empty_db, cheatsheet_in_cwd) -> None:
    result = _RUNNER.invoke(
        app, ["review", "--from", "2026/04/01", "--to", "2026-04-30"]
    )
    assert result.exit_code == 2


def test_from_after_to_returns_exit_code_2(empty_db, cheatsheet_in_cwd) -> None:
    result = _RUNNER.invoke(
        app, ["review", "--from", "2026-04-30", "--to", "2026-04-01"]
    )
    assert result.exit_code == 2
    assert "period_from" in result.stderr


def test_limit_trades_zero_returns_exit_code_2(empty_db, cheatsheet_in_cwd) -> None:
    result = _RUNNER.invoke(
        app,
        [
            "review",
            "--from",
            "2026-04-01",
            "--to",
            "2026-04-30",
            "--limit-trades",
            "0",
        ],
    )
    assert result.exit_code == 2


def test_dry_run_json_succeeds_on_empty_period(
    empty_db, cheatsheet_in_cwd, fake_llm_factory
) -> None:
    out_dir = cheatsheet_in_cwd / "reviews"
    result = _RUNNER.invoke(
        app,
        [
            "review",
            "--from",
            "2026-04-01",
            "--to",
            "2026-04-30",
            "--out-dir",
            str(out_dir),
            "--proposals-dir",
            str(cheatsheet_in_cwd / "proposals"),
            "--dry-run",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.stdout + "\n--stderr--\n" + result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload["proposals_files"] == []
    assert payload["dry_run"] is True
    assert payload["review_id"] == "manual-2026-04-01-to-2026-04-30"
    assert payload["period"] == {"from": "2026-04-01", "to": "2026-04-30"}
    assert not (out_dir / "manual-2026-04-01-to-2026-04-30").exists()


def test_force_required_when_review_exists(
    empty_db, cheatsheet_in_cwd, fake_llm_factory
) -> None:
    out_dir = cheatsheet_in_cwd / "reviews"
    review_dir = out_dir / "manual-2026-04-01-to-2026-04-30"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "data.json").write_text("{}", encoding="utf-8")

    result = _RUNNER.invoke(
        app,
        [
            "review",
            "--from",
            "2026-04-01",
            "--to",
            "2026-04-30",
            "--out-dir",
            str(out_dir),
            "--proposals-dir",
            str(cheatsheet_in_cwd / "proposals"),
        ],
    )
    assert result.exit_code == 2
    assert "already exists" in result.stderr


def test_runtime_error_returns_exit_code_3_with_redacted_traceback(
    empty_db, cheatsheet_in_cwd, monkeypatch
) -> None:
    api_key = "sk-ant-FAKE_KEY_DO_NOT_LEAK_12345"
    monkeypatch.setenv("ANTHROPIC_API_KEY", api_key)

    # Seed a closed trade so attributor actually runs the LLM (it
    # short-circuits on empty data_loader output).
    import json
    conn = sqlite3.connect(str(empty_db))
    try:
        for kind, payload in [
            (
                "entry",
                {
                    "actual_entry_price": 100.0,
                    "actual_qty": 1,
                    "cited_skills": ["technical/breakout"],
                    "entry_thesis": "t",
                    "llm_reasoning": "t",
                    "llm_confidence": 0.75,
                    "risk_flags": [],
                    "sector": "半導體",
                    "decision_status": "closed",
                },
            ),
            (
                "exit",
                {
                    "exit_tag": "discretionary",
                    "exit_reason": "test",
                    "actual_exit_price": 106.0,
                    "pnl_pct": 6.0,
                    "hold_days": 5,
                    "exited_at": "2026-04-22T13:30:00+08:00",
                    "close_price_evaluated": 106.0,
                },
            ),
        ]:
            ts = (
                "2026-04-15T14:00:00+08:00" if kind == "entry"
                else "2026-04-22T13:30:00+08:00"
            )
            conn.execute(
                "INSERT INTO journal_entries"
                "(decision_id, kind, symbol, created_at, payload_json) "
                "VALUES (?, ?, ?, ?, ?)",
                ("dec-boom", kind, "2330", ts, json.dumps(payload)),
            )
        conn.commit()
    finally:
        conn.close()

    class _BoomLLM:
        def __init__(self) -> None:
            self.model = "fake://boom"
            self.usages: list = []

        def complete(self, *args, **kwargs):
            raise RuntimeError(f"upstream broke; key={api_key}")

    def factory(node: str):
        return _BoomLLM()

    monkeypatch.setattr(cli_review, "_LLM_FACTORY_OVERRIDE", factory)

    class _StubMarketData:
        def select_bars(self, symbol, exit_date, days):
            return [105.0] * days

    monkeypatch.setattr(cli_review, "_MARKET_DATA_OVERRIDE", _StubMarketData())

    out_dir = cheatsheet_in_cwd / "reviews"
    result = _RUNNER.invoke(
        app,
        [
            "review",
            "--from",
            "2026-04-01",
            "--to",
            "2026-04-30",
            "--out-dir",
            str(out_dir),
            "--proposals-dir",
            str(cheatsheet_in_cwd / "proposals"),
        ],
    )

    assert result.exit_code == 3, result.stdout + "\n" + result.stderr
    assert api_key not in result.stderr
    assert "<redacted>" in result.stderr
