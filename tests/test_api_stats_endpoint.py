"""HTTP tests for ``GET /api/admin/stats/today``.

Spec scenarios covered:

* empty journal → all six counters are int 0.
* one pending entry + one filled entry + one reject (today) → counts.
* yesterday's row (TPE) does not contribute to today's counters.
* TPE midnight boundary: a row at 00:00:01 +08:00 of today is counted.
* ``auto_execute_audit`` rows go to their own counter, not ``decisions_made``.
* internal_error fallback: the response strips paths and SQL fragments;
  the per-request connection is closed even on raise.

Spec: openspec/changes/read-side-admin-endpoints-v0/specs/admin-read-endpoints/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

import ohmystock.api.routes.stats as stats_module
from ohmystock.api.app import create_app
from ohmystock.api.routes._deps import get_db, get_settings_dep
from ohmystock.config import Settings
from ohmystock.journal.schema import init_schema
from tests.conftest import VALID_ADMIN_TOKEN


pytestmark = pytest.mark.asyncio

_TPE = ZoneInfo("Asia/Taipei")
_FAKE_TODAY = datetime(2026, 5, 3, 12, 0, 0, tzinfo=_TPE)


@pytest.fixture()
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:", check_same_thread=False)
    init_schema(c)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture()
def freeze_today(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin ``datetime.now(_TPE)`` inside the stats handler to 2026-05-03."""

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
            if tz is not None:
                return _FAKE_TODAY
            return _FAKE_TODAY.replace(tzinfo=None)

    monkeypatch.setattr(stats_module, "datetime", _FrozenDateTime)


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


