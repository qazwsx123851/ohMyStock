"""Async API tests — /healthz, SSE shape, sqlite PRAGMA, EventBus round-trip.

Uses httpx ASGITransport for /healthz (a finite response). The SSE endpoint
cannot be exercised through ASGITransport or Starlette TestClient because
both buffer the full response before returning headers, which deadlocks
against an infinite while-True generator. We instead split the SSE check
into route registration + generator shape, and rely on the manual curl
smoke test (tasks §10.3) to verify the live streaming behavior.

asyncio_mode = "auto" (pyproject.toml) auto-runs async tests/fixtures.

Spec: openspec/changes/fastapi-bootstrap/specs/backend-api-and-eventbus/spec.md
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from ohmystock.api.app import _admin_event_stream, create_app
from ohmystock.api.db import _get_settings, get_connection
from ohmystock.eventbus.bus import EventBus
from ohmystock.eventbus.events import Event


@pytest_asyncio.fixture
async def app_client() -> AsyncClient:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_healthz_returns_ok(app_client: AsyncClient) -> None:
    r = await app_client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["version"], str) and len(body["version"]) > 0


def test_admin_events_route_registered() -> None:
    app = create_app()
    paths = {r.path for r in app.routes}
    assert "/api/admin/events" in paths


async def test_admin_event_stream_broadcasts_emitted_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    import ohmystock.api.app as app_module
    import ohmystock.eventbus as eventbus_pkg

    bus_module = sys.modules["ohmystock.eventbus.bus"]

    fresh = EventBus()
    monkeypatch.setattr(eventbus_pkg, "bus", fresh)
    monkeypatch.setattr(bus_module, "bus", fresh)
    monkeypatch.setattr(app_module, "bus", fresh)

    gen = _admin_event_stream()
    try:
        # Yield once so the generator subscribes before we emit.
        msg_task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0)
        await fresh.emit(
            Event(event_type="decision_made", agent="decider", payload={"symbol": "2330"})
        )
        msg = await asyncio.wait_for(msg_task, timeout=1.0)
    finally:
        await gen.aclose()

    assert msg["event"] == "decision_made"
    payload = json.loads(msg["data"])
    assert payload["event_type"] == "decision_made"
    assert payload["agent"] == "decider"
    assert payload["payload"] == {"symbol": "2330"}
    assert "+08:00" in payload["timestamp"]


def test_get_connection_pragmas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("OHMYSTOCK_DB_PATH", str(db_path))
    _get_settings.cache_clear()
    try:
        conn = get_connection()
        try:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            assert db_path.exists()
        finally:
            conn.close()
    finally:
        _get_settings.cache_clear()


async def test_eventbus_round_trip() -> None:
    local_bus = EventBus()
    q = local_bus.subscribe()
    await local_bus.emit(Event(event_type="x", agent="t"))
    ev = await asyncio.wait_for(q.get(), timeout=1.0)
    assert ev.event_type == "x"
    local_bus.unsubscribe(q)
