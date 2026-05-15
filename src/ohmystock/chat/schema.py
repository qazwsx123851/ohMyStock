"""Frozen pydantic models for chat sessions and messages.

Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/chat-store/spec.md

`ChatSession` and `ChatMessage` are the system-of-record models for the
admin chat surface. Both are ``frozen=True, extra="forbid"`` so callers
either pass exactly the right fields or fail loudly at construction.

ID formats are enforced by regex:
  * session id  -> ``chat_<8hex>``  (8 hex chars after the prefix)
  * message id  -> ``msg_<12hex>`` (12 hex chars after the prefix)

These line up with the storage layer's ``secrets.token_hex(4)`` /
``secrets.token_hex(6)`` allocations and with the FTS5 trigger logic
in ``ohmystock.chat.storage``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# Type aliases keep the regex patterns in one place and let other modules
# reuse them when validating route params / SSE payloads.
SESSION_ID_PATTERN = r"^chat_[0-9a-f]{8}$"
MESSAGE_ID_PATTERN = r"^msg_[0-9a-f]{12}$"


class ChatSession(BaseModel):
    """A conversation thread between Mark and the chat agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=SESSION_ID_PATTERN)
    title: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1)
    status: Literal["active", "deleted"]
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class ChatMessage(BaseModel):
    """A single message in a chat session.

    ``content`` may be empty (e.g., partial commit after streaming was
    cancelled mid-tool-call); the storage layer is append-only and we
    prefer to preserve the partial record over discarding it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=MESSAGE_ID_PATTERN)
    session_id: str = Field(pattern=SESSION_ID_PATTERN)
    role: Literal["user", "assistant", "tool_result"]
    content: str
    tool_calls_json: str | None = None
    tool_result_for: str | None = None
    llm_cost_id: str | None = None
    created_at: str = Field(min_length=1)
