"""HTTP tests for ``GET /api/admin/market/symbols/{symbol}``.

Spec scenarios covered:

* 401 on missing / wrong Bearer token.
* 200 happy path: bars, quote, rs, sepa, institutional, recent_patterns.
* `?days` validation: 0 / 253 → 400 ``invalid_days``; 1 / 252 → 200;
  ``foo`` → 400 or 422 envelope (FastAPI native).
* 404 ``market_symbol_not_found`` only when ``bars_daily`` slice is empty.
* fail-soft: empty RS / chips / patterns → ``null`` / ``[]`` and 200.
* ``change``/``change_pct`` ``null`` when only one bar in slice.
* ``total = foreign + trust + dealer`` invariant (in 張).
* recent-patterns outcome variants:
    * paired entry+exit → ``"+X% 出場"``
    * entry only → ``"+X% 持有中"``
    * unmatched (no entry) → ``"未進場"``

Spec: openspec/changes/web-admin-market-pages/specs/admin-market-symbol-endpoint/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

import ohmystock.api.routes.market as market_module
from ohmystock.api.app import create_app
from ohmystock.api.routes._deps import get_db
from ohmystock.chip.cache import init_chip_schema
from ohmystock.data.cache import init_market_data_schema
from ohmystock.journal.schema import init_schema as init_journal_schema
from ohmystock.sepa.rs import init_schema as init_rs_schema
from tests.conftest import VALID_ADMIN_TOKEN


pytestmark = pytest.mark.asyncio

_TPE = ZoneInfo("Asia/Taipei")
_FAKE_TODAY = datetime(2026, 5, 8, 17, 0, 0, tzinfo=_TPE)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:", check_same_thread=False)
    init_market_data_schema(c)
    init_journal_schema(c)
    init_chip_schema(c)
    init_rs_schema(c)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture()
def freeze_today(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin ``datetime.now(_TPE)`` inside the market handler to 2026-05-08."""

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
            if tz is not None:
                return _FAKE_TODAY
            return _FAKE_TODAY.replace(tzinfo=None)

    monkeypatch.setattr(market_module, "datetime", _FrozenDateTime)


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_bar(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    date: str,
    o: float = 100.0,
    h: float = 110.0,
    l: float = 99.0,
    c: float = 105.0,
    v: int = 1_000_000,
    amount: int = 100_000_000,
) -> None:
    conn.execute(
        "INSERT INTO bars_daily(symbol, date, o, h, l, c, v, amount, source, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (symbol, date, o, h, l, c, v, amount, "test", "2026-05-08T00:00:00+08:00"),
    )
    conn.commit()


def _insert_rs(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    asof_date: str,
    rating: int,
) -> None:
    conn.execute(
        "INSERT INTO rs_rating_cache(asof_date, symbol, rs_rating, "
        "universe_size, computed_at) VALUES (?, ?, ?, ?, ?)",
        (asof_date, symbol, rating, 100, "2026-05-08T00:00:00+00:00"),
    )
    conn.commit()


def _insert_chip(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    date: str,
    foreign_shares: int,
    trust_shares: int,
    dealer_shares: int,
) -> None:
    conn.execute(
        "INSERT INTO chip_three_major_daily(symbol, date, foreign_net, "
        "invest_trust_net, prop_dealer_net, source, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            symbol,
            date,
            foreign_shares,
            trust_shares,
            dealer_shares,
            "test",
            "2026-05-08T00:00:00+08:00",
        ),
    )
    conn.commit()


def _insert_journal(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    kind: str,
    symbol: str,
    created_at: str,
    payload: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, "
        "created_at, payload_json) VALUES (?, ?, ?, ?, ?)",
        (decision_id, kind, symbol, created_at, json.dumps(payload or {})),
    )
    conn.commit()


