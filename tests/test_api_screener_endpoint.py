"""HTTP tests for ``POST /api/admin/screener/run``.

Spec scenarios covered:

* Success path: 200 + ``asof_date_used`` + ``candidates`` + ``elapsed_ms``.
* Invalid universe: 400 ``invalid_input``.
* SSE consumer receives ``screener_started`` + ``screener_completed``.
* No ``Authorization`` header still works.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

import ohmystock.api.app as app_module
import ohmystock.eventbus as eventbus_pkg
from ohmystock.api.app import _admin_event_stream, create_app
from ohmystock.api.routes._deps import get_db
from ohmystock.eventbus import EventBus
from ohmystock.screener.cache import init_universe_schema, insert_universe_rows


bus_module = sys.modules["ohmystock.eventbus.bus"]


@pytest.fixture()
def fresh_bus(monkeypatch: pytest.MonkeyPatch) -> EventBus:
    fresh = EventBus()
    monkeypatch.setattr(eventbus_pkg, "bus", fresh)
    monkeypatch.setattr(bus_module, "bus", fresh)
    monkeypatch.setattr(app_module, "bus", fresh)
    return fresh


@pytest.fixture()
def seeded_conn():
    # ``check_same_thread=False`` only because tests inject this conn into
    # FastAPI's threadpool via dependency_overrides; production opens its
    # own conn per request inside that thread so this flag is unneeded.
    c = sqlite3.connect(":memory:", check_same_thread=False)
    init_universe_schema(c)
    insert_universe_rows(
        c,
        [
            _row("2330", "TWSE"),
            _row("2454", "TWSE"),
            _row("6488", "OTC"),
        ],
        "finmind",
        "2026-04-30T17:30:00+08:00",
    )
    try:
        yield c
    finally:
        c.close()


def _row(symbol: str, market: str, asof: str = "2026-04-30") -> dict[str, Any]:
    return {
        "asof_date": asof,
        "symbol": symbol,
        "market": market,
        "name": "X",
        "industry": "",
        "is_warning": 0,
        "is_disposal": 0,
        "is_fully_paid": 0,
        "is_ky": 0,
    }


def _build_client(seeded_conn: sqlite3.Connection) -> AsyncClient:
    app = create_app()

    def _override_get_db():
        yield seeded_conn

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


async def test_screener_run_success_envelope(
    seeded_conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    async with _build_client(seeded_conn) as client:
        r = await client.post(
            "/api/admin/screener/run",
            json={"universe": "TWSE+OTC", "asof_date": "2026-04-30"},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["asof_date_used"] == "2026-04-30"
    assert isinstance(body["data"]["candidates"], list)
    assert len(body["data"]["candidates"]) == 3
    symbols = {c["symbol"] for c in body["data"]["candidates"]}
    assert symbols == {"2330", "2454", "6488"}
    assert isinstance(body["data"]["elapsed_ms"], int)
    assert body["data"]["elapsed_ms"] >= 0
    assert "error" not in body


# ---------------------------------------------------------------------------
# Invalid universe → 400 invalid_input
# ---------------------------------------------------------------------------


async def test_screener_run_invalid_universe_returns_400(
    seeded_conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    async with _build_client(seeded_conn) as client:
        r = await client.post(
            "/api/admin/screener/run",
            json={"universe": "nonsense"},
        )

    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"
    assert body["error"]["message"]


# ---------------------------------------------------------------------------
# Pydantic-level validation: missing universe → FastAPI 422 by default;
# the route still doesn't surface as 401/403 (no-auth invariant).
# ---------------------------------------------------------------------------


async def test_screener_run_missing_universe_not_auth_error(
    seeded_conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    async with _build_client(seeded_conn) as client:
        r = await client.post("/api/admin/screener/run", json={})

    assert r.status_code not in (401, 403)


# ---------------------------------------------------------------------------
# No Authorization header → still 200 (no-auth invariant)
# ---------------------------------------------------------------------------


async def test_screener_run_works_without_authorization_header(
    seeded_conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    async with _build_client(seeded_conn) as client:
        r = await client.post(
            "/api/admin/screener/run",
            json={"universe": "TWSE+OTC", "asof_date": "2026-04-30"},
            headers={},
        )

    assert r.status_code == 200
    assert "WWW-Authenticate" not in r.headers


# ---------------------------------------------------------------------------
# SSE consumer receives screener_started + screener_completed
# ---------------------------------------------------------------------------


async def test_screener_run_emits_started_then_completed_to_sse(
    seeded_conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    """Drive the admin SSE generator on the same loop as the HTTP call;
    assert both events arrive in order."""

    gen = _admin_event_stream()
    received: list[tuple[str, dict[str, Any]]] = []

    async def _drain() -> None:
        deadline = asyncio.get_event_loop().time() + 2.0
        while asyncio.get_event_loop().time() < deadline and len(received) < 2:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return
            try:
                msg = await asyncio.wait_for(gen.__anext__(), timeout=remaining)
            except asyncio.TimeoutError:
                return
            if isinstance(msg, dict) and msg.get("event") and msg.get("data"):
                received.append((msg["event"], json.loads(msg["data"])))

    drain_task = asyncio.create_task(_drain())
    await asyncio.sleep(0)

    try:
        async with _build_client(seeded_conn) as client:
            r = await client.post(
                "/api/admin/screener/run",
                json={"universe": "TWSE+OTC", "asof_date": "2026-04-30"},
            )
        assert r.status_code == 200

        await asyncio.wait_for(drain_task, timeout=2.0)
    finally:
        await gen.aclose()

    types = [event_type for event_type, _ in received]
    assert "screener_started" in types
    assert "screener_completed" in types
    assert types.index("screener_started") < types.index("screener_completed")

    completed_body = next(b for t, b in received if t == "screener_completed")
    assert isinstance(completed_body["payload"]["symbols"], list)
    assert sorted(completed_body["payload"]["symbols"]) == ["2330", "2454", "6488"]
