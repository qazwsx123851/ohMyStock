"""Tests for auto-execute emitter: risk_off_triggered.

Asserts breaker outcomes emit risk_off_triggered with correct severity,
and that pass / sizing_clamped_then_pass do NOT emit.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass
from typing import Any

import pytest

import ohmystock.eventbus as eventbus_pkg
from ohmystock.config import Settings
from ohmystock.eventbus import EventBus
from ohmystock.journal.schema import init_schema
from ohmystock.paper import FakePaperBroker
from ohmystock.safety import try_auto_execute

bus_module = sys.modules["ohmystock.eventbus.bus"]


@dataclass(frozen=True)
class _FakeClock:
    ts: str

    def now_iso(self) -> str:
        return self.ts


_DEFAULT_DECISION_ID = "dec_2026-05-02T10-00-00_2330"
_DEFAULT_SYMBOL = "2330"
_DEFAULT_CREATED_AT = "2026-05-02T10:00:00+08:00"
_DEFAULT_NOW = "2026-05-02T10:15:00+08:00"


@pytest.fixture()
def fresh_bus(monkeypatch: pytest.MonkeyPatch) -> EventBus:
    fresh = EventBus()
    monkeypatch.setattr(eventbus_pkg, "bus", fresh)
    monkeypatch.setattr(bus_module, "bus", fresh)
    return fresh


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    return c


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "ohmystock_broker": "shioaji-sim",
        "ohmystock_auto_execute": True,
        "ohmystock_auto_execute_account_equity_twd": 1_000_000,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _seed_pending(
    conn: sqlite3.Connection,
    *,
    llm_confidence: float = 0.85,
    final_sizing_pct: float = 20.0,
    current_price: float = 100.0,
    stage: int = 2,
) -> str:
    payload: dict[str, Any] = {
        "decision_status": "pending_confirm",
        "llm_confidence": llm_confidence,
        "final_sizing_pct": final_sizing_pct,
        "current_price": current_price,
        "atr_14_pct": 2.85,
        "stage": stage,
        "auto_executed": False,
    }
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        (_DEFAULT_DECISION_ID, _DEFAULT_SYMBOL, _DEFAULT_CREATED_AT, json.dumps(payload)),
    )
    conn.commit()
    return _DEFAULT_DECISION_ID


def _drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def _types(q) -> list[str]:
    return [e.event_type for e in _drain(q)]


def test_low_confidence_breaker_emits_warn(fresh_bus: EventBus) -> None:
    conn = _conn()
    decision_id = _seed_pending(conn, llm_confidence=0.5)
    q = fresh_bus.subscribe()
    broker = FakePaperBroker(clock=_FakeClock(ts=_DEFAULT_NOW))

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=broker,
        settings=_settings(),
        clock=_FakeClock(ts=_DEFAULT_NOW),
    )
    assert result.outcome == "low_confidence"

    events = _drain(q)
    types = [e.event_type for e in events]
    assert "risk_off_triggered" in types
    risk = events[types.index("risk_off_triggered")]
    assert risk.agent == "guard"
    assert risk.payload == {"reason_category": "low_confidence", "severity": "warn"}


def test_notional_limit_breaker_emits_halt(fresh_bus: EventBus) -> None:
    conn = _conn()
    decision_id = _seed_pending(conn, final_sizing_pct=80.0, current_price=100.0)
    q = fresh_bus.subscribe()
    broker = FakePaperBroker(clock=_FakeClock(ts=_DEFAULT_NOW))

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=broker,
        settings=_settings(),
        clock=_FakeClock(ts=_DEFAULT_NOW),
    )
    assert result.outcome == "notional_limit"

    events = _drain(q)
    types = [e.event_type for e in events]
    assert "risk_off_triggered" in types
    risk = events[types.index("risk_off_triggered")]
    assert risk.payload == {"reason_category": "notional_limit", "severity": "halt"}


def test_flag_off_breaker_emits_warn(fresh_bus: EventBus) -> None:
    conn = _conn()
    decision_id = _seed_pending(conn)
    q = fresh_bus.subscribe()
    broker = FakePaperBroker(clock=_FakeClock(ts=_DEFAULT_NOW))

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=broker,
        settings=_settings(ohmystock_auto_execute=False),
        clock=_FakeClock(ts=_DEFAULT_NOW),
    )
    assert result.outcome == "flag_off"

    events = _drain(q)
    types = [e.event_type for e in events]
    assert "risk_off_triggered" in types
    risk = events[types.index("risk_off_triggered")]
    assert risk.payload == {"reason_category": "flag_off", "severity": "warn"}


def test_pass_path_does_not_emit_risk_off(fresh_bus: EventBus) -> None:
    conn = _conn()
    decision_id = _seed_pending(conn)
    q = fresh_bus.subscribe()
    broker = FakePaperBroker(clock=_FakeClock(ts=_DEFAULT_NOW))

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=broker,
        settings=_settings(),
        clock=_FakeClock(ts=_DEFAULT_NOW),
    )
    assert result.outcome == "pass"

    types = _types(q)
    assert "risk_off_triggered" not in types
    # journal_written for the audit row should still fire.
    assert "journal_written" in types


def test_sizing_clamped_then_pass_does_not_emit_risk_off(fresh_bus: EventBus) -> None:
    conn = _conn()
    # stage=2 (sys=25), final=17 → deviation=32% > 30% triggers clamp logic.
    # notional with current_price=100 → qty=1000, notional=100k (≤ 250k cap).
    decision_id = _seed_pending(conn, final_sizing_pct=17.0, current_price=100.0)
    q = fresh_bus.subscribe()
    broker = FakePaperBroker(clock=_FakeClock(ts=_DEFAULT_NOW))

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=broker,
        settings=_settings(),
        clock=_FakeClock(ts=_DEFAULT_NOW),
    )
    assert result.outcome == "sizing_clamped_then_pass"

    types = _types(q)
    assert "risk_off_triggered" not in types
