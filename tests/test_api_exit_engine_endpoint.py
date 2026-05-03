"""HTTP tests for ``POST /api/admin/exit-engine/run``.

Spec scenarios covered:

* Empty journal → ``evaluated_count=0`` + empty ``results``.
* Confirmed row hits stop_loss → ``closed`` + decision serialised.
* Market data missing → 503 ``market_data_unavailable`` + ``failed_symbols``.
* Invalid ``asof_date`` → 400 ``invalid_input``.
* ``symbol`` filter limits scope.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ohmystock.api.app import create_app
from ohmystock.api.routes._deps import get_db
from ohmystock.api.routes.exit_engine import get_market_data
from ohmystock.exit_engine.evaluator import MarketDataLookup
from ohmystock.journal.schema import init_schema
from tests.conftest import VALID_ADMIN_TOKEN


_DECISION_ID = "dec_X"
_SYMBOL = "2330"


class _DictMarketData:
    def __init__(self, data: dict[tuple[str, date], float]) -> None:
        self._data = data

    def get_close(self, symbol: str, asof: date) -> float | None:
        return self._data.get((symbol, asof))


def _make_payload(
    *,
    decision_status: str = "confirmed",
    actual_entry_price: float = 832.0,
    stop_loss_price: float = 784.58,
    expected_holding_days: int = 8,
    human_confirmed_at: str = "2026-05-02T10:15:00+08:00",
) -> dict[str, Any]:
    return {
        "decision_status": decision_status,
        "actual_entry_price": actual_entry_price,
        "actual_qty": 1000,
        "stop_loss_price": stop_loss_price,
        "expected_holding_days": expected_holding_days,
        "human_confirmed_at": human_confirmed_at,
    }


def _seed_entry(
    conn: sqlite3.Connection,
    *,
    decision_id: str = _DECISION_ID,
    symbol: str = _SYMBOL,
    created_at: str = "2026-05-02T10:00:00+08:00",
    payload: dict[str, Any] | None = None,
) -> str:
    payload = payload if payload is not None else _make_payload()
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        (decision_id, symbol, created_at, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
    return decision_id


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    init_schema(c)
    try:
        yield c
    finally:
        c.close()


def _build_client(
    conn: sqlite3.Connection, market: MarketDataLookup
) -> AsyncClient:
    app = create_app()

    def _override_get_db():
        yield conn

    def _override_get_market_data():
        return market

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_market_data] = _override_get_market_data
    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {VALID_ADMIN_TOKEN}"},
    )


# ---------------------------------------------------------------------------
# Empty journal → evaluated_count=0
# ---------------------------------------------------------------------------


async def test_exit_engine_empty_journal(conn: sqlite3.Connection) -> None:
    market = _DictMarketData({})
    async with _build_client(conn, market) as client:
        r = await client.post(
            "/api/admin/exit-engine/run",
            json={"asof_date": "2026-05-07"},
        )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["results"] == []
    assert data["evaluated_count"] == 0
    assert data["closed_count"] == 0
    assert data["held_count"] == 0
    assert data["asof_date_used"] == "2026-05-07"


# ---------------------------------------------------------------------------
# Stop-loss closes a confirmed row
# ---------------------------------------------------------------------------


async def test_exit_engine_stop_loss_closes_position(
    conn: sqlite3.Connection,
) -> None:
    _seed_entry(conn)
    market = _DictMarketData({(_SYMBOL, date(2026, 5, 7)): 780.0})
    async with _build_client(conn, market) as client:
        r = await client.post(
            "/api/admin/exit-engine/run",
            json={"asof_date": "2026-05-07"},
        )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["evaluated_count"] == 1
    assert data["closed_count"] == 1
    assert data["held_count"] == 0
    result = data["results"][0]
    assert result["decision_id"] == _DECISION_ID
    assert result["action"] == "closed"
    assert result["decision"]["exit_tag"] == "hit_stop_loss"
    assert result["decision"]["actual_exit_price"] == 780.0
    assert "pnl_pct" in result["decision"]
    assert "hold_days" in result["decision"]


# ---------------------------------------------------------------------------
# Market data missing → 503 with failed_symbols
# ---------------------------------------------------------------------------


async def test_exit_engine_missing_market_data_returns_503(
    conn: sqlite3.Connection,
) -> None:
    _seed_entry(conn)
    market = _DictMarketData({})
    async with _build_client(conn, market) as client:
        r = await client.post(
            "/api/admin/exit-engine/run",
            json={"asof_date": "2026-05-07"},
        )
    assert r.status_code == 503
    body = r.json()
    assert body["error"]["code"] == "market_data_unavailable"
    assert body["error"]["failed_symbols"] == [_SYMBOL]


# ---------------------------------------------------------------------------
# Invalid asof_date → 400 invalid_input
# ---------------------------------------------------------------------------


async def test_exit_engine_invalid_asof_returns_400(
    conn: sqlite3.Connection,
) -> None:
    market = _DictMarketData({})
    async with _build_client(conn, market) as client:
        r = await client.post(
            "/api/admin/exit-engine/run",
            json={"asof_date": "2026/13/40"},
        )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


# ---------------------------------------------------------------------------
# Symbol filter limits scope
# ---------------------------------------------------------------------------


async def test_exit_engine_symbol_filter_limits_scope(
    conn: sqlite3.Connection,
) -> None:
    _seed_entry(conn, decision_id="dec_2330", symbol="2330")
    _seed_entry(conn, decision_id="dec_2454", symbol="2454")
    market = _DictMarketData(
        {
            ("2330", date(2026, 5, 7)): 780.0,
            ("2454", date(2026, 5, 7)): 780.0,
        }
    )
    async with _build_client(conn, market) as client:
        r = await client.post(
            "/api/admin/exit-engine/run",
            json={"asof_date": "2026-05-07", "symbol": "2330"},
        )
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["evaluated_count"] == 1
    assert data["results"][0]["decision_id"] == "dec_2330"


