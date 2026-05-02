"""Cross-cutting tests: error envelopes never leak path / SQL / traceback.

Spec §「端點不洩漏內部路徑或 settings 值」 requires that ALL endpoints
emit redacted ``internal_error`` envelopes when an unexpected exception
fires. This file injects realistic failure modes into each underlying
function and verifies the response body is clean.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from ohmystock.api.app import create_app
from ohmystock.api.routes import confirm_gate as confirm_gate_route
from ohmystock.api.routes import exit_engine as exit_engine_route
from ohmystock.api.routes import screener as screener_route
from ohmystock.api.routes._deps import get_db
from ohmystock.api.routes.exit_engine import get_market_data
from ohmystock.exit_engine.evaluator import MarketDataLookup
from ohmystock.journal.schema import init_schema


_FORBIDDEN_SUBSTRINGS = (
    "/Users/",
    "/home/",
    "C:\\",
    "SELECT",
    "INSERT",
    "Traceback",
    'File "',
)


_LEAKY_MESSAGE = (
    'Traceback (most recent call last):\n'
    '  File "/Users/mark/secret.py", line 42, in foo\n'
    "    cursor.execute('SELECT * FROM journal_entries WHERE x=1')\n"
    "sqlite3.OperationalError: near 'INSERT': syntax error"
)


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


def _assert_clean(body: dict) -> None:
    encoded = json.dumps(body)
    for needle in _FORBIDDEN_SUBSTRINGS:
        assert needle not in encoded, f"leaked substring: {needle!r} in {encoded!r}"


# ---------------------------------------------------------------------------
# Screener
# ---------------------------------------------------------------------------


async def test_screener_endpoint_redacts_runtime_error(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(**kwargs):
        raise RuntimeError(_LEAKY_MESSAGE)

    monkeypatch.setattr(screener_route, "screen_universe", _boom)
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/screener/run",
            json={"universe": "TWSE+OTC"},
        )
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "internal_error"
    _assert_clean(body)


# ---------------------------------------------------------------------------
# Confirm-gate (4 endpoints — same redaction)
# ---------------------------------------------------------------------------


async def test_pending_endpoint_redacts_internal_error(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*a, **k):
        raise RuntimeError(_LEAKY_MESSAGE)

    monkeypatch.setattr(confirm_gate_route, "list_pending", _boom)
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/confirm-gate/pending")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "internal_error"
    _assert_clean(body)


async def test_confirm_endpoint_redacts_internal_error(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*a, **k):
        raise RuntimeError(_LEAKY_MESSAGE)

    monkeypatch.setattr(confirm_gate_route, "confirm", _boom)
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/confirm",
            json={"decision_id": "x", "user": "mark"},
        )
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "internal_error"
    _assert_clean(body)


async def test_reject_endpoint_redacts_internal_error(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*a, **k):
        raise RuntimeError(_LEAKY_MESSAGE)

    monkeypatch.setattr(confirm_gate_route, "reject", _boom)
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/reject",
            json={"decision_id": "x", "user": "mark", "reason": "weak"},
        )
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "internal_error"
    _assert_clean(body)


async def test_sweep_expired_endpoint_redacts_internal_error(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*a, **k):
        raise RuntimeError(_LEAKY_MESSAGE)

    monkeypatch.setattr(confirm_gate_route, "sweep_expired", _boom)
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/confirm-gate/sweep-expired",
            json={},
        )
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "internal_error"
    _assert_clean(body)


# ---------------------------------------------------------------------------
# Exit engine
# ---------------------------------------------------------------------------


class _NullMarketData:
    def get_close(self, symbol: str, asof: date) -> float | None:
        return None


async def test_exit_engine_endpoint_redacts_internal_error(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*a, **k):
        raise RuntimeError(_LEAKY_MESSAGE)

    monkeypatch.setattr(exit_engine_route, "evaluate_open_positions", _boom)
    async with _build_client(conn, market=_NullMarketData()) as client:
        r = await client.post(
            "/api/admin/exit-engine/run",
            json={"asof_date": "2026-05-07"},
        )
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "internal_error"
    _assert_clean(body)
