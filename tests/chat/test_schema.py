"""Schema tests for chat sessions and messages.

Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/chat-store/spec.md
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ohmystock.chat import ChatMessage, ChatSession


VALID_SESSION_KWARGS = dict(
    id="chat_12345678",
    title="x",
    model="m",
    status="active",
    created_at="2026-05-15T07:00:00+08:00",
    updated_at="2026-05-15T07:00:00+08:00",
)


VALID_MESSAGE_KWARGS = dict(
    id="msg_abc123def456",
    session_id="chat_12345678",
    role="user",
    content="hello",
    tool_calls_json=None,
    tool_result_for=None,
    llm_cost_id=None,
    created_at="2026-05-15T07:00:00+08:00",
)


def test_chat_session_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        ChatSession(**VALID_SESSION_KWARGS, extra="boom")  # type: ignore[arg-type]


def test_chat_session_accepts_valid_kwargs() -> None:
    s = ChatSession(**VALID_SESSION_KWARGS)
    assert s.id == "chat_12345678"
    assert s.status == "active"


def test_chat_session_is_frozen() -> None:
    s = ChatSession(**VALID_SESSION_KWARGS)
    with pytest.raises(ValidationError):
        s.title = "new"  # type: ignore[misc]


def test_chat_session_rejects_bad_id_format() -> None:
    bad = {**VALID_SESSION_KWARGS, "id": "session_12345678"}
    with pytest.raises(ValidationError):
        ChatSession(**bad)


def test_chat_session_rejects_short_id() -> None:
    bad = {**VALID_SESSION_KWARGS, "id": "chat_1234"}
    with pytest.raises(ValidationError):
        ChatSession(**bad)


def test_chat_session_rejects_unknown_status() -> None:
    bad = {**VALID_SESSION_KWARGS, "status": "archived"}
    with pytest.raises(ValidationError):
        ChatSession(**bad)


def test_chat_message_rejects_bad_id_format() -> None:
    bad = {**VALID_MESSAGE_KWARGS, "id": "not_a_valid_id"}
    with pytest.raises(ValidationError):
        ChatMessage(**bad)


def test_chat_message_rejects_bad_session_id_format() -> None:
    bad = {**VALID_MESSAGE_KWARGS, "session_id": "session_12345678"}
    with pytest.raises(ValidationError):
        ChatMessage(**bad)


def test_chat_message_rejects_unknown_role() -> None:
    bad = {**VALID_MESSAGE_KWARGS, "role": "system"}
    with pytest.raises(ValidationError):
        ChatMessage(**bad)


def test_chat_message_accepts_empty_content_for_partial_commit() -> None:
    msg = ChatMessage(**{**VALID_MESSAGE_KWARGS, "content": ""})
    assert msg.content == ""


def test_chat_message_tool_calls_json_optional() -> None:
    msg = ChatMessage(
        **{**VALID_MESSAGE_KWARGS, "tool_calls_json": '[{"id":"t1"}]'}
    )
    assert msg.tool_calls_json == '[{"id":"t1"}]'