async def test_empty_journal_all_zeros(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/stats/today")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["asof_date"] == "2026-05-03"
    for key in (
        "decisions_made",
        "entries_pending",
        "entries_filled",
        "rejects",
        "expires",
        "auto_execute_audits",
    ):
        assert data[key] == 0, key
        assert isinstance(data[key], int), key


async def test_today_pending_filled_reject(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    _insert(
        conn,
        decision_id="d1",
        kind="entry",
        symbol="2330",
        created_at="2026-05-03T09:00:00+08:00",
        payload={"decision_status": "pending_confirm"},
    )
    _insert(
        conn,
        decision_id="d2",
        kind="entry",
        symbol="2454",
        created_at="2026-05-03T09:30:00+08:00",
        payload={"actual_entry_price": 600.0, "actual_qty": 1},
    )
    _insert(
        conn,
        decision_id="d3",
        kind="reject",
        symbol="2317",
        created_at="2026-05-03T10:00:00+08:00",
    )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/stats/today")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["decisions_made"] == 2
    assert data["entries_pending"] == 1
    assert data["entries_filled"] == 1
    assert data["rejects"] == 1
    assert data["expires"] == 0


async def test_yesterday_row_not_counted(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    _insert(
        conn,
        decision_id="d1",
        kind="entry",
        symbol="2330",
        created_at="2026-05-02T23:59:00+08:00",
        payload={"actual_entry_price": 600.0, "actual_qty": 1},
    )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/stats/today")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["decisions_made"] == 0
    assert data["entries_filled"] == 0


async def test_tpe_midnight_edge(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    _insert(
        conn,
        decision_id="d1",
        kind="entry",
        symbol="2330",
        created_at="2026-05-03T00:00:01+08:00",
        payload={"actual_entry_price": 600.0, "actual_qty": 1},
    )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/stats/today")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["decisions_made"] == 1
    assert data["entries_filled"] == 1


async def test_audit_rows_dedicated_counter(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    _insert(
        conn,
        decision_id="d1",
        kind="auto_execute_audit",
        symbol="2330",
        created_at="2026-05-03T09:00:00+08:00",
    )
    _insert(
        conn,
        decision_id="d2",
        kind="auto_execute_audit",
        symbol="2454",
        created_at="2026-05-03T09:30:00+08:00",
    )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/stats/today")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["auto_execute_audits"] == 2
    # decisions_made counts only kind='entry'.
    assert data["decisions_made"] == 0


def _build_client_with_settings(
    conn: sqlite3.Connection, settings: Settings
) -> AsyncClient:
    app = create_app()

    def _override_get_db() -> Iterator[sqlite3.Connection]:
        yield conn

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_settings_dep] = lambda: settings
    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {VALID_ADMIN_TOKEN}"},
    )


def _insert_closed_trade(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    symbol: str,
    entry_price: float,
    qty_lots: int,
    pnl_pct: float,
    when: str,
) -> None:
    _insert(
        conn,
        decision_id=decision_id,
        kind="entry",
        symbol=symbol,
        created_at=when,
        payload={"actual_entry_price": entry_price, "actual_qty": qty_lots},
    )
    _insert(
        conn,
        decision_id=decision_id,
        kind="exit",
        symbol=symbol,
        created_at=when,
        payload={"pnl_pct": pnl_pct},
    )


async def test_monthly_breaker_tripped(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    # entry 600 * 1 lot * 1000 = 600,000 notional; pnl -15% → -90,000 TWD.
    # equity 1,000,000 → -9.0% ≤ -8.0% threshold → tripped.
    _insert_closed_trade(
        conn,
        decision_id="d1",
        symbol="2330",
        entry_price=600.0,
        qty_lots=1,
        pnl_pct=-15.0,
        when="2026-05-03T09:00:00+08:00",
    )
    settings = Settings(
        starting_equity_twd=1_000_000,
        ohmystock_monthly_breaker_pct=-8.0,
        ohmystock_monthly_budget_usd=100.0,
    )
    async with _build_client_with_settings(conn, settings) as client:
        r = await client.get("/api/admin/stats/today")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["monthly_breaker"]["tripped"] is True
    assert data["monthly_breaker"]["month_pnl_pct"] == pytest.approx(-9.0)


async def test_monthly_breaker_not_tripped(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    _insert_closed_trade(
        conn,
        decision_id="d1",
        symbol="2330",
        entry_price=600.0,
        qty_lots=1,
        pnl_pct=-1.0,  # -6,000 TWD → -0.6% > -8%
        when="2026-05-03T09:00:00+08:00",
    )
    settings = Settings(
        starting_equity_twd=1_000_000,
        ohmystock_monthly_breaker_pct=-8.0,
        ohmystock_monthly_budget_usd=100.0,
    )
    async with _build_client_with_settings(conn, settings) as client:
        r = await client.get("/api/admin/stats/today")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["monthly_breaker"]["tripped"] is False


async def test_cost_fields(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    conn.execute(
        "INSERT INTO llm_costs"
        "(model, input_tokens, output_tokens, cost_usd, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("claude-opus-4-7", 100, 100, 40.0, "2026-05-03T09:00:00+08:00"),
    )
    conn.execute(
        "INSERT INTO llm_costs"
        "(model, input_tokens, output_tokens, cost_usd, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("claude-haiku-4-5-20251001", 100, 100, 10.0, "2026-04-30T09:00:00+08:00"),
    )
    conn.commit()
    settings = Settings(ohmystock_monthly_budget_usd=100.0)
    async with _build_client_with_settings(conn, settings) as client:
        r = await client.get("/api/admin/stats/today")
    assert r.status_code == 200
    data = r.json()["data"]
    # only the May row counts toward 2026-05 month-to-date.
    assert data["cost"]["used_usd"] == pytest.approx(40.0)
    assert data["cost"]["budget_usd"] == pytest.approx(100.0)
    assert data["cost"]["pct"] == pytest.approx(40.0)


async def test_internal_error_redacts_path_and_sql() -> None:
    """Spec §1: 500 envelope must not leak ``/Users/`` paths or SQL fragments,
    and the per-request connection must be closed even on raise."""
    closed: list[bool] = []

    class _RaisingConn:
        def execute(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(
                "/Users/secret/x failed: SELECT * FROM journal_entries"
            )

        def close(self) -> None:
            closed.append(True)

    raising_conn = _RaisingConn()

    app = create_app()

    def _override_get_db() -> Iterator[Any]:
        try:
            yield raising_conn
        finally:
            raising_conn.close()

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {VALID_ADMIN_TOKEN}"},
    ) as client:
        r = await client.get("/api/admin/stats/today")

    assert r.status_code == 500
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "internal_error"
    msg = body["error"]["message"]
    assert "/Users/" not in msg
    assert "SELECT" not in msg
    assert "Traceback" not in msg
    assert closed, "expected connection.close() to be invoked at least once"
