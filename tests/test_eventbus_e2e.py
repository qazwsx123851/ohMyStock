"""End-to-end test: SSE consumer observes the confirm-gate event sequence.

Drives the `_admin_event_stream` generator while running `confirm()` in
the same task; asserts that order_sent arrives through the SSE serializer
in the admin JSON shape with the correct `+08:00` timestamp.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys

import pytest

import ohmystock.api.app as app_module
import ohmystock.eventbus as eventbus_pkg
from ohmystock.api.app import _admin_event_stream
from ohmystock.eventbus import EventBus
from ohmystock.journal.schema import init_schema
from ohmystock.paper import FakePaperBroker
from ohmystock.safety import confirm

bus_module = sys.modules["ohmystock.eventbus.bus"]


_DECISION_ID = "dec_2026-05-02T10-00-00_2330"
_SYMBOL = "2330"


class _FakeClock:
    def __init__(self, ts: str = "2026-05-02T10:15:00+08:00") -> None:
        self.ts = ts

    def now_iso(self) -> str:
        return self.ts


@pytest.fixture()
def fresh_bus(monkeypatch: pytest.MonkeyPatch) -> EventBus:
    fresh = EventBus()
    monkeypatch.setattr(eventbus_pkg, "bus", fresh)
    monkeypatch.setattr(bus_module, "bus", fresh)
    monkeypatch.setattr(app_module, "bus", fresh)
    return fresh


def _seed_pending(conn: sqlite3.Connection) -> str:
    payload = {
        "decision_status": "pending_confirm",
        "final_sizing_pct": 25.0,
        "current_price": 50.0,
        "atr_14_pct": 2.85,
    }
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        (_DECISION_ID, _SYMBOL, "2026-05-02T10:00:00+08:00", json.dumps(payload)),
    )
    conn.commit()
    return _DECISION_ID


async def _read_until(gen, predicate, *, timeout: float = 2.0):
    """Pull frames until ``predicate(msg)`` is true; skip keepalive comments."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return None
        try:
            msg = await asyncio.wait_for(gen.__anext__(), timeout=remaining)
        except asyncio.TimeoutError:
            return None
        if isinstance(msg, dict) and msg.get("event") and msg.get("data"):
            if predicate(msg):
                return msg
        # else keepalive comment — keep waiting.


async def test_confirm_path_streams_order_sent_in_admin_shape(
    fresh_bus: EventBus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module, "_KEEPALIVE_TIMEOUT_SECONDS", 0.2)

    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    decision_id = _seed_pending(conn)
    broker = FakePaperBroker(clock=_FakeClock())

    gen = _admin_event_stream()
    try:
        # Pump generator one tick so it subscribes BEFORE we trigger confirm().
        reader = asyncio.create_task(
            _read_until(gen, lambda m: m["event"] == "order_sent", timeout=2.0)
        )
        await asyncio.sleep(0)

        confirm(
            conn,
            decision_id=decision_id,
            broker=broker,
            default_capital_twd=1_000_000,
            user="mark",
            clock=_FakeClock(),
        )

        msg = await reader
    finally:
        await gen.aclose()
        conn.close()

    assert msg is not None
    assert msg["event"] == "order_sent"
    body = json.loads(msg["data"])
    assert body["event_type"] == "order_sent"
    assert body["agent"] == "trader"
    assert body["payload"]["symbol"] == _SYMBOL
    assert "+08:00" in body["timestamp"]
    assert isinstance(body["payload"]["price"], (int, float))
    assert isinstance(body["payload"]["quantity"], int)
    assert isinstance(body["payload"]["broker_order_id"], str)
