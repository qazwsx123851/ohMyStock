"""Tests for ``ohmystock.decider.orchestrator.decide_entry``."""

from __future__ import annotations

import json
import sqlite3
from typing import Iterator

import pytest

from ohmystock.decider.models import DeciderOutput
from ohmystock.decider.node import (
    DeciderOutputParseError,
    FakePMConclusionNode,
    LLMUsage,
)
from ohmystock.decider.orchestrator import (
    OrchestrationResult,
    decide_entry,
    default_decision_id,
)
from ohmystock.journal.schema import init_schema
from ohmystock.swarm.models import (
    CandidateSnapshot,
    EntryDecisionInput,
    MarketContext,
    RulesDigest,
)


_FIXED_NOW = "2026-04-30T14:34:22+08:00"


class _FixedClock:
    def now_iso(self) -> str:
        return _FIXED_NOW


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    try:
        yield c
    finally:
        c.close()


def _make_candidate(**overrides: object) -> CandidateSnapshot:
    base: dict[str, object] = {
        "symbol": "2330",
        "name": "台積電",
        "final_score": 78,
        "tech_score": 32,
        "chip_score": 18,
        "fundamental_score": 22,
        "sentiment_score": 6,
        "ema20_distance_pct": 3.2,
        "atr_14_pct": 2.4,
        "current_price": 845.0,
        "stage": 2,
        "rs_percentile": 87,
        "trend_template_passed": 8,
        "vcp_quality": "breakout",
        "pivot_price": 832.0,
        "distance_from_52w_high_pct": 4.1,
        "distance_from_52w_low_pct": 41.6,
    }
    base.update(overrides)
    return CandidateSnapshot(**base)


def _make_entry_input(candidate: CandidateSnapshot | None = None) -> EntryDecisionInput:
    return EntryDecisionInput(
        decision_id="dec_2026-04-30T14-30-00_2330",
        trigger_at="2026-04-30T14:30:00+08:00",
        candidate=candidate or _make_candidate(),
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


def _make_output(**overrides: object) -> DeciderOutput:
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
        "reasoning": "VCP breakout 杯柄突破量能放大；" + ("論點" * 100),
        "cited_skills": ["technical/breakout"],
        "invalidation_conditions": ["RS Percentile 跌破 50"],
        "risk_flags": [],
        "tool_calls_summary": [],
    }
    payload.update(overrides)
    return DeciderOutput.model_validate(payload)


def _make_usage() -> LLMUsage:
    return LLMUsage(
        input_tokens=18420,
        output_tokens=1240,
        cost_usd=0.36930,
        model="claude-opus-4-7",
    )


def _decide(
    conn: sqlite3.Connection,
    fake: FakePMConclusionNode,
    entry_input: EntryDecisionInput | None = None,
) -> OrchestrationResult:
    return decide_entry(
        entry_input or _make_entry_input(),
        conn=conn,
        decider=fake,
        clock=_FixedClock(),
    )


def test_default_decision_id_uses_input_decision_id() -> None:
    ei = _make_entry_input()
    assert default_decision_id(ei) == "dec_2026-04-30T14-30-00_2330"


def test_enter_path_writes_one_entry_and_one_cost(conn: sqlite3.Connection) -> None:
    fake = FakePMConclusionNode(output=_make_output(), usage=_make_usage())
    result = _decide(conn, fake)

    assert result.written_kind == "entry"
    assert result.force_reject_reason is None
    assert result.final.decision == "enter"

    n_entries = conn.execute(
        "SELECT count(*) FROM journal_entries WHERE kind='entry'"
    ).fetchone()[0]
    assert n_entries == 1

    n_costs = conn.execute("SELECT count(*) FROM llm_costs").fetchone()[0]
    assert n_costs == 1

    cost_decision_id = conn.execute(
        "SELECT decision_id FROM llm_costs"
    ).fetchone()[0]
    assert cost_decision_id == result.decision_id


