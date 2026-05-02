"""HTTP tests for the four confirm-gate admin endpoints.

Spec scenarios covered:

* GET /pending — empty list, one row serialised, ``timeout_minutes=0`` → 400.
* POST /confirm — success (fill+qty), not_found 404, not_pending 409,
  empty user 400, SSE ``order_sent`` broadcast, no-auth invariant.
* POST /reject — success, empty reason 400, not_pending 409.
* POST /sweep-expired — empty list, one expired row, ``timeout_minutes=-1`` → 400.
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
from ohmystock.journal.schema import init_schema


bus_module = sys.modules["ohmystock.eventbus.bus"]


_DECISION_ID = "dec_2026-05-02T10-00-00_2330"
_SYMBOL = "2330"
_CREATED_AT = "2026-05-02T10:00:00+08:00"


@pytest.fixture()
def fresh_bus(monkeypatch: pytest.MonkeyPatch) -> EventBus:
    fresh = EventBus()
    monkeypatch.setattr(eventbus_pkg, "bus", fresh)
    monkeypatch.setattr(bus_module, "bus", fresh)
    monkeypatch.setattr(app_module, "bus", fresh)
    return fresh


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    init_schema(c)
    try:
        yield c
    finally:
        c.close()


def _seed_pending(
    conn: sqlite3.Connection,
    *,
    decision_id: str = _DECISION_ID,
    symbol: str = _SYMBOL,
    created_at: str = _CREATED_AT,
    final_sizing_pct: float = 25.0,
    current_price: float = 50.0,
    atr_14_pct: float = 2.85,
    decision_status: str = "pending_confirm",
) -> str:
    payload = {
        "decision_status": decision_status,
        "final_sizing_pct": final_sizing_pct,
        "current_price": current_price,
        "atr_14_pct": atr_14_pct,
    }
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        (decision_id, symbol, created_at, json.dumps(payload)),
    )
    conn.commit()
    return decision_id


def _build_client(conn: sqlite3.Connection) -> AsyncClient:
    app = create_app()

    def _override_get_db():
        yield conn

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# GET /api/admin/confirm-gate/pending
# ---------------------------------------------------------------------------


async def test_pending_empty_returns_default_timeout(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/confirm-gate/pending")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["items"] == []
    assert body["data"]["timeout_minutes"] == 30  # config default


async def test_pending_serialises_one_row(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    _seed_pending(conn)
    async with _build_client(conn) as client:
        r = await client.get(
            "/api/admin/confirm-gate/pending?timeout_minutes=120"
        )
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert len(items) == 1
    item = items[0]
    assert set(item.keys()) == {
        "decision_id",
        "symbol",
        "created_at",
        "age_seconds",
        "ttl_seconds",
        "current_price",
        "final_sizing_pct",
    }
    assert item["symbol"] == _SYMBOL
    assert item["current_price"] == 50.0
    assert item["final_sizing_pct"] == 25.0


async def test_pending_timeout_zero_returns_400(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    async with _build_client(conn) as client:
        r = await client.get(
            "/api/admin/confirm-gate/pending?timeout_minutes=0"
        )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


async def test_pending_no_authorization_header_returns_200(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/confirm-gate/pending", headers={})
    assert r.status_code == 200
    assert r.status_code not in (401, 403)


# ---------------------------------------------------------------------------
# POST /api/admin/confirm-gate/confirm
# ---------------------------------------------------------------------------


async def test_confirm_success_returns_fill_and_qty(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    _seed_pending(conn)
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/confirm",
            json={"decision_id": _DECISION_ID, "user": "mark"},
        )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["decision_id"] == _DECISION_ID
    assert data["fill"]["fill_price"] == 50.0
    assert data["fill"]["filled_qty"] == data["qty"]
    assert data["qty"] > 0


async def test_confirm_unknown_decision_returns_404(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/confirm",
            json={"decision_id": "missing", "user": "mark"},
        )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_confirm_not_pending_returns_409(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    _seed_pending(conn, decision_status="confirmed")
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/confirm",
            json={"decision_id": _DECISION_ID, "user": "mark"},
        )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "not_pending"


async def test_confirm_empty_user_returns_400_or_422(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    _seed_pending(conn)
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/confirm",
            json={"decision_id": _DECISION_ID, "user": ""},
        )
    # Pydantic min_length=1 enforces 422; an explicit handler that re-raises
    # ValueError would land 400. Either is acceptable per the no-auth spec
    # (the key invariant is non-401/403).
    assert r.status_code in (400, 422)


async def test_confirm_no_authorization_header_returns_200(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    _seed_pending(conn)
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/confirm",
            json={"decision_id": _DECISION_ID, "user": "mark"},
            headers={},
        )
    assert r.status_code == 200
    assert r.status_code not in (401, 403)


async def test_confirm_emits_order_sent_via_sse(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    _seed_pending(conn)

    gen = _admin_event_stream()
    received: list[tuple[str, dict[str, Any]]] = []

    async def _drain() -> None:
        deadline = asyncio.get_event_loop().time() + 2.0
        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return
            try:
                msg = await asyncio.wait_for(gen.__anext__(), timeout=remaining)
            except asyncio.TimeoutError:
                return
            if isinstance(msg, dict) and msg.get("event") and msg.get("data"):
                received.append((msg["event"], json.loads(msg["data"])))
                if any(t == "order_sent" for t, _ in received):
                    return

    drain_task = asyncio.create_task(_drain())
    await asyncio.sleep(0)

    try:
        async with _build_client(conn) as client:
            r = await client.post(
                "/api/admin/confirm-gate/confirm",
                json={"decision_id": _DECISION_ID, "user": "mark"},
            )
        assert r.status_code == 200
        await asyncio.wait_for(drain_task, timeout=2.0)
    finally:
        await gen.aclose()

    types = [t for t, _ in received]
    assert "order_sent" in types
    order_sent = next(b for t, b in received if t == "order_sent")
    assert order_sent["payload"]["symbol"] == _SYMBOL


# ---------------------------------------------------------------------------
# POST /api/admin/confirm-gate/reject
# ---------------------------------------------------------------------------


async def test_reject_success_returns_reject_row_id(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    _seed_pending(conn)
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/reject",
            json={
                "decision_id": _DECISION_ID,
                "user": "mark",
                "reason": "weak setup",
            },
        )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["decision_id"] == _DECISION_ID
    assert isinstance(data["reject_row_id"], int)
    assert data["reject_row_id"] > 0


async def test_reject_whitespace_reason_returns_400(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    _seed_pending(conn)
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/reject",
            json={
                "decision_id": _DECISION_ID,
                "user": "mark",
                "reason": "   ",
            },
        )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


async def test_reject_already_rejected_returns_409(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    _seed_pending(conn, decision_status="rejected")
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/reject",
            json={
                "decision_id": _DECISION_ID,
                "user": "mark",
                "reason": "weak setup",
            },
        )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "not_pending"


# ---------------------------------------------------------------------------
# POST /api/admin/confirm-gate/sweep-expired
# ---------------------------------------------------------------------------


async def test_sweep_expired_no_rows_returns_empty(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/sweep-expired",
            json={},
        )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["swept_decision_ids"] == []
    assert data["swept_count"] == 0
    assert data["timeout_minutes"] == 30


async def test_sweep_expired_one_row_swept(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    _seed_pending(conn, created_at="2020-01-01T00:00:00+08:00")
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/sweep-expired",
            json={"timeout_minutes": 30},
        )
    assert r.status_code == 200
    data = r.json()["data"]
    assert _DECISION_ID in data["swept_decision_ids"]
    assert data["swept_count"] == 1


async def test_sweep_expired_negative_timeout_returns_400(
    conn: sqlite3.Connection, fresh_bus: EventBus
) -> None:
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/sweep-expired",
            json={"timeout_minutes": -1},
        )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"
