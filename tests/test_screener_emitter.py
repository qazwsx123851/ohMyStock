"""Tests for screener emitters: screener_started + screener_completed."""

from __future__ import annotations

import sqlite3
import sys
from typing import Any

import pytest

import ohmystock.eventbus as eventbus_pkg
from ohmystock.data.cache import init_market_data_schema
from ohmystock.eventbus import EventBus
from ohmystock.screener.cache import init_universe_schema, insert_universe_rows
from ohmystock.screener.universe import screen_universe

bus_module = sys.modules["ohmystock.eventbus.bus"]


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    init_universe_schema(c)
    init_market_data_schema(c)
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


def _row(symbol: str, market: str, asof: str = "2026-04-30", **kw) -> dict[str, Any]:
    return {
        "asof_date": asof,
        "symbol": symbol,
        "market": market,
        "name": kw.get("name", "X"),
        "industry": kw.get("industry", ""),
        "is_warning": kw.get("is_warning", 0),
        "is_disposal": kw.get("is_disposal", 0),
        "is_fully_paid": kw.get("is_fully_paid", 0),
        "is_ky": kw.get("is_ky", 0),
    }


def _seed(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    insert_universe_rows(conn, rows, "finmind", "2026-04-30T17:30:00+08:00")


def _drain(q) -> list:
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def test_screener_emits_started_then_completed_on_happy_path(
    conn, fresh_bus: EventBus
) -> None:
    _seed(
        conn,
        [
            _row("2330", "TWSE"),
            _row("2454", "TWSE"),
            _row("6488", "OTC"),
        ],
    )
    q = fresh_bus.subscribe()

    result = screen_universe(
        universe="TWSE+OTC",
        asof_date="2026-04-30",
        _conn=conn,
        _client=None,
    )
    assert result["ok"] is True

    events = _drain(q)
    types = [e.event_type for e in events]
    assert "screener_started" in types
    assert "screener_completed" in types
    started_idx = types.index("screener_started")
    completed_idx = types.index("screener_completed")
    assert started_idx < completed_idx

    started = events[started_idx]
    assert started.agent == "scanner"
    assert started.payload == {"universe_size": 3}

    completed = events[completed_idx]
    assert completed.agent == "scanner"
    assert completed.payload["candidate_count"] == 3
    assert sorted(completed.payload["symbols"]) == ["2330", "2454", "6488"]


def test_screener_no_completed_on_invalid_input_path(
    conn, fresh_bus: EventBus
) -> None:
    q = fresh_bus.subscribe()

    # Invalid input → returns error envelope before universe load → no events.
    result = screen_universe(
        universe="bogus",
        _conn=conn,
        _client=None,
    )
    assert result["ok"] is False

    events = _drain(q)
    assert all(e.event_type != "screener_completed" for e in events)


def test_screener_completes_with_no_subscribers_attached(conn, fresh_bus: EventBus) -> None:
    _seed(conn, [_row("2330", "TWSE")])

    # No subscribe() call — bus has zero subscribers.
    result = screen_universe(
        universe="TWSE",
        asof_date="2026-04-30",
        _conn=conn,
        _client=None,
    )
    assert result["ok"] is True
    assert result["data"]["candidates"][0]["symbol"] == "2330"