def _seed_bars_60(conn: sqlite3.Connection, symbol: str = "2330") -> None:
    """Insert 60 daily bars 2026-03-10..2026-05-08, monotonic close 1000..1059.

    Calendar-dense (not trading-day-only) so the endpoint's calendar-window
    walk lands the slice deterministically when ``_FAKE_TODAY`` is 2026-05-08.
    """
    base = datetime(2026, 3, 10).date()
    for i in range(60):
        d = (base + timedelta(days=i)).isoformat()
        _insert_bar(conn, symbol=symbol, date=d, c=1000.0 + i)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_no_auth_returns_401(conn: sqlite3.Connection) -> None:
    async with _build_client(conn, headers={}) as client:
        r = await client.get("/api/admin/market/symbols/2330")
    assert r.status_code == 401
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "auth_missing"


async def test_wrong_token_returns_401(conn: sqlite3.Connection) -> None:
    async with _build_client(
        conn, headers={"Authorization": "Bearer wrong"}
    ) as client:
        r = await client.get("/api/admin/market/symbols/2330")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_invalid"


# ---------------------------------------------------------------------------
# Happy path + schema
# ---------------------------------------------------------------------------


async def test_happy_path_returns_full_envelope(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    _seed_bars_60(conn)
    _insert_rs(conn, symbol="2330", asof_date="2026-05-08", rating=92)
    _insert_chip(
        conn,
        symbol="2330",
        date="2026-05-08",
        foreign_shares=1_200_000,
        trust_shares=300_000,
        dealer_shares=-50_000,
    )

    async with _build_client(conn) as client:
        r = await client.get("/api/admin/market/symbols/2330")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["symbol"] == "2330"

    assert data["quote"]["price"] == 1059.0
    assert data["quote"]["change"] == pytest.approx(1.0, abs=1e-6)
    assert data["quote"]["change_pct"] == pytest.approx(
        1.0 / 1058.0, abs=1e-6
    )

    bars = data["bars_daily"]
    assert len(bars) <= 60
    assert bars[0]["date"] < bars[-1]["date"]

    assert data["rs"] == {"value": 92, "asof": "2026-05-08"}
    # 60 calendar-dense bars are insufficient for classify_stage's 252
    # min-history → fail-soft to None per spec D7.
    assert data["sepa"] is None
    inst_rows = data["institutional"]
    assert len(inst_rows) == 1
    inst = inst_rows[0]
    assert inst["foreign"] == 1200
    assert inst["trust"] == 300
    assert inst["dealer"] == -50
    assert inst["total"] == inst["foreign"] + inst["trust"] + inst["dealer"]
    assert data["recent_patterns"] == []


async def test_change_null_when_only_one_bar(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    _insert_bar(conn, symbol="2330", date="2026-05-08", c=1025.0)

    async with _build_client(conn) as client:
        r = await client.get("/api/admin/market/symbols/2330?days=1")

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["quote"]["price"] == 1025.0
    assert data["quote"]["change"] is None
    assert data["quote"]["change_pct"] is None


# ---------------------------------------------------------------------------
# 404 / fail-soft
# ---------------------------------------------------------------------------


async def test_unknown_symbol_returns_404(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/market/symbols/9999")
    assert r.status_code == 404
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "market_symbol_not_found"


async def test_failsoft_empty_subsources_still_200(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    _seed_bars_60(conn)

    async with _build_client(conn) as client:
        r = await client.get("/api/admin/market/symbols/2330")

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["rs"] is None
    assert data["institutional"] == []
    assert data["recent_patterns"] == []


# ---------------------------------------------------------------------------
# ?days validation
# ---------------------------------------------------------------------------


async def test_days_zero_returns_400(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/market/symbols/2330?days=0")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_days"


async def test_days_253_returns_400(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/market/symbols/2330?days=253")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_days"


async def test_days_foo_returns_400_or_422_envelope(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/market/symbols/2330?days=foo")
    assert r.status_code in (400, 422)
    assert isinstance(r.json(), dict)


async def test_days_1_boundary(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    _insert_bar(conn, symbol="2330", date="2026-05-08", c=1025.0)

    async with _build_client(conn) as client:
        r = await client.get("/api/admin/market/symbols/2330?days=1")
    assert r.status_code == 200
    assert len(r.json()["data"]["bars_daily"]) <= 1


async def test_days_252_boundary(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    _seed_bars_60(conn)
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/market/symbols/2330?days=252")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Institutional invariant
# ---------------------------------------------------------------------------


async def test_institutional_total_equals_sum(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    _seed_bars_60(conn)
    for i, day in enumerate(
        ("2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07", "2026-05-08")
    ):
        _insert_chip(
            conn,
            symbol="2330",
            date=day,
            foreign_shares=(1 + i) * 1_000_000,
            trust_shares=(1 + i) * 100_000,
            dealer_shares=-(1 + i) * 50_000,
        )

    async with _build_client(conn) as client:
        r = await client.get("/api/admin/market/symbols/2330")
    assert r.status_code == 200
    inst = r.json()["data"]["institutional"]
    assert len(inst) == 5
    for row in inst:
        assert row["total"] == row["foreign"] + row["trust"] + row["dealer"]
    assert inst[0]["date"] < inst[-1]["date"]


# ---------------------------------------------------------------------------
# Recent patterns outcome variants
# ---------------------------------------------------------------------------


async def test_pattern_unmatched_outcome_no_entry(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    _seed_bars_60(conn)
    _insert_journal(
        conn,
        decision_id="p1",
        kind="entry",
        symbol="2330",
        created_at="2026-05-01T13:30:00+08:00",
        payload={"pattern": "SEPA breakout", "score": 0.86},
    )

    async with _build_client(conn) as client:
        r = await client.get("/api/admin/market/symbols/2330")
    assert r.status_code == 200
    patterns = r.json()["data"]["recent_patterns"]
    assert len(patterns) == 1
    assert patterns[0]["pattern"] == "SEPA breakout"
    assert patterns[0]["score"] == pytest.approx(0.86)
    assert patterns[0]["outcome"] == "未進場"


async def test_pattern_entry_only_outcome_holding(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    _seed_bars_60(conn)
    _insert_journal(
        conn,
        decision_id="p1",
        kind="reject",
        symbol="2330",
        created_at="2026-04-22T13:30:00+08:00",
        payload={"pattern": "SEPA breakout", "score": 0.86},
    )
    _insert_journal(
        conn,
        decision_id="d1",
        kind="entry",
        symbol="2330",
        created_at="2026-04-23T09:30:00+08:00",
        payload={"actual_entry_price": 1000.0, "actual_qty": 1},
    )

    async with _build_client(conn) as client:
        r = await client.get("/api/admin/market/symbols/2330")
    assert r.status_code == 200
    patterns = r.json()["data"]["recent_patterns"]
    assert len(patterns) == 1
    assert "持有中" in patterns[0]["outcome"]
    assert patterns[0]["outcome"].startswith("+")


async def test_pattern_paired_entry_exit_outcome(
    conn: sqlite3.Connection, freeze_today: None
) -> None:
    _seed_bars_60(conn)
    _insert_journal(
        conn,
        decision_id="p1",
        kind="reject",
        symbol="2330",
        created_at="2026-04-22T13:30:00+08:00",
        payload={"pattern": "SEPA breakout", "score": 0.86},
    )
    _insert_journal(
        conn,
        decision_id="d1",
        kind="entry",
        symbol="2330",
        created_at="2026-04-23T09:30:00+08:00",
        payload={"actual_entry_price": 1000.0, "actual_qty": 1},
    )
    _insert_journal(
        conn,
        decision_id="d1",
        kind="exit",
        symbol="2330",
        created_at="2026-04-26T13:00:00+08:00",
        payload={"actual_exit_price": 1025.0, "pnl_pct": 2.5},
    )

    async with _build_client(conn) as client:
        r = await client.get("/api/admin/market/symbols/2330")
    assert r.status_code == 200
    patterns = r.json()["data"]["recent_patterns"]
    assert len(patterns) == 1
    assert "出場" in patterns[0]["outcome"]
    assert patterns[0]["outcome"].startswith("+2.5")
