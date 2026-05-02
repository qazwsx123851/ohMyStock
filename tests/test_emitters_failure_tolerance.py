"""Tests for the cross-cutting "emit-is-best-effort" invariant.

Each producer's primary write/return path SHALL succeed even when the
EventBus raises on every emit. Also covers queue-full (drop) tolerance.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from asyncio import Queue
from typing import Any

import pytest

import ohmystock.eventbus as eventbus_pkg
from ohmystock.config import Settings
from ohmystock.eventbus import Event, EventBus
from ohmystock.journal.schema import init_schema
from ohmystock.paper import FakePaperBroker
from ohmystock.safety import confirm, try_auto_execute

bus_module = sys.modules["ohmystock.eventbus.bus"]


_DECISION_ID = "dec_2026-05-02T10-00-00_2330"
_SYMBOL = "2330"
_NOW = "2026-05-02T10:15:00+08:00"


class _FakeClock:
    def __init__(self, ts: str = _NOW) -> None:
        self.ts = ts

    def now_iso(self) -> str:
        return self.ts


@pytest.fixture()
def boom_bus(monkeypatch: pytest.MonkeyPatch) -> EventBus:
    """A bus whose emit path raises on every event delivery."""

    class BoomBus(EventBus):
        async def emit(self, event: Event) -> None:  # type: ignore[override]
            raise RuntimeError("boom")

    fresh = BoomBus()

    class BoomQueue:
        def put_nowait(self, _ev: Any) -> None:
            raise RuntimeError("kaboom")

    fresh._subscribers.append(BoomQueue())  # type: ignore[arg-type]

    monkeypatch.setattr(eventbus_pkg, "bus", fresh)
    monkeypatch.setattr(bus_module, "bus", fresh)
    return fresh


def _seed_pending(
    conn: sqlite3.Connection,
    *,
    final_sizing_pct: float = 25.0,
    current_price: float = 50.0,
    llm_confidence: float = 0.85,
    stage: int = 2,
) -> str:
    payload = {
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
        (_DECISION_ID, _SYMBOL, "2026-05-02T10:00:00+08:00", json.dumps(payload)),
    )
    conn.commit()
    return _DECISION_ID


def test_confirm_succeeds_even_when_bus_emit_raises(boom_bus: EventBus) -> None:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    decision_id = _seed_pending(conn)
    broker = FakePaperBroker(clock=_FakeClock())

    result = confirm(
        conn,
        decision_id=decision_id,
        broker=broker,
        default_capital_twd=1_000_000,
        user="mark",
        clock=_FakeClock(),
    )
    assert result.fill.symbol == _SYMBOL

    status = conn.execute(
        "SELECT json_extract(payload_json, '$.decision_status') FROM journal_entries "
        "WHERE decision_id=? AND kind='entry'",
        (decision_id,),
    ).fetchone()[0]
    assert status == "confirmed"


def test_auto_execute_low_confidence_succeeds_when_bus_emit_raises(
    boom_bus: EventBus,
) -> None:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    decision_id = _seed_pending(conn, llm_confidence=0.5)
    broker = FakePaperBroker(clock=_FakeClock())
    settings = Settings(
        ohmystock_broker="shioaji-sim",
        ohmystock_auto_execute=True,
        ohmystock_auto_execute_account_equity_twd=1_000_000,
    )  # type: ignore[arg-type]

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=broker,
        settings=settings,
        clock=_FakeClock(),
    )
    assert result.outcome == "low_confidence"

    audit_count = conn.execute(
        "SELECT count(*) FROM journal_entries WHERE kind='auto_execute_audit'"
    ).fetchone()[0]
    assert audit_count == 1


def test_queue_full_drop_does_not_break_auto_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-fill a maxsize=1 subscriber queue; auto_execute must still return
    its expected result and persist the audit row."""

    fresh = EventBus()
    monkeypatch.setattr(eventbus_pkg, "bus", fresh)
    monkeypatch.setattr(bus_module, "bus", fresh)

    capped: Queue[Event] = Queue(maxsize=1)
    capped.put_nowait(Event(event_type="filler", agent="test"))
    fresh._subscribers.append(capped)

    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    decision_id = _seed_pending(conn, llm_confidence=0.5)
    broker = FakePaperBroker(clock=_FakeClock())
    settings = Settings(
        ohmystock_broker="shioaji-sim",
        ohmystock_auto_execute=True,
        ohmystock_auto_execute_account_equity_twd=1_000_000,
    )  # type: ignore[arg-type]

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=broker,
        settings=settings,
        clock=_FakeClock(),
    )
    assert result.outcome == "low_confidence"

    audit_count = conn.execute(
        "SELECT count(*) FROM journal_entries WHERE kind='auto_execute_audit'"
    ).fetchone()[0]
    assert audit_count == 1
