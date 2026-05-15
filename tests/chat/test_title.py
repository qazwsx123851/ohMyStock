"""autogen_title fail-safe tests.

Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/chat-agent-runtime/spec.md
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ohmystock.chat import ChatMessage
from ohmystock.chat.title import FALLBACK_TITLE, autogen_title


pytestmark = pytest.mark.asyncio


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


def _ok_response(text: str) -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)]
    )


class FakeClient:
    def __init__(
        self,
        response: Any | None = None,
        exc: Exception | None = None,
        sleep_seconds: float = 0.0,
    ) -> None:
        self.response = response
        self.exc = exc
        self.sleep_seconds = sleep_seconds
        self.messages = self

    def create(self, **kwargs: Any) -> Any:  # noqa: ANN401
        import time

        if self.sleep_seconds:
            time.sleep(self.sleep_seconds)
        if self.exc is not None:
            raise self.exc
        return self.response


async def test_happy_path_returns_summary() -> None:
    client = FakeClient(_ok_response("2330 籌碼分析"))
    title = await autogen_title(
        [_msg("user", "今天 2330 籌碼怎樣？")],
        model="claude-haiku-4-5",
        anthropic_client=client,
    )
    assert title == "2330 籌碼分析"


async def test_api_exception_returns_fallback() -> None:
    client = FakeClient(exc=RuntimeError("API down"))
    title = await autogen_title(
        [_msg("user", "hi")],
        model="claude-haiku-4-5",
        anthropic_client=client,
    )
    assert title == FALLBACK_TITLE


async def test_timeout_returns_fallback() -> None:
    client = FakeClient(_ok_response("late"), sleep_seconds=0.3)
    title = await autogen_title(
        [_msg("user", "hi")],
        model="claude-haiku-4-5",
        anthropic_client=client,
        timeout_seconds=0.05,
    )
    assert title == FALLBACK_TITLE


async def test_empty_response_returns_fallback() -> None:
    client = FakeClient(_ok_response(""))
    title = await autogen_title(
        [_msg("user", "hi")],
        model="claude-haiku-4-5",
        anthropic_client=client,
    )
    assert title == FALLBACK_TITLE


async def test_response_truncated_to_16_codepoints() -> None:
    client = FakeClient(_ok_response("這是一個非常非常非常非常非常長的標題不可能放下"))
    title = await autogen_title(
        [_msg("user", "hi")],
        model="claude-haiku-4-5",
        anthropic_client=client,
    )
    assert len(title) <= 16


async def test_no_messages_returns_fallback() -> None:
    client = FakeClient(_ok_response("anything"))
    title = await autogen_title(
        [], model="claude-haiku-4-5", anthropic_client=client
    )
    assert title == FALLBACK_TITLE
