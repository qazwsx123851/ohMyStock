"""Tests for decider emitters: decider_thinking + decision_made."""

from __future__ import annotations

import sqlite3
import sys
from typing import Iterator

import pytest

import ohmystock.eventbus as eventbus_pkg
from ohmystock.decider.models import DeciderOutput
from ohmystock.decider.node import (
    DeciderOutputParseError,
    FakePMConclusionNode,
    LLMUsage,
)
from ohmystock.decider.orchestrator import decide_entry
from ohmystock.eventbus import EventBus
from ohmystock.journal.schema import init_schema
from ohmystock.swarm.models import (
    CandidateSnapshot,
    EntryDecisionInput,
    MarketContext,
    RulesDigest,
)

bus_module = sys.modules["ohmystock.eventbus.bus"]


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


@pytest.fixture()
def fresh_bus(monkeypatch: pytest.MonkeyPatch) -> EventBus:
    fresh = EventBus()
    monkeypatch.setattr(eventbus_pkg, "bus", fresh)
    monkeypatch.setattr(bus_module, "bus", fresh)
    return fresh


def _make_candidate() -> CandidateSnapshot:
    return CandidateSnapshot(
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
    )


def _make_entry_input() -> EntryDecisionInput:
    return EntryDecisionInput(
        decision_id="dec_2026-04-30T14-30-00_2330",
        trigger_at="2026-04-30T14:30:00+08:00",
        candidate=_make_candidate(),
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
            {"name": "vcp_pivot_breakout_with_volume", "pass": True, "evidence": "..."},
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


def _drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def _decide(conn: sqlite3.Connection, fake: FakePMConclusionNode):
    return decide_entry(
        _make_entry_input(),
        conn=conn,
        decider=fake,
        clock=_FixedClock(),
    )


def test_entry_path_emits_thinking_then_decision_made(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    q = fresh_bus.subscribe()
    fake = FakePMConclusionNode(output=_make_output(), usage=_make_usage())
    _decide(conn, fake)

    events = _drain(q)
    types = [e.event_type for e in events]
    assert "decider_thinking" in types
    assert "decision_made" in types
    assert "awaiting_confirm" in types
    thinking = events[types.index("decider_thinking")]
    decision = events[types.index("decision_made")]
    awaiting = events[types.index("awaiting_confirm")]

    assert thinking.agent == "decider"
    assert thinking.payload == {"symbol": "2330", "confidence_so_far": 0.0}

    assert decision.agent == "decider"
    assert decision.payload["symbol"] == "2330"
    assert decision.payload["action"] == "entry"
    assert decision.payload["confidence"] == pytest.approx(0.83)
    assert isinstance(decision.payload["reasoning"], str)
    assert decision.payload["reasoning"]

    # awaiting_confirm fires only on the entry path; carries timeout_at + price.
    assert awaiting.agent == "trader"
    assert awaiting.payload["symbol"] == "2330"
    assert "+08:00" in awaiting.payload["timeout_at"]
    assert awaiting.payload["expected_price"] == 845.0


def test_skip_path_emits_decision_made_with_action_skip(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    q = fresh_bus.subscribe()
    output = _make_output(decision="reject", confidence=0.4)
    fake = FakePMConclusionNode(output=output, usage=_make_usage())
    _decide(conn, fake)

    events = _drain(q)
    types = [e.event_type for e in events]
    assert "decision_made" in types
    decision = events[types.index("decision_made")]
    assert decision.payload["action"] == "skip"
    assert decision.payload["symbol"] == "2330"
    # Skip path does NOT progress to confirm gate.
    assert "awaiting_confirm" not in types


def test_parse_error_path_does_not_emit_decision_made(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    q = fresh_bus.subscribe()
    fake = FakePMConclusionNode(
        raise_parse_error=DeciderOutputParseError(
            "bad raw text", cause=ValueError("nope")
        )
    )
    with pytest.raises(DeciderOutputParseError):
        _decide(conn, fake)

    events = _drain(q)
    types = [e.event_type for e in events]
    # decider_thinking fires before the call; decision_made does NOT on raise.
    assert "decider_thinking" in types
    assert "decision_made" not in types
