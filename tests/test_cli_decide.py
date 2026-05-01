"""Tests for ``ohmystock decide`` CLI subcommand."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterator

import pytest
from typer.testing import CliRunner

from ohmystock.cli import app
from ohmystock.decider.models import DeciderOutput
from ohmystock.decider.node import (
    DeciderOutputParseError,
    LLMUsage,
)
from ohmystock.decider.orchestrator import OrchestrationResult
from ohmystock.swarm.models import (
    CandidateSnapshot,
    EntryDecisionInput,
    MarketContext,
    RulesDigest,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    db = tmp_path / "journal.db"
    monkeypatch.setenv("OHMYSTOCK_DB_PATH", str(db))
    yield db


def _entry_input() -> EntryDecisionInput:
    return EntryDecisionInput(
        decision_id="dec_2026-04-30T14-30-00_2330",
        trigger_at="2026-04-30T14:30:00+08:00",
        candidate=CandidateSnapshot(
            symbol="2330",
            name="台積電",
            final_score=78,
            tech_score=32,
            chip_score=18,
            fundamental_score=22,
            sentiment_score=6,
            ema20_distance_pct=3.2,
            atr_14_pct=2.4,
            current_price=845.0,
            stage=2,
            rs_percentile=87,
            trend_template_passed=8,
            vcp_quality="breakout",
            pivot_price=832.0,
            distance_from_52w_high_pct=4.1,
            distance_from_52w_low_pct=41.6,
        ),
        market_context=MarketContext(
            risk_off=False,
            monthly_pnl_pct=-1.8,
            recent_20_winrate=0.55,
            consecutive_loss=1,
            existing_positions=[],
            total_exposure_pct=0.0,
            same_sector_count=0,
        ),
        rules_summary=RulesDigest(
            must_have=["a", "b", "c"],
            bonus_items=["1", "2", "3", "4", "5", "6", "7", "8"],
        ),
        available_tools=[],
        available_skills=[],
    )


def _decider_output(**overrides: object) -> DeciderOutput:
    payload: dict[str, object] = {
        "output_schema_version": "v3.1",
        "decision_id": "dec_2026-04-30T14-30-00_2330",
        "decided_at": "2026-04-30T14:34:22+08:00",
        "model": "claude-opus-4-7",
        "decision": "enter",
        "confidence": 0.83,
        "stage": 2,
        "rs_percentile": 87,
        "trend_template_passed": 8,
        "vcp_quality": "breakout",
        "pivot_price": 832.0,
        "must_have_check": [
            {"name": "trend_template_8_of_8", "pass": True, "evidence": "..."},
            {"name": "stage_2_confirmed", "pass": True, "evidence": "..."},
            {
                "name": "vcp_pivot_breakout_with_volume",
                "pass": True,
                "evidence": "...",
            },
        ],
        "bonus_score": 6,
        "bonus_breakdown": [],
        "proposed_sizing_pct": 18.0,
        "expected_holding_days": 8,
        "reasoning": "x" * 250,
        "cited_skills": ["technical/breakout"],
        "invalidation_conditions": [],
        "risk_flags": [],
        "tool_calls_summary": [],
    }
    payload.update(overrides)
    return DeciderOutput.model_validate(payload)


def _patch_assemble_and_decide(
    monkeypatch: pytest.MonkeyPatch,
    *,
    decide_result: OrchestrationResult | None = None,
    decide_raises: Exception | None = None,
    assemble_raises: Exception | None = None,
) -> None:
    """Wire up cli/_decide.py dependencies for a CLI test.

    The CLI module imports ``_run_assemble`` and ``decide_entry`` lazily, so
    we patch the *target modules* — Typer keeps its own reference once the
    command function is called.
    """
    from ohmystock.cli import _decide as cli_decide
    from ohmystock.cli import _assemble as cli_assemble
    from ohmystock.decider import orchestrator as orch_mod

    def fake_assemble(*, symbol: str, asof: str, trigger_at: str, **kw):
        if assemble_raises is not None:
            raise assemble_raises
        return _entry_input()

    monkeypatch.setattr(cli_assemble, "_run_assemble", fake_assemble)

    def fake_decide_entry(*args, **kwargs):
        if decide_raises is not None:
            raise decide_raises
        assert decide_result is not None
        return decide_result

    monkeypatch.setattr(orch_mod, "decide_entry", fake_decide_entry)
    monkeypatch.setattr(cli_decide, "decide_entry", fake_decide_entry)

    monkeypatch.setenv("OHMYSTOCK_DECIDER_MODEL", "fake://always-enter")
    monkeypatch.setenv("OHMYSTOCK_ALLOW_FAKE_DECIDER", "true")


def test_decide_help_lists_flags_and_warning(runner: CliRunner) -> None:
    result = runner.invoke(app, ["decide", "--help"])
    assert result.exit_code == 0
    assert "--symbol" in result.stdout
    assert "--asof" in result.stdout
    assert "--json" in result.stdout
    assert "pending_confirm" in result.stdout


def test_decide_enter_path_exit_0(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    isolated_db: Path,
) -> None:
    fake_result = OrchestrationResult(
        decision_id="dec_2026-04-30T14-30-00_2330",
        final=_decider_output(),
        written_kind="entry",
        llm_cost=LLMUsage(
            input_tokens=18420,
            output_tokens=1240,
            cost_usd=0.36930,
            model="claude-opus-4-7",
        ),
        force_reject_reason=None,
    )
    _patch_assemble_and_decide(monkeypatch, decide_result=fake_result)

    result = runner.invoke(
        app, ["decide", "--symbol", "2330", "--asof", "2026-04-30"]
    )
    assert result.exit_code == 0, result.stderr
    assert "decision: enter" in result.stdout
    assert "decision_id: dec_2026-04-30T14-30-00_2330" in result.stdout
    assert "cost_usd: 0.3693" in result.stdout


def test_decide_json_path_emits_valid_json(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    isolated_db: Path,
) -> None:
    fake_result = OrchestrationResult(
        decision_id="dec_2026-04-30T14-30-00_2330",
        final=_decider_output(),
        written_kind="entry",
        llm_cost=LLMUsage(
            input_tokens=18420,
            output_tokens=1240,
            cost_usd=0.36930,
            model="claude-opus-4-7",
        ),
        force_reject_reason=None,
    )
    _patch_assemble_and_decide(monkeypatch, decide_result=fake_result)

    result = runner.invoke(
        app,
        ["decide", "--symbol", "2330", "--asof", "2026-04-30", "--json"],
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload.keys()) >= {
        "decision_id",
        "decision",
        "force_reject_reason",
        "cost_usd",
    }
    assert payload["decision"] == "enter"
    assert payload["decision_id"] == "dec_2026-04-30T14-30-00_2330"
    assert payload["force_reject_reason"] is None


def test_decide_reject_path_exit_1(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    isolated_db: Path,
) -> None:
    fake_result = OrchestrationResult(
        decision_id="dec_2026-04-30T14-30-00_2330",
        final=_decider_output(decision="reject", confidence=0.4),
        written_kind="reject",
        llm_cost=LLMUsage(
            input_tokens=18420,
            output_tokens=1240,
            cost_usd=0.36930,
            model="claude-opus-4-7",
        ),
        force_reject_reason="stage_4_excluded",
    )
    _patch_assemble_and_decide(monkeypatch, decide_result=fake_result)

    result = runner.invoke(
        app, ["decide", "--symbol", "2330", "--asof", "2026-04-30"]
    )
    assert result.exit_code == 1, result.stderr
    assert "decision: reject" in result.stdout
    assert "force_reject_reason: stage_4_excluded" in result.stdout


def test_decide_assembler_failure_exit_2(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    isolated_db: Path,
) -> None:
    from ohmystock.swarm import AssemblerInputError

    _patch_assemble_and_decide(
        monkeypatch,
        assemble_raises=AssemblerInputError("symbol not in universe: 9999"),
    )

    result = runner.invoke(
        app, ["decide", "--symbol", "9999", "--asof", "2026-04-30"]
    )
    assert result.exit_code == 2
    assert "entry_input_assembly_failed:" in result.stderr
    assert "symbol not in universe" in result.stderr


def test_decide_parse_error_exit_3(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    isolated_db: Path,
) -> None:
    err = DeciderOutputParseError(
        "garbage", json.JSONDecodeError("expecting value", "garbage", 0)
    )
    _patch_assemble_and_decide(monkeypatch, decide_raises=err)

    result = runner.invoke(
        app, ["decide", "--symbol", "2330", "--asof", "2026-04-30"]
    )
    assert result.exit_code == 3
    assert "DeciderOutputParseError" in result.stderr


def test_decide_refuses_fake_in_non_test_env_exit_4(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    isolated_db: Path,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_DECIDER_MODEL", "fake://always-enter")
    monkeypatch.delenv("OHMYSTOCK_ALLOW_FAKE_DECIDER", raising=False)

    result = runner.invoke(
        app, ["decide", "--symbol", "2330", "--asof", "2026-04-30"]
    )
    assert result.exit_code == 4
    assert "refused to use fake decider" in result.stderr


def test_decide_db_path_creates_journal(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When the orchestrator runs end-to-end with a real conn, the SQLite
    file at OHMYSTOCK_DB_PATH should exist after the command. We patch
    decide_entry to a no-op that still uses the conn opened by the CLI.
    """
    db_path = tmp_path / "subdir" / "journal.db"
    monkeypatch.setenv("OHMYSTOCK_DB_PATH", str(db_path))

    fake_result = OrchestrationResult(
        decision_id="dec_2026-04-30T14-30-00_2330",
        final=_decider_output(),
        written_kind="entry",
        llm_cost=LLMUsage(
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            model="fake://",
        ),
        force_reject_reason=None,
    )
    _patch_assemble_and_decide(monkeypatch, decide_result=fake_result)

    result = runner.invoke(
        app, ["decide", "--symbol", "2330", "--asof", "2026-04-30"]
    )
    assert result.exit_code == 0, result.stderr
    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='journal_entries'"
        ).fetchall()
        assert rows == [("journal_entries",)]
    finally:
        conn.close()