def test_enter_payload_contains_required_fields(conn: sqlite3.Connection) -> None:
    fake = FakePMConclusionNode(output=_make_output(), usage=_make_usage())
    _decide(conn, fake)

    raw_json = conn.execute(
        "SELECT payload_json FROM journal_entries WHERE kind='entry'"
    ).fetchone()[0]
    payload = json.loads(raw_json)

    required_keys = {
        "llm_model", "llm_confidence", "llm_reasoning", "cited_skills",
        "must_have_check", "bonus_score", "proposed_sizing_pct",
        "expected_holding_days", "stage", "rs_percentile",
        "trend_template_passed", "vcp_quality", "pivot_price",
        "llm_input_tokens", "llm_output_tokens", "llm_cost_usd",
        "entry_thesis", "thesis_invalidation",
    }
    assert required_keys.issubset(payload.keys())
    assert payload["decision_status"] == "pending_confirm"
    assert payload["llm_input_tokens"] == 18420
    assert payload["llm_cost_usd"] == 0.36930


def test_pending_confirm_nullable_fields_are_none(conn: sqlite3.Connection) -> None:
    fake = FakePMConclusionNode(output=_make_output(), usage=_make_usage())
    _decide(conn, fake)

    row = conn.execute(
        "SELECT json_extract(payload_json, '$.decision_status'),"
        " json_extract(payload_json, '$.stop_loss_price'),"
        " json_extract(payload_json, '$.atr_at_entry'),"
        " json_extract(payload_json, '$.risk_regime_at_entry'),"
        " json_extract(payload_json, '$.auto_executed'),"
        " json_extract(payload_json, '$.human_confirmed_by')"
        " FROM journal_entries WHERE kind='entry'"
    ).fetchone()
    assert row == ("pending_confirm", None, None, None, 0, None)


def test_fts5_match_on_entry_thesis(conn: sqlite3.Connection) -> None:
    # NB: SQLite's unicode61 tokenizer (FTS5 default) treats a contiguous
    # CJK run as a single token, so the searchable phrase must be delimited
    # from surrounding CJK chars by a space or punctuation. The first
    # ``MATCH`` searches for an ASCII token; the second confirms that an
    # isolated Chinese token also indexes correctly.
    output = _make_output(
        reasoning=(
            "VCP breakout 杯柄突破 量能放大；"
            + ("論點" * 100)
        )
    )
    fake = FakePMConclusionNode(output=output, usage=_make_usage())
    _decide(conn, fake)

    ascii_rows = conn.execute(
        "SELECT rowid FROM journal_entries_fts "
        "WHERE journal_entries_fts MATCH 'breakout'"
    ).fetchall()
    assert len(ascii_rows) >= 1

    cjk_rows = conn.execute(
        "SELECT rowid FROM journal_entries_fts "
        "WHERE journal_entries_fts MATCH '杯柄突破'"
    ).fetchall()
    assert len(cjk_rows) >= 1


def test_llm_voluntary_reject_writes_reject_layer_llm(
    conn: sqlite3.Connection,
) -> None:
    output = _make_output(decision="reject", confidence=0.4)
    fake = FakePMConclusionNode(output=output, usage=_make_usage())
    result = _decide(conn, fake)

    assert result.written_kind == "reject"
    assert result.force_reject_reason == "confidence_below_0_6"

    row = conn.execute(
        "SELECT json_extract(payload_json, '$.reject_layer'),"
        " json_extract(payload_json, '$.reject_reason'),"
        " json_extract(payload_json, '$.decision_status')"
        " FROM journal_entries WHERE kind='reject'"
    ).fetchone()
    assert row == ("llm", "confidence_below_0_6", "rejected")


def test_force_reject_stage_4_writes_applied_overrides(
    conn: sqlite3.Connection,
) -> None:
    output = _make_output(stage=4)
    candidate = _make_candidate(stage=4)
    fake = FakePMConclusionNode(output=output, usage=_make_usage())

    result = _decide(conn, fake, _make_entry_input(candidate=candidate))

    assert result.written_kind == "reject"
    assert result.force_reject_reason == "stage_4_excluded"

    row = conn.execute(
        "SELECT json_extract(payload_json, '$.reject_reason'),"
        " json_extract(payload_json, '$.applied_overrides')"
        " FROM journal_entries WHERE kind='reject'"
    ).fetchone()
    assert row[0] == "stage_4_excluded"
    overrides = json.loads(row[1])
    assert "force_rejected:stage_4_excluded" in overrides


