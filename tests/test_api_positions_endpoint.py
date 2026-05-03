"""HTTP tests for ``GET /api/admin/positions/open``.

Spec scenarios covered:

* empty journal → ``items=[]``, ``count=0``, ISO ``asof_iso`` with +08:00.
* one filled & open position → enriched with ``stop_loss`` / ``t1_target``
  / ``time_stop_date`` and ``hold_days``.
* payload missing ``stop_loss`` → field is ``null``.
* matching ``exit`` row → no longer listed.
* still ``pending_confirm`` (no ``actual_entry_price``) → not listed.
* per-request connection invariant: spy on ``get_connection`` shows two
  consecutive requests acquire two distinct ``sqlite3.Connection`` objects.

Spec: openspec/changes/read-side-admin-endpoints-v0/specs/admin-read-endpoints/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

import ohmystock.api.db as api_db
from ohmystock.api.app import create_app
from ohmystock.api.routes._deps import get_db
from ohmystock.journal.schema import init_schema
from tests.conftest import VALID_ADMIN_TOKEN


pytestmark = pytest.mark.asyncio


@pytest.fixture()
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:", check_same_thread=False)
    init_schema(c)
    try:
        yield c
    finally:
        c.close()


def _insert(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    kind: str,
    symbol: str,
    created_at: str,
    payload: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        (
            "INSERT INTO journal_entries(decision_id, kind, symbol, "
            "created_at, payload_json) VALUES (?, ?, ?, ?, ?)"
        ),
        (decision_id, kind, symbol, created_at, json.dumps(payload or {})),
    )
    conn.commit()


def _build_client(conn: sqlite3.Connection) -> AsyncClient:
    app = create_app()

    def _override_get_db() -> Iterator[sqlite3.Connection]:
        yield conn

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {VALID_ADMIN_TOKEN}"},
    )


async def test_empty_journal_returns_no_items(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/positions/open")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["items"] == []
    assert body["data"]["count"] == 0
    assert "+08:00" in body["data"]["asof_iso"]


async def test_filled_open_position_enriched(conn: sqlite3.Connection) -> None:
    _insert(
        conn,
        decision_id="d1",
        kind="entry",
        symbol="2330",
        created_at="2026-04-01T09:30:00+08:00",
        payload={
            "actual_entry_price": 600.0,
            "actual_qty": 1,
            "sector": "半導體",
            "stop_loss": 580.0,
            "t1_target": 660.0,
            "time_stop_date": "2026-06-01",
        },
    )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/positions/open")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert len(items) == 1
    item = items[0]
    assert item["decision_id"] == "d1"
    assert item["symbol"] == "2330"
    assert item["entry_price"] == 600.0
    assert item["qty_lots"] == 1
    assert item["sector"] == "半導體"
    assert item["stop_loss"] == 580.0
    assert item["t1_target"] == 660.0
    assert item["time_stop_date"] == "2026-06-01"
    assert item["hold_days"] >= 0


async def test_payload_missing_stop_loss_renders_null(
    conn: sqlite3.Connection,
) -> None:
    _insert(
        conn,
        decision_id="d1",
        kind="entry",
        symbol="2330",
        created_at="2026-04-01T09:30:00+08:00",
        payload={"actual_entry_price": 600.0, "actual_qty": 1},
    )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/positions/open")
    assert r.status_code == 200
    item = r.json()["data"]["items"][0]
    assert item["stop_loss"] is None
    assert item["t1_target"] is None
    assert item["time_stop_date"] is None


async def test_exited_position_not_listed(conn: sqlite3.Connection) -> None:
    _insert(
        conn,
        decision_id="d1",
        kind="entry",
        symbol="2330",
        created_at="2026-04-01T09:30:00+08:00",
        payload={"actual_entry_price": 600.0, "actual_qty": 1},
    )
    _insert(
        conn,
        decision_id="d1",
        kind="exit",
        symbol="2330",
        created_at="2026-04-10T13:00:00+08:00",
        payload={"actual_exit_price": 620.0, "pnl_pct": 3.33},
    )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/positions/open")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["items"] == []
    assert body["data"]["count"] == 0


async def test_pending_confirm_not_listed(conn: sqlite3.Connection) -> None:
    _insert(
        conn,
        decision_id="d1",
        kind="entry",
        symbol="2330",
        created_at="2026-04-01T09:30:00+08:00",
        payload={"decision_status": "pending_confirm"},
    )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/positions/open")
    assert r.status_code == 200
    assert r.json()["data"]["items"] == []


async def test_per_request_connection_invariant(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Spec §1: each request acquires its own ``sqlite3.Connection``.

    We do NOT override ``get_db`` so the production dep calls into
    ``api_db.get_connection`` for real. We point the DB path at a fresh
    tmp file and spy on ``get_connection`` to capture the actual
    connection object handed to each request.
    """
    db_path = tmp_path / "ohmystock-test.db"
    monkeypatch.setenv("OHMYSTOCK_DB_PATH", str(db_path))
    # _get_settings is lru_cached; clear so the new env var is picked up.
    api_db._get_settings.cache_clear()

    captured: list[sqlite3.Connection] = []

    real_get = api_db.get_connection

    def spy_get_connection() -> sqlite3.Connection:
        c = real_get()
        init_schema(c)
        captured.append(c)
        return c

    monkeypatch.setattr(api_db, "get_connection", spy_get_connection)
    # The dep imports ``get_connection`` directly; patch that name too.
    import ohmystock.api.routes._deps as deps_module

    monkeypatch.setattr(deps_module, "get_connection", spy_get_connection)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {VALID_ADMIN_TOKEN}"},
    ) as client:
        r1 = await client.get("/api/admin/positions/open")
        r2 = await client.get("/api/admin/positions/open")

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert len(captured) >= 2
    assert captured[0] is not captured[1]
