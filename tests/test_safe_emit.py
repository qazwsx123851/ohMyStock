"""Tests for ohmystock.eventbus.safe_emit."""

from __future__ import annotations

import asyncio

import pytest

import sys

import ohmystock.eventbus as eventbus_pkg
from ohmystock.eventbus import Event, EventBus, safe_emit

bus_module = sys.modules["ohmystock.eventbus.bus"]


async def test_safe_emit_delivers_to_subscriber(monkeypatch: pytest.MonkeyPatch) -> None:
    fresh = EventBus()
    monkeypatch.setattr(eventbus_pkg, "bus", fresh)
    monkeypatch.setattr(bus_module, "bus", fresh)
    q = fresh.subscribe()

    await safe_emit(Event(event_type="decision_made", agent="decider"))

    received = q.get_nowait()
    assert received.event_type == "decision_made"
    assert received.agent == "decider"


async def test_safe_emit_swallows_runtimeerror(monkeypatch: pytest.MonkeyPatch) -> None:
    async def raise_boom(_event: Event) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(eventbus_pkg.bus, "emit", raise_boom)

    # Should not raise.
    await safe_emit(Event(event_type="decision_made", agent="decider"))


async def test_safe_emit_propagates_cancelled_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def raise_cancel(_event: Event) -> None:
        raise asyncio.CancelledError()

    monkeypatch.setattr(eventbus_pkg.bus, "emit", raise_cancel)

    with pytest.raises(asyncio.CancelledError):
        await safe_emit(Event(event_type="decision_made", agent="decider"))
