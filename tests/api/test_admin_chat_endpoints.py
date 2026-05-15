"""HTTP tests for ``/api/admin/chat/*``.

Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/admin-chat-endpoints/spec.md

The streaming POST endpoint is exercised via a monkeypatched
``_ANTHROPIC_CLIENT_FACTORY`` so no real API call is ever made.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ohmystock.api.app import create_app
from ohmystock.api.routes import chat as routes_chat
from ohmystock.api.routes._deps import get_db
from ohmystock.chat import init_schema as chat_init_schema
from ohmystock.journal.schema import init_schema as journal_init_schema
from tests.conftest import VALID_ADMIN_TOKEN


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:", check_same_thread=False)
    journal_init_schema(c)
    chat_init_schema(c)
    try:
        yield c
    finally:
        c.close()


def _build_client(
    conn: sqlite3.Connection, *, with_auth: bool = True
) -> AsyncClient:
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


def _ok_response(text: str, *, stop_reason: str = "end_turn") -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=5, output_tokens=10),
    )


class _FakeMessages:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)

    def create(self, **kwargs: Any) -> Any:  # noqa: ANN401
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.messages = _FakeMessages(responses)


@pytest.fixture()
def mock_anthropic(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    client = _FakeClient([_ok_response("好的，台積電目前股價穩定。")])
    monkeypatch.setattr(
        routes_chat, "_ANTHROPIC_CLIENT_FACTORY", lambda key: client
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    return client


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_list_sessions_no_auth_returns_401(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn, with_auth=False) as c:
        r = await c.get("/api/admin/chat/sessions")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_missing"


async def test_search_no_auth_returns_401(conn: sqlite3.Connection) -> None:
    async with _build_client(conn, with_auth=False) as c:
        r = await c.get("/api/admin/chat/search", params={"q": "x"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Sessions list (GET /sessions)
# ---------------------------------------------------------------------------


async def test_list_sessions_empty(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/chat/sessions")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["total"] == 0
    assert body["data"]["items"] == []
    assert body["data"]["has_more"] is False


async def test_list_sessions_limit_zero_400(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/chat/sessions", params={"limit": 0})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


# ---------------------------------------------------------------------------
# Create session (POST /sessions)
# ---------------------------------------------------------------------------


async def test_create_session_defaults(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as c:
        r = await c.post("/api/admin/chat/sessions", json={})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["id"].startswith("chat_")
    assert len(data["id"]) == len("chat_") + 8
    assert data["title"] == "新對話"
    assert data["message_count"] == 0


async def test_create_session_extra_field_rejected(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as c:
        r = await c.post(
            "/api/admin/chat/sessions", json={"title": "x", "extra": "boom"}
        )
    assert r.status_code == 422


async def test_create_session_title_too_long(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as c:
        r = await c.post(
            "/api/admin/chat/sessions", json={"title": "x" * 121}
        )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Session detail (GET /sessions/{id})
# ---------------------------------------------------------------------------


async def test_get_session_detail_path_traversal_400(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/chat/sessions/..%2Fsecrets")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


async def test_get_session_detail_not_found(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/chat/sessions/chat_aaaaaaaa")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_get_session_detail_after_create(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as c:
        new = await c.post("/api/admin/chat/sessions", json={})
        sid = new.json()["data"]["id"]
        r = await c.get(f"/api/admin/chat/sessions/{sid}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["session"]["id"] == sid
    assert data["messages"] == []


# ---------------------------------------------------------------------------
# Delete (DELETE /sessions/{id})
# ---------------------------------------------------------------------------


async def test_delete_session_unknown_404(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as c:
        r = await c.delete("/api/admin/chat/sessions/chat_aaaaaaaa")
    assert r.status_code == 404


async def test_delete_then_detail_returns_422(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as c:
        new = await c.post("/api/admin/chat/sessions", json={})
        sid = new.json()["data"]["id"]
        r1 = await c.delete(f"/api/admin/chat/sessions/{sid}")
        r2 = await c.get(f"/api/admin/chat/sessions/{sid}")
    assert r1.status_code == 200
    assert r1.json()["data"]["deleted"] is True
    assert r2.status_code == 422
    assert r2.json()["error"]["code"] == "session_deleted"


async def test_delete_idempotent(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as c:
        new = await c.post("/api/admin/chat/sessions", json={})
        sid = new.json()["data"]["id"]
        r1 = await c.delete(f"/api/admin/chat/sessions/{sid}")
        r2 = await c.delete(f"/api/admin/chat/sessions/{sid}")
    assert r1.status_code == 200
    assert r2.status_code == 200


# ---------------------------------------------------------------------------
# Send message — pre-stream validation
# ---------------------------------------------------------------------------


async def test_send_message_unknown_session_404(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as c:
        r = await c.post(
            "/api/admin/chat/sessions/chat_aaaaaaaa/messages",
            json={"content": "hi"},
        )
    assert r.status_code == 404


async def test_send_message_missing_api_key_422(
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    async with _build_client(conn) as c:
        new = await c.post("/api/admin/chat/sessions", json={})
        sid = new.json()["data"]["id"]
        r = await c.post(
            f"/api/admin/chat/sessions/{sid}/messages",
            json={"content": "hi"},
        )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "missing_api_key"


async def test_send_message_deleted_session_422(
    conn: sqlite3.Connection,
    mock_anthropic: _FakeClient,
) -> None:
    async with _build_client(conn) as c:
        new = await c.post("/api/admin/chat/sessions", json={})
        sid = new.json()["data"]["id"]
        await c.delete(f"/api/admin/chat/sessions/{sid}")
        r = await c.post(
            f"/api/admin/chat/sessions/{sid}/messages",
            json={"content": "hi"},
        )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "session_deleted"


# ---------------------------------------------------------------------------
# Send message — streaming happy path
# ---------------------------------------------------------------------------


async def test_send_message_streams_and_persists(
    conn: sqlite3.Connection,
    mock_anthropic: _FakeClient,
) -> None:
    async with _build_client(conn) as c:
        new = await c.post("/api/admin/chat/sessions", json={})
        sid = new.json()["data"]["id"]
        r = await c.post(
            f"/api/admin/chat/sessions/{sid}/messages",
            json={"content": "今天 2330 怎樣"},
        )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        body = r.text
        # SSE frames present
        assert "event: delta" in body
        assert "event: done" in body

        # Stored messages
        detail = await c.get(f"/api/admin/chat/sessions/{sid}")
        msgs = detail.json()["data"]["messages"]
        roles = [m["role"] for m in msgs]
        assert roles == ["user", "assistant"]
        assert "台積電" in msgs[1]["content"]

    rows = conn.execute(
        "SELECT decision_id FROM llm_costs WHERE decision_id LIKE 'chat:%'"
    ).fetchall()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Search (GET /search)
# ---------------------------------------------------------------------------


async def test_search_empty_q_400(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/chat/search", params={"q": "   "})
    # FastAPI's Query(min_length=1) treats whitespace as non-empty; our
    # store's _sanitise_q strips and raises invalid_input → 400.
    assert r.status_code in (400, 422)


async def test_search_missing_q_422(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as c:
        r = await c.get("/api/admin/chat/search")
    assert r.status_code == 422


async def test_search_inverted_dates_400(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as c:
        r = await c.get(
            "/api/admin/chat/search",
            params={
                "q": "x",
                "date_from": "2026-05-15",
                "date_to": "2026-05-01",
            },
        )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


async def test_search_fts5_syntax_error_remapped(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as c:
        new = await c.post("/api/admin/chat/sessions", json={})
        sid = new.json()["data"]["id"]
        # Insert a message directly so the FTS5 index is non-empty.
        conn.execute(
            "INSERT INTO chat_messages "
            "(id, session_id, role, content, tool_calls_json, "
            " tool_result_for, llm_cost_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "msg_aaaaaaaaaaaa",
                sid,
                "user",
                "hello",
                None,
                None,
                None,
                "2026-05-15T07:00:00+08:00",
            ),
        )
        conn.commit()
        r = await c.get("/api/admin/chat/search", params={"q": '"unclosed'})
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "invalid_query"
    assert "OperationalError" not in r.text


async def test_search_returns_groups(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as c:
        new = await c.post("/api/admin/chat/sessions", json={})
        sid = new.json()["data"]["id"]
        conn.execute(
            "INSERT INTO chat_messages "
            "(id, session_id, role, content, tool_calls_json, "
            " tool_result_for, llm_cost_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "msg_aaaaaaaaaaaa",
                sid,
                "user",
                "台積電 籌碼分析",
                None,
                None,
                None,
                "2026-05-15T07:00:00+08:00",
            ),
        )
        conn.commit()
        r = await c.get(
            "/api/admin/chat/search", params={"q": "台積電", "limit": 10}
        )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total_hits"] == 1
    assert data["groups"][0]["session_id"] == sid
