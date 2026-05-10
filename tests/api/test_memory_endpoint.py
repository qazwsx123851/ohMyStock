"""HTTP tests for ``GET /api/admin/memory/rows`` and ``/search``.

Spec scenarios covered (admin-memory-endpoints):

* List 200 shape (empty + non-empty), recency ordering, content_preview /
  content_truncated flags.
* List ``kind`` / ``tag`` / combined filters; pagination + ``has_more``;
  ``limit`` clamp; ``invalid_input`` cases (kind / limit / offset).
* Search 200 BM25 ordering, ``q`` validation (empty / whitespace / missing),
  FTS5 syntax error remap to ``invalid_query`` without leaking parser text,
  boolean expression support, score not exposed, kind/tag query params
  ignored on search.
* 401 ``auth_missing`` / ``auth_invalid`` on both endpoints.
* 405 on POST/PUT/DELETE/PATCH.
* 500 path: store raises non-MemoryStoreError → ``internal_error`` envelope
  with no Traceback leakage.
* Lifespan side-effect: ``memory_rows`` table exists after ``create_app``
  runs through its lifespan handler.

Spec: openspec/changes/web-admin-memory-page-and-store/specs/admin-memory-endpoints/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from ohmystock.api.app import create_app
from ohmystock.api.routes import memory as routes_memory
from ohmystock.api.routes._deps import get_db
from ohmystock.memory import MemoryStore, init_schema
from tests.conftest import VALID_ADMIN_TOKEN


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    kind: str,
    content: str,
    tags: list[str] | None = None,
    source: str | None = None,
    created_at: str = "2026-05-09T10:00:00+08:00",
) -> int:
    cur = conn.execute(
        "INSERT INTO memory_rows(kind, content, tags, source, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (kind, content, json.dumps(tags or []), source, created_at),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


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
# Auth
# ---------------------------------------------------------------------------


async def test_list_no_auth_returns_401(conn: sqlite3.Connection) -> None:
    async with _build_client(conn, with_auth=False) as c:
        r = await c.get("/api/admin/memory/rows")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_missing"


async def test_list_wrong_token_returns_401(conn: sqlite3.Connection) -> None:
    async with _build_client(conn, with_auth=False) as c:
        c.headers["Authorization"] = "Bearer wrong"
        r = await c.get("/api/admin/memory/rows")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_invalid"


async def test_search_no_auth_returns_401(conn: sqlite3.Connection) -> None:
    async with _build_client(conn, with_auth=False) as c:
        r = await c.get("/api/admin/memory/search", params={"q": "x"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_missing"


# ---------------------------------------------------------------------------
# List shape (200)
# ---------------------------------------------------------------------------


async def test_list_empty_db(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/rows")
    assert r.status_code == 200
    assert r.json() == {
        "ok": True,
        "data": {
            "items": [],
            "total": 0,
            "limit": 50,
            "offset": 0,
            "has_more": False,
        },
    }


async def test_list_orders_by_created_at_desc(conn: sqlite3.Connection) -> None:
    older = _insert(
        conn, kind="note", content="older", created_at="2026-05-09T10:00:00+08:00"
    )
    newer = _insert(
        conn, kind="note", content="newer", created_at="2026-05-09T11:00:00+08:00"
    )
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/rows")
    items = r.json()["data"]["items"]
    assert items[0]["id"] == newer
    assert items[1]["id"] == older


async def test_list_content_preview_truncation(conn: sqlite3.Connection) -> None:
    long_text = "x" * 250
    _insert(conn, kind="note", content=long_text)
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/rows")
    item = r.json()["data"]["items"][0]
    assert item["content"] == long_text
    assert len(item["content_preview"]) == 200
    assert item["content_truncated"] is True


async def test_list_short_content_not_truncated(conn: sqlite3.Connection) -> None:
    _insert(conn, kind="note", content="short")
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/rows")
    item = r.json()["data"]["items"][0]
    assert item["content_preview"] == "short"
    assert item["content_truncated"] is False


async def test_list_filters_by_kind(conn: sqlite3.Connection) -> None:
    _insert(conn, kind="note", content="a", created_at="2026-05-09T10:00:01+08:00")
    _insert(conn, kind="lesson", content="b", created_at="2026-05-09T10:00:02+08:00")
    _insert(conn, kind="lesson", content="c", created_at="2026-05-09T10:00:03+08:00")
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/rows", params={"kind": "lesson"})
    body = r.json()
    assert body["data"]["total"] == 2
    assert {i["kind"] for i in body["data"]["items"]} == {"lesson"}


async def test_list_filters_by_tag(conn: sqlite3.Connection) -> None:
    a = _insert(conn, kind="note", content="a", tags=["vcp"])
    b = _insert(conn, kind="note", content="b", tags=["vcp", "breakout"])
    _insert(conn, kind="note", content="c", tags=["breakout"])
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/rows", params={"tag": "vcp"})
    ids = {i["id"] for i in r.json()["data"]["items"]}
    assert ids == {a, b}


async def test_list_combined_kind_and_tag(conn: sqlite3.Connection) -> None:
    _insert(conn, kind="note", content="a", tags=["vcp"])
    target = _insert(conn, kind="lesson", content="b", tags=["vcp"])
    _insert(conn, kind="lesson", content="c", tags=["breakout"])
    async with _build_client(conn) as c:
        r = await c.get(
            "/api/admin/memory/rows", params={"kind": "lesson", "tag": "vcp"}
        )
    items = r.json()["data"]["items"]
    assert [i["id"] for i in items] == [target]


async def test_list_pagination(conn: sqlite3.Connection) -> None:
    for i in range(100):
        _insert(
            conn,
            kind="note",
            content=f"r{i}",
            created_at=f"2026-05-09T10:{i // 60:02d}:{i % 60:02d}+08:00",
        )
    async with _build_client(conn) as c:
        r = await c.get(
            "/api/admin/memory/rows", params={"limit": 20, "offset": 40}
        )
        body = r.json()["data"]
        assert len(body["items"]) == 20
        assert body["offset"] == 40
        assert body["has_more"] is True

        r2 = await c.get(
            "/api/admin/memory/rows", params={"limit": 20, "offset": 80}
        )
        assert r2.json()["data"]["has_more"] is False


async def test_list_limit_clamped_to_200(conn: sqlite3.Connection) -> None:
    for i in range(250):
        _insert(
            conn,
            kind="note",
            content=f"r{i}",
            created_at=f"2026-05-09T10:{i // 60:02d}:{i % 60:02d}+08:00",
        )
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/rows", params={"limit": 999})
    body = r.json()["data"]
    assert len(body["items"]) == 200
    assert body["limit"] == 200


# ---------------------------------------------------------------------------
# List 400 invalid_input
# ---------------------------------------------------------------------------


async def test_list_invalid_kind_returns_400(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/rows", params={"kind": "garbage"})
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"


async def test_list_zero_limit_returns_400(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/rows", params={"limit": 0})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


async def test_list_negative_offset_returns_400(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/rows", params={"offset": -1})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


async def test_list_empty_tag_treated_as_absent(conn: sqlite3.Connection) -> None:
    _insert(conn, kind="note", content="x")
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/rows", params={"tag": ""})
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 1


# ---------------------------------------------------------------------------
# Search shape (200)
# ---------------------------------------------------------------------------


async def test_search_orders_by_bm25(conn: sqlite3.Connection) -> None:
    a = _insert(
        conn,
        kind="note",
        content="breakout breakout breakout",
        created_at="2026-05-09T10:00:00+08:00",
    )
    b = _insert(
        conn,
        kind="note",
        content="breakout once",
        created_at="2026-05-09T10:00:01+08:00",
    )
    _insert(
        conn,
        kind="note",
        content="unrelated",
        created_at="2026-05-09T10:00:02+08:00",
    )
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/search", params={"q": "breakout"})
    body = r.json()["data"]
    assert [i["id"] for i in body["items"]][:2] == [a, b]
    assert body["total"] == 2


async def test_search_response_shape_no_score(conn: sqlite3.Connection) -> None:
    _insert(conn, kind="note", content="hello world")
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/search", params={"q": "hello"})
    item = r.json()["data"]["items"][0]
    assert set(item.keys()) == {
        "id",
        "kind",
        "content",
        "content_preview",
        "content_truncated",
        "tags",
        "source",
        "created_at",
    }


async def test_search_honours_boolean_and(conn: sqlite3.Connection) -> None:
    target = _insert(conn, kind="note", content="VCP breakout")
    _insert(conn, kind="note", content="VCP only")
    _insert(conn, kind="note", content="breakout only")
    async with _build_client(conn) as c:
        r = await c.get(
            "/api/admin/memory/search", params={"q": "VCP AND breakout"}
        )
    body = r.json()["data"]
    assert [i["id"] for i in body["items"]] == [target]
    assert body["total"] == 1


async def test_search_kind_tag_params_ignored(conn: sqlite3.Connection) -> None:
    _insert(conn, kind="note", content="foo", tags=["x"])
    _insert(conn, kind="lesson", content="foo bar", tags=["y"])
    async with _build_client(conn) as c:
        plain = await c.get("/api/admin/memory/search", params={"q": "foo"})
        with_extras = await c.get(
            "/api/admin/memory/search",
            params={"q": "foo", "kind": "lesson", "tag": "vcp"},
        )
    assert plain.json()["data"]["total"] == with_extras.json()["data"]["total"]


# ---------------------------------------------------------------------------
# Search 400
# ---------------------------------------------------------------------------


async def test_search_empty_q_returns_400(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/search", params={"q": ""})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


async def test_search_whitespace_q_returns_400(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/search", params={"q": "   "})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


async def test_search_missing_q_returns_422(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/search")
    assert r.status_code == 422


async def test_search_malformed_query_returns_400_invalid_query(
    conn: sqlite3.Connection,
) -> None:
    _insert(conn, kind="note", content="x")
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/search", params={"q": "foo OR"})
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "invalid_query"
    text = r.text.lower()
    assert "sqlite3" not in text
    # The original SQLite parser wording (e.g. "fts5: syntax error") must NOT
    # leak. Our canned message is "FTS5 query syntax error", which will
    # contain "fts5" in lowercase — that's intentional, so we only assert
    # the verbatim raw-error phrasing is absent.
    assert "fts5: syntax error" not in text
    assert "traceback" not in text


# ---------------------------------------------------------------------------
# 405 on non-GET methods
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
async def test_405_on_rows(conn: sqlite3.Connection, method: str) -> None:
    async with _build_client(conn) as c:
        fn = getattr(c, method)
        r = await fn("/api/admin/memory/rows")
    assert r.status_code == 405


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
async def test_405_on_search(conn: sqlite3.Connection, method: str) -> None:
    async with _build_client(conn) as c:
        fn = getattr(c, method)
        r = await fn("/api/admin/memory/search")
    assert r.status_code == 405


# ---------------------------------------------------------------------------
# 500 internal_error path
# ---------------------------------------------------------------------------


async def test_list_internal_error_path(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(self, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("synthetic internal failure XYZ")

    monkeypatch.setattr(MemoryStore, "list", _boom)
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/memory/rows")
    assert r.status_code == 500
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "internal_error"
    text = r.text.lower()
    assert "traceback" not in text
    assert "synthetic internal failure" not in r.text


# ---------------------------------------------------------------------------
# Lifespan side-effect — memory_rows is created on app startup
# ---------------------------------------------------------------------------


async def test_lifespan_creates_memory_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Drive the FastAPI lifespan context directly and assert that
    ``memory.init_schema`` ran against the bootstrap connection.

    ``httpx.ASGITransport`` does NOT trigger startup/shutdown by default,
    so we enter the lifespan context manager explicitly via FastAPI's
    ``router.lifespan_context``.
    """

    db_path = tmp_path / "lifespan.db"

    def _fake_get_connection() -> sqlite3.Connection:
        return sqlite3.connect(str(db_path), check_same_thread=False)

    monkeypatch.setattr(
        "ohmystock.api.app.get_connection", _fake_get_connection
    )

    app = create_app()
    async with app.router.lifespan_context(app):
        pass

    inspect = sqlite3.connect(str(db_path))
    try:
        table_names = {
            row[0]
            for row in inspect.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('memory_rows', 'memory_rows_fts')"
            ).fetchall()
        }
    finally:
        inspect.close()

    assert table_names == {"memory_rows", "memory_rows_fts"}
    assert hasattr(routes_memory, "router")
