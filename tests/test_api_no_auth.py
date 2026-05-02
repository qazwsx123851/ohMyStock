"""No-auth invariant: every admin action endpoint accepts requests
without ``Authorization`` headers. Bearer auth lands in a follow-on
change (``web-admin-bearer-auth``).
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from ohmystock.api.app import create_app
from ohmystock.api.routes._deps import get_db
from ohmystock.api.routes.exit_engine import get_market_data
from ohmystock.exit_engine.evaluator import MarketDataLookup
from ohmystock.journal.schema import init_schema


class _NullMarketData:
    def get_close(self, symbol: str, asof: date) -> float | None:
        return None


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    init_schema(c)
    try:
        yield c
    finally:
        c.close()


def _build_client(
    conn: sqlite3.Connection,
    market: MarketDataLookup | None = None,
) -> AsyncClient:
    app = create_app()

    def _override_get_db():
        yield conn

    app.dependency_overrides[get_db] = _override_get_db
    if market is not None:
        app.dependency_overrides[get_market_data] = lambda: market
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_screener_run_not_401_or_403(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/screener/run",
            json={"universe": "TWSE+OTC"},
            headers={},
        )
    assert r.status_code not in (401, 403)


async def test_pending_get_not_401_or_403(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/confirm-gate/pending", headers={})
    assert r.status_code not in (401, 403)


async def test_confirm_post_not_401_or_403(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/confirm",
            json={"decision_id": "missing", "user": "mark"},
            headers={},
        )
    assert r.status_code not in (401, 403)


async def test_reject_post_not_401_or_403(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/reject",
            json={"decision_id": "missing", "user": "mark", "reason": "weak"},
            headers={},
        )
    assert r.status_code not in (401, 403)


async def test_sweep_expired_post_not_401_or_403(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/sweep-expired",
            json={},
            headers={},
        )
    assert r.status_code not in (401, 403)


async def test_exit_engine_post_not_401_or_403(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn, market=_NullMarketData()) as client:
        r = await client.post(
            "/api/admin/exit-engine/run",
            json={"asof_date": "2026-05-07"},
            headers={},
        )
    assert r.status_code not in (401, 403)
