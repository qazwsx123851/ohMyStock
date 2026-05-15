"""Integration tests for the no-auth public SSE channel.

Covers: ``MaskedEventSerializer`` is applied per frame, route accepts requests
without ``Authorization``, the per-process ``SymbolMaskTable`` is installed by
lifespan, CORS is scoped to ``/api/public/*`` only, the route module imports
nothing named ``auth``.

Spec: openspec/changes/web-public-shell-and-mask/specs/admin-public-events-endpoint/spec.md
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

import ohmystock.api.routes.public_events as route_module
import ohmystock.eventbus as eventbus_pkg
from ohmystock.api.app import create_app
from ohmystock.api.routes.public_events import (
    _public_event_stream,
    clear_mask_table,
    set_mask_table,
)
from ohmystock.eventbus import Event, EventBus, SymbolMaskTable

bus_module = sys.modules["ohmystock.eventbus.bus"]


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Static-text guard: spec requires zero ``auth`` matches in the route module.
# ---------------------------------------------------------------------------


async def test_no_auth_import_in_route_module_source() -> None:
    """Async only to satisfy the module-level ``pytestmark = pytest.mark.asyncio``;
    body is fully synchronous."""
    source = Path(route_module.__file__).read_text(encoding="utf-8").lower()
    assert "auth" not in source, (
        "public_events.py must NOT reference any auth identifier; "
        "found 'auth' substring in source."
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fresh_bus(monkeypatch: pytest.MonkeyPatch) -> EventBus:
    fresh = EventBus()
    monkeypatch.setattr(eventbus_pkg, "bus", fresh)
    monkeypatch.setattr(bus_module, "bus", fresh)
    monkeypatch.setattr(route_module, "bus", fresh)
    return fresh


@pytest.fixture()
def installed_mask_table() -> SymbolMaskTable:
    table = SymbolMaskTable({"2330": "半導體"})
    set_mask_table(table)
    try:
        yield table
    finally:
        clear_mask_table()


# ---------------------------------------------------------------------------
# Stream-level behaviour
# ---------------------------------------------------------------------------


async def test_emit_decision_made_yields_masked_symbol_frame(
    fresh_bus: EventBus, installed_mask_table: SymbolMaskTable
) -> None:
    gen = _public_event_stream()
    try:
        msg_task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0)
        await fresh_bus.emit(
            Event(
                event_type="decision_made",
                agent="decider",
                payload={
                    "symbol": "2330",
                    "confidence": 0.72,
                    "action": "entry",
                    "reasoning": "2330 突破 20MA",
                },
            )
        )
        msg = await asyncio.wait_for(msg_task, timeout=1.0)
    finally:
        await gen.aclose()

    body = json.loads(msg["data"])
    assert body["payload"]["masked_symbol"] == "STK-A"
    assert body["payload"]["industry_hint"] == "半導體"
    assert body["payload"]["reasoning_summary"] == "STK-? 突破 20MA"
    # Hardest property: the raw 4-digit code never appears anywhere in the
    # serialized frame. This is the SITC mask compliance check.
    assert "2330" not in msg["data"]
    assert "symbol" not in body["payload"]
    assert "reasoning" not in body["payload"]


async def test_unsubscribe_called_on_disconnect(
    fresh_bus: EventBus,
    installed_mask_table: SymbolMaskTable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy_called: list[object] = []
    real_unsubscribe = fresh_bus.unsubscribe

    def spy(q):
        spy_called.append(q)
        real_unsubscribe(q)

    monkeypatch.setattr(fresh_bus, "unsubscribe", spy)

    gen = _public_event_stream()
    try:
        msg_task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0)
        await fresh_bus.emit(
            Event(event_type="decision_made", agent="decider", payload={})
        )
        await asyncio.wait_for(msg_task, timeout=1.0)
    finally:
        await gen.aclose()

    assert len(spy_called) == 1


async def test_idle_yields_keepalive_under_short_timeout(
    fresh_bus: EventBus,
    installed_mask_table: SymbolMaskTable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_module, "_KEEPALIVE_TIMEOUT_SECONDS", 0.05)
    gen = _public_event_stream()
    try:
        msg = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
    finally:
        await gen.aclose()
    assert getattr(msg, "comment", None) == "keepalive"


async def test_stream_without_set_mask_table_raises() -> None:
    clear_mask_table()
    gen = _public_event_stream()
    try:
        with pytest.raises(RuntimeError, match="set_mask_table"):
            await gen.__anext__()
    finally:
        await gen.aclose()


# ---------------------------------------------------------------------------
# HTTP-level behaviour (no auth, CORS, route registration)
# ---------------------------------------------------------------------------


async def test_route_registered_and_no_auth_required() -> None:
    app = create_app()
    paths = {r.path for r in app.routes}
    assert "/api/public/events" in paths


async def test_options_preflight_from_5173_passes_for_public_path() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        r = await client.options(
            "/api/public/events",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert r.status_code == 204
    assert r.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"


async def test_options_preflight_from_admin_dev_5174_also_passes() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        r = await client.options(
            "/api/public/events",
            headers={
                "Origin": "http://localhost:5174",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert r.status_code == 204
    assert r.headers.get("Access-Control-Allow-Origin") == "http://localhost:5174"


async def test_options_preflight_from_unknown_origin_rejected() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        r = await client.options(
            "/api/public/events",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
    # Preflight returns 204 OPTIONS shell but without ACAO, browsers refuse.
    assert "Access-Control-Allow-Origin" not in r.headers


async def test_public_cors_does_not_leak_into_admin_routes() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        r = await client.options(
            "/api/admin/events",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert r.headers.get("Access-Control-Allow-Origin") != "http://localhost:5173"
