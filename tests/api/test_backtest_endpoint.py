"""HTTP tests for ``/api/admin/backtest/*``.

Spec: openspec/changes/web-admin-backtest-pages/specs/admin-backtest-endpoints/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

import ohmystock.api.routes.backtest as backtest_module
from ohmystock.api.app import create_app
from ohmystock.api.routes._deps import get_db
from ohmystock.backtest import storage as backtest_storage
from ohmystock.data.cache import init_market_data_schema
from tests.conftest import VALID_ADMIN_TOKEN


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:", check_same_thread=False)
    init_market_data_schema(c)
    backtest_storage.init_schema(c)
    try:
        yield c
    finally:
        c.close()


def _build_client(
    conn: sqlite3.Connection, *, headers: dict[str, str] | None = None
) -> AsyncClient:
    app = create_app()

    def _override_get_db() -> Iterator[sqlite3.Connection]:
        yield conn

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=headers
        if headers is not None
        else {"Authorization": f"Bearer {VALID_ADMIN_TOKEN}"},
    )


def _seed_bars(
    conn: sqlite3.Connection,
    symbol: str,
    start_year: int = 2024,
    days: int = 252,
) -> list[str]:
    """Insert ``days`` weekday bars starting at ``YYYY-01-01`` with a wiggle
    that gives SmaCross enough room to issue at least one buy + sell."""
    from datetime import date, timedelta

    out: list[str] = []
    base = date(start_year, 1, 1)
    cur = base
    for i in range(days):
        while cur.weekday() >= 5:
            cur += timedelta(days=1)
        cycle = (i % 40) - 20
        price = 100 + i * 0.4 + cycle * 0.5
        conn.execute(
            "INSERT INTO bars_daily(symbol, date, o, h, l, c, v, amount, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                symbol,
                cur.isoformat(),
                price,
                price + 1,
                price - 1,
                price,
                1_000_000,
                100_000_000,
                "test",
                "2026-05-08T00:00:00+08:00",
            ),
        )
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    conn.commit()
    return out


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_get_strategies_401_no_token(conn: sqlite3.Connection) -> None:
    async with _build_client(conn, headers={}) as client:
        resp = await client.get("/api/admin/backtest/strategies")
    assert resp.status_code == 401
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "auth_missing"


async def test_post_run_401_wrong_token(conn: sqlite3.Connection) -> None:
    async with _build_client(
        conn, headers={"Authorization": "Bearer wrong"}
    ) as client:
        resp = await client.post(
            "/api/admin/backtest/run",
            json={
                "strategy": "sma_cross",
                "symbols": ["2330"],
                "period_from": "2024-01-01",
                "period_to": "2024-12-31",
            },
        )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "auth_invalid"


# ---------------------------------------------------------------------------
# /strategies
# ---------------------------------------------------------------------------


async def test_get_strategies_happy(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        resp = await client.get("/api/admin/backtest/strategies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    items = body["data"]["strategies"]
    assert isinstance(items, list)
    assert any(item["name"] == "sma_cross" for item in items)
    for item in items:
        assert set(item.keys()) == {"name", "description"}


# ---------------------------------------------------------------------------
# POST /run
# ---------------------------------------------------------------------------


async def test_post_run_happy_persists_row(conn: sqlite3.Connection) -> None:
    _seed_bars(conn, "2330", start_year=2024, days=200)
    async with _build_client(conn) as client:
        resp = await client.post(
            "/api/admin/backtest/run",
            json={
                "strategy": "sma_cross",
                "symbols": ["2330"],
                "period_from": "2024-01-02",
                "period_to": "2024-09-30",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["status"] == "completed"
    assert isinstance(data["job_id"], str) and len(data["job_id"]) == 32

    rows = conn.execute("SELECT id, status, result_json FROM backtest_jobs").fetchall()
    assert len(rows) == 1
    decoded = json.loads(rows[0][2])
    assert "equity_curve" in decoded
    assert "trades" in decoded


async def test_post_run_missing_bars_400(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        resp = await client.post(
            "/api/admin/backtest/run",
            json={
                "strategy": "sma_cross",
                "symbols": ["9999"],
                "period_from": "2024-01-01",
                "period_to": "2024-12-31",
            },
        )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "missing_bars"
    assert "9999" in body["error"]["message"]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "strategy": "nonexistent",
            "symbols": ["2330"],
            "period_from": "2024-01-01",
            "period_to": "2024-12-31",
        },
        {
            "strategy": "sma_cross",
            "symbols": ["2330"],
            "period_from": "2024-12-31",
            "period_to": "2024-01-01",
        },
    ],
)
async def test_post_run_invalid_input_400(
    conn: sqlite3.Connection, payload: dict
) -> None:
    async with _build_client(conn) as client:
        resp = await client.post("/api/admin/backtest/run", json=payload)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_input"


async def test_post_run_oversized_symbols_400(conn: sqlite3.Connection) -> None:
    payload = {
        "strategy": "sma_cross",
        "symbols": [str(1000 + i) for i in range(51)],
        "period_from": "2024-01-01",
        "period_to": "2024-12-31",
    }
    async with _build_client(conn) as client:
        resp = await client.post("/api/admin/backtest/run", json=payload)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "input_too_large"


async def test_post_run_oversized_period_400(conn: sqlite3.Connection) -> None:
    payload = {
        "strategy": "sma_cross",
        "symbols": ["2330"],
        "period_from": "2010-01-01",
        "period_to": "2024-12-31",
    }
    async with _build_client(conn) as client:
        resp = await client.post("/api/admin/backtest/run", json=payload)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "input_too_large"


async def test_post_run_engine_failure_persists_failed_row(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_bars(conn, "2330", start_year=2024, days=30)

    def fake_run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "ok": False,
            "elapsed_ms": 5,
            "data": None,
            "error": {
                "code": "INVALID_INPUT",
                "message": "warmup not satisfied",
                "retriable": False,
            },
        }

    monkeypatch.setattr(backtest_module, "run_backtest", fake_run)

    async with _build_client(conn) as client:
        resp = await client.post(
            "/api/admin/backtest/run",
            json={
                "strategy": "sma_cross",
                "symbols": ["2330"],
                "period_from": "2024-01-02",
                "period_to": "2024-02-01",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] == "failed"

    row = conn.execute(
        "SELECT status, result_json FROM backtest_jobs"
    ).fetchone()
    assert row[0] == "failed"
    assert json.loads(row[1])["error"]["code"] == "INVALID_INPUT"


# ---------------------------------------------------------------------------
# GET /jobs
# ---------------------------------------------------------------------------


def _insert_completed_row(
    conn: sqlite3.Connection,
    *,
    id: str,
    created_at: str,
    metrics: dict | None = None,
    equity_curve: list[dict] | None = None,
    trades: list[dict] | None = None,
) -> None:
    payload = {
        "metrics": metrics
        or {
            "cagr": 0.182,
            "sharpe": 1.42,
            "max_drawdown": -0.083,
            "win_rate": 0.54,
            "total_return": 0.18,
            "sortino": 1.6,
            "profit_factor": 1.5,
            "expectancy": 1200.0,
            "total_trades": 12,
            "mdd_duration_days": 21,
        },
        "equity_curve": equity_curve
        or [{"date": "2024-01-02", "equity": 1_000_000.0}],
        "trades": trades or [],
    }
    backtest_storage.insert_job(
        conn,
        backtest_storage.BacktestJobRow(
            id=id,
            strategy="sma_cross",
            period_from="2024-01-01",
            period_to="2024-12-31",
            custom_symbols_json=json.dumps(["2330"]),
            initial_capital=1_000_000.0,
            status="completed",
            elapsed_ms=200,
            result_json=json.dumps(payload),
            created_at=created_at,
        ),
    )


def _insert_failed_row(
    conn: sqlite3.Connection, *, id: str, created_at: str
) -> None:
    backtest_storage.insert_job(
        conn,
        backtest_storage.BacktestJobRow(
            id=id,
            strategy="sma_cross",
            period_from="2024-07-01",
            period_to="2024-12-31",
            custom_symbols_json=json.dumps(["2330"]),
            initial_capital=1_000_000.0,
            status="failed",
            elapsed_ms=5,
            result_json=json.dumps(
                {"error": {"code": "INVALID_INPUT", "message": "warmup"}}
            ),
            created_at=created_at,
        ),
    )


async def test_get_jobs_empty(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        resp = await client.get("/api/admin/backtest/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["items"] == []
    assert body["data"]["count"] == 0


async def test_get_jobs_sorted_desc(conn: sqlite3.Connection) -> None:
    _insert_completed_row(conn, id="r1", created_at="2026-05-01T10:00:00+08:00")
    _insert_completed_row(conn, id="r3", created_at="2026-05-08T10:00:00+08:00")
    _insert_completed_row(conn, id="r2", created_at="2026-05-04T10:00:00+08:00")
    async with _build_client(conn) as client:
        resp = await client.get("/api/admin/backtest/jobs")
    items = resp.json()["data"]["items"]
    assert [i["id"] for i in items] == ["r3", "r2", "r1"]
    assert items[0]["created_at"] == "2026-05-08T10:00:00+08:00"


async def test_get_jobs_limit_clamp(conn: sqlite3.Connection) -> None:
    for i in range(120):
        _insert_completed_row(
            conn,
            id=f"r{i:03d}",
            created_at=f"2026-04-{(i % 28) + 1:02d}T00:00:{i % 60:02d}+08:00",
        )
    async with _build_client(conn) as client:
        resp = await client.get("/api/admin/backtest/jobs?limit=500")
    assert len(resp.json()["data"]["items"]) <= 100


async def test_get_jobs_does_not_leak_result_json(
    conn: sqlite3.Connection,
) -> None:
    _insert_completed_row(conn, id="r1", created_at="2026-05-08T10:00:00+08:00")
    async with _build_client(conn) as client:
        resp = await client.get("/api/admin/backtest/jobs")
    body_str = resp.text
    assert "result_json" not in body_str
    assert "equity_curve" not in body_str
    item = resp.json()["data"]["items"][0]
    assert "result_json" not in item
    assert "trades" not in item


async def test_get_jobs_failed_row_has_null_metrics(
    conn: sqlite3.Connection,
) -> None:
    _insert_failed_row(conn, id="f1", created_at="2026-05-08T10:00:00+08:00")
    async with _build_client(conn) as client:
        resp = await client.get("/api/admin/backtest/jobs")
    item = resp.json()["data"]["items"][0]
    assert item["status"] == "failed"
    assert item["annual_return_pct"] is None
    assert item["sharpe"] is None
    assert item["max_drawdown_pct"] is None
    assert item["win_rate_pct"] is None


# ---------------------------------------------------------------------------
# GET /jobs/{id}
# ---------------------------------------------------------------------------


async def test_get_job_detail_404(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        resp = await client.get(
            "/api/admin/backtest/jobs/0123456789abcdef0123456789abcdef"
        )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_get_job_detail_completed_full_payload(
    conn: sqlite3.Connection,
) -> None:
    equity = [
        {"date": "2024-01-02", "equity": 1_000_000.0},
        {"date": "2024-01-03", "equity": 1_010_000.0},
        {"date": "2024-01-04", "equity": 1_005_000.0},
        {"date": "2024-01-05", "equity": 1_020_000.0},
        {"date": "2024-01-08", "equity": 1_030_000.0},
    ]
    trades = [
        {
            "symbol": "2330",
            "side": "buy",
            "qty": 1000,
            "fill_price": 600.0,
            "fill_date": "2024-01-03",
            "status": "filled",
            "cost": {"total": 0.0},
        },
        {
            "symbol": "2330",
            "side": "sell",
            "qty": 1000,
            "fill_price": 612.0,
            "fill_date": "2024-01-08",
            "status": "filled",
            "cost": {"total": 0.0},
        },
    ]
    _insert_completed_row(
        conn,
        id="j1",
        created_at="2026-05-08T10:00:00+08:00",
        equity_curve=equity,
        trades=trades,
    )
    async with _build_client(conn) as client:
        resp = await client.get("/api/admin/backtest/jobs/j1")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["metrics"] is not None
    assert len(data["equity_curve"]) == 5
    assert len(data["drawdown"]) == 5
    assert len(data["trades"]) == 1
    assert data["trades"][0]["entry_date"] == "2024-01-03"
    assert data["trades"][0]["exit_date"] == "2024-01-08"
    assert data["trades"][0]["pnl_twd"] == pytest.approx(12000.0)
    assert data["error"] is None


async def test_get_job_detail_drawdown_correctness(
    conn: sqlite3.Connection,
) -> None:
    equity = [
        {"date": "d1", "equity": 100.0},
        {"date": "d2", "equity": 120.0},
        {"date": "d3", "equity": 90.0},
        {"date": "d4", "equity": 150.0},
    ]
    _insert_completed_row(
        conn,
        id="dd1",
        created_at="2026-05-08T10:00:00+08:00",
        equity_curve=equity,
        trades=[],
    )
    async with _build_client(conn) as client:
        resp = await client.get("/api/admin/backtest/jobs/dd1")
    dd = resp.json()["data"]["drawdown"]
    assert dd[0]["dd"] == pytest.approx(0.0)
    assert dd[1]["dd"] == pytest.approx(0.0)
    assert dd[2]["dd"] == pytest.approx(-0.25, abs=1e-6)
    assert dd[3]["dd"] == pytest.approx(0.0)


async def test_get_job_detail_failed_degraded(
    conn: sqlite3.Connection,
) -> None:
    _insert_failed_row(conn, id="fdetail", created_at="2026-05-08T10:00:00+08:00")
    async with _build_client(conn) as client:
        resp = await client.get("/api/admin/backtest/jobs/fdetail")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["metrics"] is None
    assert data["equity_curve"] == []
    assert data["drawdown"] == []
    assert data["trades"] == []
    assert data["error"]["code"]
    assert data["error"]["message"]


# ---------------------------------------------------------------------------
# Internal-error redaction
# ---------------------------------------------------------------------------


async def test_internal_error_redacts_sensitive_strings(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_bars(conn, "2330", start_year=2024, days=30)

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError(
            "/Users/secret/db corrupt: SELECT * FROM backtest_jobs\nTraceback (most recent call last)"
        )

    monkeypatch.setattr(backtest_storage, "insert_job", boom)
    async with _build_client(conn) as client:
        resp = await client.post(
            "/api/admin/backtest/run",
            json={
                "strategy": "sma_cross",
                "symbols": ["2330"],
                "period_from": "2024-01-02",
                "period_to": "2024-02-01",
            },
        )
    assert resp.status_code == 500
    text = resp.text
    assert "/Users/" not in text
    assert "SELECT" not in text
    assert "Traceback" not in text
