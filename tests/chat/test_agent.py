"""ChatAgent streaming runtime tests.

Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/chat-agent-runtime/spec.md
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from typing import Any

import pytest

from ohmystock.chat import ChatMessage
from ohmystock.chat.agent import ChatAgent
from ohmystock.chat.tools import ToolHandler, QueryJournalArgs
from ohmystock.journal.schema import init_schema as init_journal_schema


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _msg(role: str, content: str, idx: int = 0) -> ChatMessage:
    return ChatMessage(
        id=f"msg_{idx:012x}",
        session_id="chat_12345678",
        role=role,
        content=content,
        tool_calls_json=None,
        tool_result_for=None,
        llm_cost_id=None,
        created_at=f"2026-05-15T07:00:{idx:02d}+08:00",
    )


def _content_text(text: str) -> Any:
    return SimpleNamespace(type="text", text=text)


def _content_tool_use(*, tu_id: str, name: str, input_: dict) -> Any:
    return SimpleNamespace(
        type="tool_use", id=tu_id, name=name, input=input_
    )


def _response(
    content: list[Any],
    *,
    stop_reason: str = "end_turn",
    input_tokens: int = 10,
    output_tokens: int = 20,
) -> Any:
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=input_tokens, output_tokens=output_tokens
        ),
    )


class FakeMessages:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:  # noqa: ANN401
        self.calls.append(kwargs)
        if not self._responses:
            raise RuntimeError("no more fake responses")
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.messages = FakeMessages(responses)


class RaisingMessages:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    def create(self, **kwargs: Any) -> Any:  # noqa: ANN401
        self.calls += 1
        raise self.exc


class RaisingClient:
    def __init__(self, exc: Exception) -> None:
        self.messages = RaisingMessages(exc)


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_journal_schema(c)
    return c


def _stub_tools() -> list[ToolHandler]:
    return [
        ToolHandler(
            name="query_journal",
            description="stub",
            args_model=QueryJournalArgs,
            handler=lambda args, conn: {"rows": [], "total": 0},
        )
    ]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_simple_text_response_emits_delta_then_done(
    conn: sqlite3.Connection,
) -> None:
    client = FakeClient([_response([_content_text("台積電上漲了。")])])
    agent = ChatAgent(
        model="claude-sonnet-4-6",
        tools=_stub_tools(),
        anthropic_client=client,
        conn=conn,
    )
    events = [e async for e in agent.stream([_msg("user", "問問")])]
    types = [e["event"] for e in events]
    assert types[0] == "delta"
    assert types[-1] == "done"
    assert all(t in {"delta", "done"} for t in types)
    full = "".join(e["text"] for e in events if e["event"] == "delta")
    assert full == "台積電上漲了。"


async def test_done_event_writes_llm_costs_row(
    conn: sqlite3.Connection,
) -> None:
    client = FakeClient(
        [_response([_content_text("ok")], input_tokens=5, output_tokens=15)]
    )
    agent = ChatAgent(
        model="claude-sonnet-4-6",
        tools=_stub_tools(),
        anthropic_client=client,
        conn=conn,
    )
    events = [e async for e in agent.stream([_msg("user", "問")])]
    done = [e for e in events if e["event"] == "done"][0]
    rows = conn.execute(
        "SELECT decision_id, model, input_tokens, output_tokens FROM llm_costs"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0].startswith("chat:msg_")
    assert rows[0][1] == "claude-sonnet-4-6"
    assert rows[0][2] == 5
    assert rows[0][3] == 15
    assert done["cost_usd"] > 0


# ---------------------------------------------------------------------------
# Tool use loop
# ---------------------------------------------------------------------------


async def test_tool_use_flow_emits_call_and_result(
    conn: sqlite3.Connection,
) -> None:
    first = _response(
        [
            _content_tool_use(
                tu_id="tool_1", name="query_journal", input_={"symbol": "2330"}
            )
        ],
        stop_reason="tool_use",
    )
    final = _response(
        [_content_text("查到了，沒有相關紀錄。")], stop_reason="end_turn"
    )
    client = FakeClient([first, final])
    agent = ChatAgent(
        model="claude-sonnet-4-6",
        tools=_stub_tools(),
        anthropic_client=client,
        conn=conn,
    )
    events = [e async for e in agent.stream([_msg("user", "查 2330")])]
    types = [e["event"] for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    tc = [e for e in events if e["event"] == "tool_call"][0]
    assert tc["name"] == "query_journal"
    tr = [e for e in events if e["event"] == "tool_result"][0]
    assert tr["result"] == {"rows": [], "total": 0}
    assert events[-1]["event"] == "done"


# ---------------------------------------------------------------------------
# History trimming
# ---------------------------------------------------------------------------


async def test_max_history_truncates_messages_sent(
    conn: sqlite3.Connection,
) -> None:
    client = FakeClient([_response([_content_text("ok")])])
    agent = ChatAgent(
        model="claude-sonnet-4-6",
        tools=_stub_tools(),
        anthropic_client=client,
        conn=conn,
        max_history=3,
    )
    history = [_msg("user", f"msg-{i}", idx=i) for i in range(10)]
    _ = [e async for e in agent.stream(history)]
    sent = client.messages.calls[0]["messages"]
    assert len(sent) == 3
    # Last three messages preserved
    assert sent[-1]["content"] == "msg-9"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class FakeRateLimitError(Exception):
    pass


async def test_anthropic_exception_emits_error_event_not_raise(
    conn: sqlite3.Connection,
) -> None:
    client = RaisingClient(FakeRateLimitError("slow down"))
    agent = ChatAgent(
        model="claude-sonnet-4-6",
        tools=_stub_tools(),
        anthropic_client=client,
        conn=conn,
    )
    events = [e async for e in agent.stream([_msg("user", "hi")])]
    assert len(events) == 1
    err = events[0]
    assert err["event"] == "error"
    assert err["code"] == "rate_limit"
    # No llm_costs row was written
    n = conn.execute("SELECT COUNT(*) FROM llm_costs").fetchone()[0]
    assert n == 0
