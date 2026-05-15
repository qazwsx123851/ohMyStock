"""Chat tool wrapper + dispatcher tests.

Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/chat-agent-runtime/spec.md
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from ohmystock.chat.tools import (
    BUILTIN_TOOLS,
    QueryJournalArgs,
    ToolHandler,
    dispatch_tool,
)
from ohmystock.journal.schema import init_schema as init_journal_schema
from ohmystock.memory import init_schema as init_memory_schema


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_journal_schema(c)
    init_memory_schema(c)
    return c


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


def test_builtin_tools_exact_set() -> None:
    assert {t.name for t in BUILTIN_TOOLS} == {
        "query_journal",
        "search_memory",
        "get_market_symbol",
        "list_skills",
    }


def test_each_tool_uses_frozen_extra_forbid() -> None:
    for tool in BUILTIN_TOOLS:
        cfg = tool.args_model.model_config
        # Pydantic v2 stores both flags on model_config.
        assert cfg.get("frozen") is True, tool.name
        assert cfg.get("extra") == "forbid", tool.name


# ---------------------------------------------------------------------------
# query_journal
# ---------------------------------------------------------------------------


def _insert_journal_row(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    kind: str,
    symbol: str,
    created_at: str,
    payload: dict,
) -> None:
    conn.execute(
        "INSERT INTO journal_entries (decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (decision_id, kind, symbol, created_at, json.dumps(payload)),
    )
    conn.commit()


def test_query_journal_filters_by_symbol(conn: sqlite3.Connection) -> None:
    _insert_journal_row(
        conn,
        decision_id="dec-1",
        kind="entry",
        symbol="2330",
        created_at="2026-05-14T09:00:00+08:00",
        payload={"actual_entry_price": 1000},
    )
    _insert_journal_row(
        conn,
        decision_id="dec-2",
        kind="entry",
        symbol="2454",
        created_at="2026-05-14T09:00:00+08:00",
        payload={"actual_entry_price": 500},
    )
    out = dispatch_tool("query_journal", {"symbol": "2330"}, conn)
    assert out["total"] == 1
    assert out["rows"][0]["symbol"] == "2330"


def test_query_journal_limit_clamp_via_pydantic(
    conn: sqlite3.Connection,
) -> None:
    out = dispatch_tool("query_journal", {"limit": 999}, conn)
    # 999 exceeds the pydantic upper bound -> invalid_args from dispatcher.
    assert "error" in out
    assert out["error"].startswith("invalid_args")


def test_query_journal_invalid_status(conn: sqlite3.Connection) -> None:
    out = dispatch_tool("query_journal", {"status": "weird"}, conn)
    assert out["error"].startswith("invalid_status")


def test_query_journal_inverted_date_range(conn: sqlite3.Connection) -> None:
    out = dispatch_tool(
        "query_journal",
        {"date_from": "2026-05-15", "date_to": "2026-05-01"},
        conn,
    )
    assert out["error"].startswith("invalid_input")


# ---------------------------------------------------------------------------
# search_memory
# ---------------------------------------------------------------------------


def test_search_memory_fts(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO memory_rows (kind, content, tags, source, created_at) "
        "VALUES ('lesson', '台積電 籌碼分析心得', '[\"twse\"]', NULL, ?)",
        ("2026-05-14T09:00:00+08:00",),
    )
    conn.commit()
    out = dispatch_tool("search_memory", {"q": "台積電"}, conn)
    assert out["total"] == 1
    assert out["rows"][0]["content"].startswith("台積電")


def test_search_memory_list_fallback(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO memory_rows (kind, content, tags, source, created_at) "
        "VALUES ('lesson', 'A', '[]', NULL, ?)",
        ("2026-05-14T09:00:00+08:00",),
    )
    conn.execute(
        "INSERT INTO memory_rows (kind, content, tags, source, created_at) "
        "VALUES ('note', 'B', '[]', NULL, ?)",
        ("2026-05-14T10:00:00+08:00",),
    )
    conn.commit()
    out = dispatch_tool("search_memory", {"q": "", "limit": 10}, conn)
    assert out["total"] == 2


def test_search_memory_invalid_kind(conn: sqlite3.Connection) -> None:
    out = dispatch_tool("search_memory", {"kind": "weird"}, conn)
    assert out["error"].startswith("invalid_kind")


# ---------------------------------------------------------------------------
# get_market_symbol
# ---------------------------------------------------------------------------


def test_get_market_symbol_not_found(conn: sqlite3.Connection) -> None:
    out = dispatch_tool(
        "get_market_symbol", {"symbol": "9999", "days": 5}, conn
    )
    assert out["error"].startswith("not_found")


def test_get_market_symbol_days_out_of_range(
    conn: sqlite3.Connection,
) -> None:
    out = dispatch_tool(
        "get_market_symbol", {"symbol": "2330", "days": 999}, conn
    )
    assert out["error"].startswith("invalid_args")


# ---------------------------------------------------------------------------
# list_skills
# ---------------------------------------------------------------------------


def test_list_skills_returns_rows(conn: sqlite3.Connection) -> None:
    out = dispatch_tool("list_skills", {}, conn)
    assert "rows" in out
    assert isinstance(out["rows"], list)
    # body MUST NOT leak through
    for row in out["rows"]:
        assert "body" not in row


def test_list_skills_filter_unknown_category(
    conn: sqlite3.Connection,
) -> None:
    out = dispatch_tool(
        "list_skills", {"category": "definitely-not-real"}, conn
    )
    assert out["total"] == 0
    assert out["rows"] == []


# ---------------------------------------------------------------------------
# Dispatcher safety
# ---------------------------------------------------------------------------


def test_unknown_tool_name(conn: sqlite3.Connection) -> None:
    out = dispatch_tool("screener_run", {}, conn)
    assert out == {"error": "unknown_tool: screener_run"}


def test_invalid_args_unknown_field(conn: sqlite3.Connection) -> None:
    out = dispatch_tool("query_journal", {"hax": True}, conn)
    assert out["error"].startswith("invalid_args")


def test_handler_exception_caught(conn: sqlite3.Connection) -> None:
    def boom(args, c):
        raise sqlite3.OperationalError("db locked")

    custom = [
        ToolHandler(
            name="boom",
            description="explodes",
            args_model=QueryJournalArgs,
            handler=boom,
        )
    ]
    out = dispatch_tool("boom", {}, conn, tools=custom)
    assert out["error"].startswith("tool_failed: OperationalError")
