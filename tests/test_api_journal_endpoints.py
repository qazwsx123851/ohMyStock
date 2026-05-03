"""HTTP tests for the two read-only journal admin endpoints.

Spec scenarios covered:

* GET /journal/rows — empty list, three-row ordering, kind filter, invalid
  kind 400, limit clamp, limit=0 → 400, offset paging + has_more,
  date_from > date_to → 400, payload restored as nested dict.
* GET /journal/decisions/{id} — not_found 404, single entry, three rows
  ordered ASC.
* Cross-cutting: missing Authorization → 401 ``auth_missing`` for all
  four read endpoints (covers spec §1 and §"4 個 router 註冊").

Spec: openspec/changes/read-side-admin-endpoints-v0/specs/admin-read-endpoints/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

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
) -> int:
    cursor = conn.execute(
        (
            "INSERT INTO journal_entries(decision_id, kind, symbol, "
            "created_at, payload_json) VALUES (?, ?, ?, ?, ?)"
        ),
        (decision_id, kind, symbol, created_at, json.dumps(payload or {})),
    )
    conn.commit()
    return int(cursor.lastrowid or 0)


def _build_client(conn: sqlite3.Connection, *, with_auth: bool = True) -> AsyncClient:
    app = create_app()

    def _override_get_db() -> Iterator[sqlite3.Connection]:
        yield conn

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    headers = (
        {"Authorization": f"Bearer {VALID_ADMIN_TOKEN}"} if with_auth else {}
    )
    return AsyncClient(
        transport=transport, base_url="http://test", headers=headers
    )


# ---------------------------------------------------------------------------
# GET /api/admin/journal/rows
# ---------------------------------------------------------------------------


async def test_rows_empty_table(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/journal/rows")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["items"] == []
    assert body["data"]["total"] == 0
    assert body["data"]["limit"] == 100
    assert body["data"]["offset"] == 0
    assert body["data"]["has_more"] is False


async def test_rows_three_ordered_desc(conn: sqlite3.Connection) -> None:
    _insert(
        conn,
        decision_id="d1",
        kind="entry",
        symbol="2330",
        created_at="2026-05-01T09:00:00+08:00",
    )
    _insert(
        conn,
        decision_id="d2",
        kind="exit",
        symbol="2330",
        created_at="2026-05-02T09:00:00+08:00",
    )
    _insert(
        conn,
        decision_id="d3",
        kind="entry",
        symbol="2454",
        created_at="2026-05-02T09:00:00+08:00",
    )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/journal/rows")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert len(items) == 3
    # First two share created_at; the one inserted later (higher id) is first.
    assert items[0]["created_at"] == "2026-05-02T09:00:00+08:00"
    assert items[1]["created_at"] == "2026-05-02T09:00:00+08:00"
    assert items[0]["id"] > items[1]["id"]
    assert items[2]["kind"] == "entry"
    assert items[2]["symbol"] == "2330"
    assert items[2]["created_at"] == "2026-05-01T09:00:00+08:00"


async def test_rows_filter_by_kind(conn: sqlite3.Connection) -> None:
    _insert(
        conn,
        decision_id="d1",
        kind="entry",
        symbol="2330",
        created_at="2026-05-01T09:00:00+08:00",
    )
    _insert(
        conn,
        decision_id="d1",
        kind="exit",
        symbol="2330",
        created_at="2026-05-02T09:00:00+08:00",
    )
    _insert(
        conn,
        decision_id="d2",
        kind="reject",
        symbol="2454",
        created_at="2026-05-02T10:00:00+08:00",
    )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/journal/rows?kind=entry")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["total"] == 1
    assert len(body["data"]["items"]) == 1
    assert body["data"]["items"][0]["kind"] == "entry"


async def test_rows_invalid_kind_returns_400(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/journal/rows?kind=fill")
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"


async def test_rows_limit_clamps_silently(conn: sqlite3.Connection) -> None:
    for i in range(600):
        _insert(
            conn,
            decision_id=f"d{i}",
            kind="entry",
            symbol="2330",
            created_at=f"2026-05-{((i % 28) + 1):02d}T09:00:00+08:00",
        )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/journal/rows?limit=1000")
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]["items"]) == 500
    assert body["data"]["limit"] == 500  # echoed effective value
    assert body["data"]["total"] == 600
    assert body["data"]["has_more"] is True


async def test_rows_limit_zero_returns_400(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/journal/rows?limit=0")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


async def test_rows_offset_pagination_has_more_false(
    conn: sqlite3.Connection,
) -> None:
    for i in range(250):
        _insert(
            conn,
            decision_id=f"d{i}",
            kind="entry",
            symbol="2330",
            created_at=f"2026-05-{((i % 28) + 1):02d}T09:00:{i % 60:02d}+08:00",
        )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/journal/rows?limit=100&offset=200")
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]["items"]) == 50
    assert body["data"]["total"] == 250
    assert body["data"]["has_more"] is False


async def test_rows_date_from_after_date_to_returns_400(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as client:
        r = await client.get(
            "/api/admin/journal/rows?date_from=2026-05-10&date_to=2026-05-01"
        )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


async def test_rows_payload_restored_as_dict(conn: sqlite3.Connection) -> None:
    _insert(
        conn,
        decision_id="d1",
        kind="entry",
        symbol="2330",
        created_at="2026-05-01T09:00:00+08:00",
        payload={"actual_entry_price": 600.0, "stop_loss": 580.0},
    )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/journal/rows")
    assert r.status_code == 200
    payload = r.json()["data"]["items"][0]["payload"]
    assert isinstance(payload, dict)
    assert payload["actual_entry_price"] == 600.0
    assert payload["stop_loss"] == 580.0


# ---------------------------------------------------------------------------
# GET /api/admin/journal/decisions/{decision_id}
# ---------------------------------------------------------------------------


async def test_decision_not_found_returns_404(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/journal/decisions/missing-id")
    assert r.status_code == 404
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "not_found"


async def test_decision_single_entry_row(conn: sqlite3.Connection) -> None:
    _insert(
        conn,
        decision_id="d1",
        kind="entry",
        symbol="2330",
        created_at="2026-05-01T09:00:00+08:00",
    )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/journal/decisions/d1")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["decision_id"] == "d1"
    assert len(body["data"]["rows"]) == 1
    assert body["data"]["rows"][0]["kind"] == "entry"
    assert body["data"]["rows"][0]["symbol"] == "2330"


async def test_decision_three_rows_ordered_asc(conn: sqlite3.Connection) -> None:
    _insert(
        conn,
        decision_id="d1",
        kind="auto_execute_audit",
        symbol="2330",
        created_at="2026-05-01T09:00:00+08:00",
    )
    _insert(
        conn,
        decision_id="d1",
        kind="entry",
        symbol="2330",
        created_at="2026-05-01T09:00:01+08:00",
    )
    _insert(
        conn,
        decision_id="d1",
        kind="exit",
        symbol="2330",
        created_at="2026-05-03T13:00:00+08:00",
    )
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/journal/decisions/d1")
    assert r.status_code == 200
    rows = r.json()["data"]["rows"]
    assert [row["kind"] for row in rows] == [
        "auto_execute_audit",
        "entry",
        "exit",
    ]


# ---------------------------------------------------------------------------
# Cross-cutting: missing Authorization
# ---------------------------------------------------------------------------


async def test_missing_authorization_returns_401_for_all_read_paths(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn, with_auth=False) as client:
        for path in (
            "/api/admin/journal/rows",
            "/api/admin/journal/decisions/anything",
            "/api/admin/positions/open",
            "/api/admin/stats/today",
        ):
            r = await client.get(path)
            assert r.status_code == 401, path
            body = r.json()
            assert body["ok"] is False, path
            assert body["error"]["code"] == "auth_missing", path


# ---------------------------------------------------------------------------
# Cross-endpoint smoke: route registration
# ---------------------------------------------------------------------------


async def test_all_four_read_paths_registered(conn: sqlite3.Connection) -> None:
    """Cover spec §"4 個 router 註冊"; with valid Bearer, none of the four
    paths returns FastAPI's default 404 ``Not Found`` body."""
    async with _build_client(conn) as client:
        for path in (
            "/api/admin/journal/rows",
            "/api/admin/journal/decisions/anything",
            "/api/admin/positions/open",
            "/api/admin/stats/today",
        ):
            r = await client.get(path)
            body = r.json()
            assert "ok" in body, f"{path} body missing ok key: {body!r}"
