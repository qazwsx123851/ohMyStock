"""Storage layer tests: schema bootstrap, CRUD, FTS5 search.

Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/chat-store/spec.md
"""

from __future__ import annotations

import sqlite3

import pytest

from ohmystock.chat import (
    ChatMessage,
    ChatSession,
    ChatStoreError,
    get_session,
    init_schema,
    insert_message,
    insert_session,
    list_sessions,
    search_messages,
    select_messages,
    soft_delete_session,
    touch_session,
    update_session_title,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    return c


def _session(
    *,
    id: str = "chat_12345678",
    title: str = "x",
    status: str = "active",
    updated: str = "2026-05-15T07:00:00+08:00",
) -> ChatSession:
    return ChatSession(
        id=id,
        title=title,
        model="claude-sonnet-4-6",
        status=status,
        created_at=updated,
        updated_at=updated,
    )


def _msg(
    *,
    id: str,
    session_id: str = "chat_12345678",
    role: str = "user",
    content: str = "hello",
    created_at: str = "2026-05-15T07:00:00+08:00",
    tool_calls_json: str | None = None,
) -> ChatMessage:
    return ChatMessage(
        id=id,
        session_id=session_id,
        role=role,
        content=content,
        tool_calls_json=tool_calls_json,
        tool_result_for=None,
        llm_cost_id=None,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------


def test_init_schema_is_idempotent() -> None:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    init_schema(c)  # no raise
    cols = c.execute("PRAGMA table_info(chat_sessions)").fetchall()
    assert len(cols) == 6
    cols = c.execute("PRAGMA table_info(chat_messages)").fetchall()
    assert len(cols) == 8


def test_status_check_constraint(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO chat_sessions VALUES (?, ?, ?, ?, ?, ?)",
        ("chat_11111111", "t", "m", "active", "2026-05-15T07:00:00+08:00",
         "2026-05-15T07:00:00+08:00"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO chat_sessions VALUES (?, ?, ?, ?, ?, ?)",
            ("chat_22222222", "t", "m", "archived",
             "2026-05-15T07:00:00+08:00", "2026-05-15T07:00:00+08:00"),
        )


def test_fts5_trigger_insert(conn: sqlite3.Connection) -> None:
    insert_session(conn, _session())
    insert_message(conn, _msg(id="msg_aaaaaaaaaaaa", content="台積電 籌碼分析"))
    hits = conn.execute(
        "SELECT rowid FROM chat_messages_fts WHERE chat_messages_fts MATCH ?",
        ("台積電",),
    ).fetchall()
    assert len(hits) == 1


def test_fts5_trigger_delete(conn: sqlite3.Connection) -> None:
    insert_session(conn, _session())
    insert_message(conn, _msg(id="msg_aaaaaaaaaaaa", content="台積電 籌碼"))
    conn.execute("DELETE FROM chat_messages WHERE id=?", ("msg_aaaaaaaaaaaa",))
    conn.commit()
    hits = conn.execute(
        "SELECT rowid FROM chat_messages_fts WHERE chat_messages_fts MATCH ?",
        ("台積電",),
    ).fetchall()
    assert hits == []


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


def test_list_sessions_orders_by_updated_at_desc(
    conn: sqlite3.Connection,
) -> None:
    insert_session(
        conn, _session(id="chat_aaaaaaaa", updated="2026-05-15T09:00:00+08:00")
    )
    insert_session(
        conn, _session(id="chat_bbbbbbbb", updated="2026-05-15T10:00:00+08:00")
    )
    insert_session(
        conn, _session(id="chat_cccccccc", updated="2026-05-15T11:00:00+08:00")
    )
    items, total = list_sessions(conn, limit=10, offset=0)
    assert [i["id"] for i in items] == ["chat_cccccccc", "chat_bbbbbbbb", "chat_aaaaaaaa"]
    assert total == 3


def test_list_sessions_only_active(conn: sqlite3.Connection) -> None:
    insert_session(conn, _session(id="chat_aaaaaaaa", status="active"))
    insert_session(conn, _session(id="chat_bbbbbbbb", status="deleted"))
    items, total = list_sessions(conn, limit=10, offset=0)
    assert [i["id"] for i in items] == ["chat_aaaaaaaa"]
    assert total == 1


def test_list_sessions_limit_out_of_range(conn: sqlite3.Connection) -> None:
    with pytest.raises(ChatStoreError) as exc_info:
        list_sessions(conn, limit=201, offset=0)
    assert exc_info.value.code == "invalid_input"


def test_list_sessions_negative_offset(conn: sqlite3.Connection) -> None:
    with pytest.raises(ChatStoreError) as exc_info:
        list_sessions(conn, limit=10, offset=-1)
    assert exc_info.value.code == "invalid_input"


def test_list_sessions_message_count(conn: sqlite3.Connection) -> None:
    insert_session(conn, _session())
    insert_message(conn, _msg(id="msg_aaaaaaaaaaaa"))
    insert_message(conn, _msg(id="msg_bbbbbbbbbbbb"))
    items, _ = list_sessions(conn, limit=10, offset=0)
    assert items[0]["message_count"] == 2


def test_get_session_returns_none_for_unknown(
    conn: sqlite3.Connection,
) -> None:
    assert get_session(conn, "chat_aaaaaaaa") is None


def test_soft_delete_unknown_returns_false(
    conn: sqlite3.Connection,
) -> None:
    ok = soft_delete_session(
        conn, "chat_doesnotex", "2026-05-15T07:00:00+08:00"
    )
    assert ok is False


def test_soft_delete_idempotent(conn: sqlite3.Connection) -> None:
    insert_session(conn, _session(id="chat_aaaaaaaa"))
    first = soft_delete_session(
        conn, "chat_aaaaaaaa", "2026-05-15T08:00:00+08:00"
    )
    assert first is True
    # second call should not bump updated_at
    second = soft_delete_session(
        conn, "chat_aaaaaaaa", "2026-05-15T09:00:00+08:00"
    )
    assert second is True
    sess = get_session(conn, "chat_aaaaaaaa")
    assert sess is not None
    assert sess.status == "deleted"
    assert sess.updated_at == "2026-05-15T08:00:00+08:00"


def test_touch_session_updates_updated_at(conn: sqlite3.Connection) -> None:
    insert_session(
        conn,
        _session(id="chat_aaaaaaaa", updated="2026-05-15T07:00:00+08:00"),
    )
    touch_session(conn, "chat_aaaaaaaa", "2026-05-15T08:00:00+08:00")
    sess = get_session(conn, "chat_aaaaaaaa")
    assert sess is not None
    assert sess.updated_at == "2026-05-15T08:00:00+08:00"


def test_update_session_title(conn: sqlite3.Connection) -> None:
    insert_session(conn, _session(id="chat_aaaaaaaa", title="新對話"))
    update_session_title(conn, "chat_aaaaaaaa", "2330 籌碼")
    sess = get_session(conn, "chat_aaaaaaaa")
    assert sess is not None
    assert sess.title == "2330 籌碼"


# ---------------------------------------------------------------------------
# Message CRUD
# ---------------------------------------------------------------------------


def test_select_messages_orders_asc(conn: sqlite3.Connection) -> None:
    insert_session(conn, _session())
    insert_message(
        conn,
        _msg(id="msg_aaaaaaaaaaaa", created_at="2026-05-15T07:00:00+08:00"),
    )
    insert_message(
        conn,
        _msg(id="msg_bbbbbbbbbbbb", created_at="2026-05-15T07:01:00+08:00"),
    )
    msgs = select_messages(conn, "chat_12345678")
    assert [m.id for m in msgs] == ["msg_aaaaaaaaaaaa", "msg_bbbbbbbbbbbb"]


def test_insert_message_bad_tool_calls_json_writes_null(
    conn: sqlite3.Connection,
) -> None:
    insert_session(conn, _session())
    msg = _msg(id="msg_aaaaaaaaaaaa", tool_calls_json="{broken")
    insert_message(conn, msg)  # no raise
    row = conn.execute(
        "SELECT tool_calls_json FROM chat_messages WHERE id=?",
        ("msg_aaaaaaaaaaaa",),
    ).fetchone()
    assert row[0] is None


def test_insert_message_well_formed_tool_calls_json_preserved(
    conn: sqlite3.Connection,
) -> None:
    insert_session(conn, _session())
    msg = _msg(id="msg_aaaaaaaaaaaa", tool_calls_json='[{"id":"t1"}]')
    insert_message(conn, msg)
    row = conn.execute(
        "SELECT tool_calls_json FROM chat_messages WHERE id=?",
        ("msg_aaaaaaaaaaaa",),
    ).fetchone()
    assert row[0] == '[{"id":"t1"}]'


# ---------------------------------------------------------------------------
# FTS5 search
# ---------------------------------------------------------------------------


def test_search_messages_groups_by_session(conn: sqlite3.Connection) -> None:
    insert_session(conn, _session(id="chat_aaaaaaaa", title="A 對話"))
    insert_session(conn, _session(id="chat_bbbbbbbb", title="B 對話"))
    insert_message(
        conn,
        _msg(
            id="msg_aaaaaaaaaaaa",
            session_id="chat_aaaaaaaa",
            content="台積電 籌碼分析",
        ),
    )
    insert_message(
        conn,
        _msg(
            id="msg_bbbbbbbbbbbb",
            session_id="chat_aaaaaaaa",
            content="台積電 月線突破",
        ),
    )
    insert_message(
        conn,
        _msg(
            id="msg_cccccccccccc",
            session_id="chat_bbbbbbbb",
            content="台積電 法人買超",
        ),
    )

    groups = search_messages(conn, q="台積電", limit=20)
    assert {g["session_id"] for g in groups} == {"chat_aaaaaaaa", "chat_bbbbbbbb"}
    by_sid = {g["session_id"]: g for g in groups}
    assert len(by_sid["chat_aaaaaaaa"]["hits"]) == 2
    assert len(by_sid["chat_bbbbbbbb"]["hits"]) == 1
    # snippet should carry highlight markers
    assert "<mark>" in by_sid["chat_aaaaaaaa"]["hits"][0]["snippet"]


def test_search_messages_empty_q_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(ChatStoreError) as exc_info:
        search_messages(conn, q="   ", limit=10)
    assert exc_info.value.code == "invalid_input"


def test_search_messages_fts5_syntax_error_remapped(
    conn: sqlite3.Connection,
) -> None:
    insert_session(conn, _session())
    insert_message(conn, _msg(id="msg_aaaaaaaaaaaa", content="hello"))
    with pytest.raises(ChatStoreError) as exc_info:
        search_messages(conn, q='"unclosed', limit=10)
    assert exc_info.value.code == "invalid_query"
    # MUST NOT leak the underlying SQLite OperationalError text
    err_text = str(exc_info.value)
    assert "OperationalError" not in err_text


def test_search_messages_date_filter(conn: sqlite3.Connection) -> None:
    insert_session(conn, _session())
    insert_message(
        conn,
        _msg(
            id="msg_aaaaaaaaaaaa",
            content="台積電 早盤",
            created_at="2026-05-14T08:00:00+08:00",
        ),
    )
    insert_message(
        conn,
        _msg(
            id="msg_bbbbbbbbbbbb",
            content="台積電 收盤",
            created_at="2026-05-15T13:30:00+08:00",
        ),
    )
    insert_message(
        conn,
        _msg(
            id="msg_cccccccccccc",
            content="台積電 隔日",
            created_at="2026-05-16T09:00:00+08:00",
        ),
    )
    groups = search_messages(
        conn,
        q="台積電",
        date_from="2026-05-15",
        date_to="2026-05-15",
        limit=20,
    )
    hits = groups[0]["hits"]
    msg_ids = [h["message_id"] for h in hits]
    assert msg_ids == ["msg_bbbbbbbbbbbb"]


def test_search_messages_date_from_after_date_to_raises(
    conn: sqlite3.Connection,
) -> None:
    with pytest.raises(ChatStoreError) as exc_info:
        search_messages(
            conn,
            q="x",
            date_from="2026-05-16",
            date_to="2026-05-15",
            limit=20,
        )
    assert exc_info.value.code == "invalid_input"


def test_search_messages_includes_deleted_sessions(
    conn: sqlite3.Connection,
) -> None:
    insert_session(conn, _session(id="chat_aaaaaaaa", status="deleted"))
    insert_message(
        conn,
        _msg(id="msg_aaaaaaaaaaaa", session_id="chat_aaaaaaaa", content="hit"),
    )
    groups = search_messages(conn, q="hit", limit=10)
    assert groups[0]["session_status"] == "deleted"
