"""Tests for confirm-gate emitter: order_sent."""

from __future__ import annotations

import json
import sqlite3
import sys

import pytest

import ohmystock.eventbus as eventbus_pkg
from ohmystock.eventbus import EventBus
from ohmystock.journal.schema import init_schema
from ohmystock.paper import FakePaperBroker
from ohmystock.safety import ConfirmGateError, confirm

bus_module = sys.modules["ohmystock.eventbus.bus"]


_DEFAULT_CAPITAL = 1_000_000


class _FakeClock:
    def __init__(self, ts: str = "2026-05-02T10:15:00+08:00") -> None:
        self.ts = ts

    def now_iso(self) -> str:
        return self.ts


@pytest.fixture()
def conn():
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


def _seed_pending(
    conn: sqlite3.Connection,
    decision_id: str = "dec_2026-05-02T10-00-00_2330",
    symbol: str = "2330",
    final_sizing_pct: float = 25.0,
    current_price: float = 50.0,
    atr_14_pct: float = 2.85,
) -> str:
    payload = {
        "decision_status": "pending_confirm",
        "final_sizing_pct": final_sizing_pct,
        "current_price": current_price,
        "atr_14_pct": atr_14_pct,
    }
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        (decision_id, symbol, "2026-05-02T10:00:00+08:00", json.dumps(payload)),
    )
    conn.commit()
    return decision_id


def _drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def test_confirm_happy_path_emits_order_sent(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    decision_id = _seed_pending(conn)
    q = fresh_bus.subscribe()
    broker = FakePaperBroker(clock=_FakeClock())

    result = confirm(
        conn,
        decision_id=decision_id,
        broker=broker,
        default_capital_twd=_DEFAULT_CAPITAL,
        user="mark",
        clock=_FakeClock(),
    )

    events = _drain(q)
    types = [e.event_type for e in events]
    assert "order_sent" in types
    sent = events[types.index("order_sent")]
    assert sent.agent == "trader"
    assert sent.payload["symbol"] == "2330"
    assert sent.payload["price"] == result.fill.fill_price
    assert sent.payload["quantity"] == result.fill.filled_qty
    assert sent.payload["broker_order_id"] == result.fill.fill_ts
    assert "+08:00" in sent.payload["broker_order_id"]


def test_confirm_broker_failure_does_not_emit_order_sent(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    decision_id = _seed_pending(conn)
    q = fresh_bus.subscribe()
    broker = FakePaperBroker(clock=_FakeClock(), raise_on_submit=True)

    with pytest.raises(ConfirmGateError) as exc_info:
        confirm(
            conn,
            decision_id=decision_id,
            broker=broker,
            default_capital_twd=_DEFAULT_CAPITAL,
            user="mark",
            clock=_FakeClock(),
        )
    assert exc_info.value.code == "broker_failed"

    events = _drain(q)
    types = [e.event_type for e in events]
    assert "order_sent" not in types


def test_confirm_not_pending_does_not_emit_order_sent(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    decision_id = _seed_pending(conn)
    # First confirm succeeds.
    broker = FakePaperBroker(clock=_FakeClock())
    confirm(
        conn,
        decision_id=decision_id,
        broker=broker,
        default_capital_twd=_DEFAULT_CAPITAL,
        user="mark",
        clock=_FakeClock(),
    )
    # Now subscribe and try to re-confirm — should fail with not_pending.
    q = fresh_bus.subscribe()
    with pytest.raises(ConfirmGateError) as exc_info:
        confirm(
            conn,
            decision_id=decision_id,
            broker=broker,
            default_capital_twd=_DEFAULT_CAPITAL,
            user="mark",
            clock=_FakeClock(),
        )
    assert exc_info.value.code == "not_pending"

    events = _drain(q)
    types = [e.event_type for e in events]
    assert "order_sent" not in types
