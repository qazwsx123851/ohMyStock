"""Tests for /api/admin/events SSE subscriber behavior.

Covers: real-event broadcast in admin JSON shape, idle keepalive, unsubscribe
on disconnect, no-auth still works.
"""

from __future__ import annotations

import asyncio
import json
import sys

import pytest

import ohmystock.api.app as app_module
import ohmystock.eventbus as eventbus_pkg
from ohmystock.api.app import _admin_event_stream, create_app
from ohmystock.eventbus import Event, EventBus

bus_module = sys.modules["ohmystock.eventbus.bus"]


@pytest.fixture()
def fresh_bus(monkeypatch: pytest.MonkeyPatch) -> EventBus:
    fresh = EventBus()
    monkeypatch.setattr(eventbus_pkg, "bus", fresh)
    monkeypatch.setattr(bus_module, "bus", fresh)
    monkeypatch.setattr(app_module, "bus", fresh)
    return fresh


async def test_real_event_broadcast_in_admin_json_shape(fresh_bus: EventBus) -> None:
    gen = _admin_event_stream()
    try:
        msg_task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0)
        await fresh_bus.emit(
            Event(
                event_type="decision_made",
                agent="decider",
                payload={"symbol": "2330", "confidence": 0.72},
            )
        )
        msg = await asyncio.wait_for(msg_task, timeout=1.0)
    finally:
        await gen.aclose()

    assert msg["event"] == "decision_made"
    body = json.loads(msg["data"])
    assert set(body.keys()) == {"event_id", "timestamp", "event_type", "agent", "payload"}
    assert body["payload"]["symbol"] == "2330"
    assert body["payload"]["confidence"] == 0.72


async def test_unsubscribe_called_on_disconnect(
    fresh_bus: EventBus, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy_called: list[object] = []
    real_unsubscribe = fresh_bus.unsubscribe

    def spy(q):
        spy_called.append(q)
        real_unsubscribe(q)

    monkeypatch.setattr(fresh_bus, "unsubscribe", spy)

    gen = _admin_event_stream()
    try:
        msg_task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0)
        await fresh_bus.emit(Event(event_type="decision_made", agent="decider"))
        await asyncio.wait_for(msg_task, timeout=1.0)
    finally:
        await gen.aclose()

    assert len(spy_called) == 1


async def test_route_registered_no_auth() -> None:
    app = create_app()
    paths = {r.path for r in app.routes}
    assert "/api/admin/events" in paths
    assert "/healthz" in paths


async def test_idle_yields_keepalive_under_short_timeout(
    fresh_bus: EventBus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With timeout reduced to fractions of a second, idle stream yields a
    ServerSentEvent comment frame (keepalive) instead of dropping."""

    monkeypatch.setattr(app_module, "_KEEPALIVE_TIMEOUT_SECONDS", 0.05)

    gen = _admin_event_stream()
    try:
        msg = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
    finally:
        await gen.aclose()

    if isinstance(msg, dict):
        assert "event" not in msg or msg.get("event") in (None, "")
    else:
        assert getattr(msg, "comment", None) == "keepalive"
