"""Tests for journal emitter: journal_written.

Asserts the cross-cutting helper fires once per row commit and that the
helper itself is best-effort (does not raise on bus failure).
"""

from __future__ import annotations

import json
import sqlite3
import sys

import pytest

import ohmystock.eventbus as eventbus_pkg
from ohmystock.eventbus import EventBus
from ohmystock.journal import emit_journal_written
from ohmystock.journal.schema import init_schema

bus_module = sys.modules["ohmystock.eventbus.bus"]


@pytest.fixture()
def fresh_bus(monkeypatch: pytest.MonkeyPatch) -> EventBus:
    fresh = EventBus()
    monkeypatch.setattr(eventbus_pkg, "bus", fresh)
    monkeypatch.setattr(bus_module, "bus", fresh)
    return fresh


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    init_schema(c)
    try:
        yield c
    finally:
        c.close()


def _drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


@pytest.mark.parametrize(
    "kind",
    ["entry", "fill", "exit", "reject", "expire", "auto_execute_audit"],
)
def test_emit_journal_written_emits_single_event_with_kind_and_symbol(
    fresh_bus: EventBus, kind: str
) -> None:
    q = fresh_bus.subscribe()
    emit_journal_written(kind, "2330")

    events = _drain(q)
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "journal_written"
    assert ev.agent == "librarian"
    assert ev.payload == {"journal_kind": kind, "symbol": "2330"}


def test_emit_with_no_subscribers_is_a_noop(fresh_bus: EventBus) -> None:
    # No subscribe() call — bus has zero subscribers.
    emit_journal_written("entry", "2330")  # must not raise


def test_emit_swallows_bus_failure(fresh_bus: EventBus) -> None:
    """If a subscriber's queue raises something unexpected, drop quietly."""

    class BoomQueue:
        def put_nowait(self, _ev):
            raise RuntimeError("kaboom")

    fresh_bus._subscribers.append(BoomQueue())  # type: ignore[arg-type]

    # Must not propagate.
    emit_journal_written("entry", "2330")


def test_inline_journal_row_then_emit_smoke(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    """Smoke test: a row commit followed by an emit produces one journal_written."""

    q = fresh_bus.subscribe()
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        (
            "dec_x",
            "2330",
            "2026-05-02T10:00:00+08:00",
            json.dumps({"decision_status": "pending_confirm"}),
        ),
    )
    conn.commit()
    emit_journal_written("entry", "2330")

    events = _drain(q)
    assert any(
        e.event_type == "journal_written" and e.payload["symbol"] == "2330"
        for e in events
    )