def test_parse_error_writes_reject_then_reraises(conn: sqlite3.Connection) -> None:
    err = DeciderOutputParseError(
        "i think we should buy",
        json.JSONDecodeError("expecting value", "i think...", 0),
    )
    fake = FakePMConclusionNode(raise_parse_error=err)

    with pytest.raises(DeciderOutputParseError):
        _decide(conn, fake)

    n_rejects = conn.execute(
        "SELECT count(*) FROM journal_entries WHERE kind='reject'"
    ).fetchone()[0]
    assert n_rejects == 1

    row = conn.execute(
        "SELECT json_extract(payload_json, '$.reject_reason'),"
        " json_extract(payload_json, '$.reject_layer')"
        " FROM journal_entries WHERE kind='reject'"
    ).fetchone()
    assert row[0].startswith("json_parse_error:")
    assert row[1] == "llm"

    cost_row = conn.execute(
        "SELECT input_tokens, output_tokens, cost_usd FROM llm_costs"
    ).fetchone()
    assert cost_row == (0, 0, 0.0)


def test_parse_error_reject_payload_zero_token_fields(
    conn: sqlite3.Connection,
) -> None:
    err = DeciderOutputParseError(
        "garbage", json.JSONDecodeError("e", "g", 0)
    )
    fake = FakePMConclusionNode(raise_parse_error=err)

    with pytest.raises(DeciderOutputParseError):
        _decide(conn, fake)

    row = conn.execute(
        "SELECT json_extract(payload_json, '$.llm_input_tokens'),"
        " json_extract(payload_json, '$.llm_cost_usd')"
        " FROM journal_entries WHERE kind='reject'"
    ).fetchone()
    assert row in {(None, None), (0, 0.0), (0, 0)}


def test_write_failure_rolls_back_both_tables(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakePMConclusionNode(output=_make_output(), usage=_make_usage())

    from ohmystock.decider import orchestrator as orch_mod

    def boom(*args, **kwargs):
        raise sqlite3.IntegrityError("simulated")

    monkeypatch.setattr(orch_mod, "write_entry_pending_confirm", boom)

    with pytest.raises(sqlite3.IntegrityError):
        _decide(conn, fake)

    n_entries = conn.execute(
        "SELECT count(*) FROM journal_entries"
    ).fetchone()[0]
    n_costs = conn.execute("SELECT count(*) FROM llm_costs").fetchone()[0]
    assert n_entries == 0
    assert n_costs == 0


def test_stage_3_sizing_capped_in_final_payload(conn: sqlite3.Connection) -> None:
    output = _make_output(stage=3, proposed_sizing_pct=18.0)
    candidate = _make_candidate(stage=3)
    fake = FakePMConclusionNode(output=output, usage=_make_usage())

    result = _decide(conn, fake, _make_entry_input(candidate=candidate))

    assert result.force_reject_reason is None
    assert result.final.proposed_sizing_pct == 10.0

    row = conn.execute(
        "SELECT json_extract(payload_json, '$.proposed_sizing_pct'),"
        " json_extract(payload_json, '$.final_sizing_pct')"
        " FROM journal_entries WHERE kind='entry'"
    ).fetchone()
    assert row == (18.0, 10.0)


def test_created_at_uses_clock(conn: sqlite3.Connection) -> None:
    fake = FakePMConclusionNode(output=_make_output(), usage=_make_usage())
    _decide(conn, fake)

    j_at = conn.execute(
        "SELECT created_at FROM journal_entries"
    ).fetchone()[0]
    c_at = conn.execute("SELECT created_at FROM llm_costs").fetchone()[0]
    assert j_at == _FIXED_NOW
    assert c_at == _FIXED_NOW
