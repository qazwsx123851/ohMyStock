"""Public surface of the chat subsystem.

Storage helpers, agent runtime, and tool registry are layered on top of the
frozen pydantic models in :mod:`ohmystock.chat.schema`. Each later module
re-uses these types; the package ``__all__`` therefore only exposes what
external callers (API routes, tests) legitimately need.

Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/
"""

from __future__ import annotations

from ohmystock.chat.schema import (
    MESSAGE_ID_PATTERN,
    SESSION_ID_PATTERN,
    ChatMessage,
    ChatSession,
)
from ohmystock.chat.storage import (
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


__all__ = [
    "ChatMessage",
    "ChatSession",
    "ChatStoreError",
    "MESSAGE_ID_PATTERN",
    "SESSION_ID_PATTERN",
    "get_session",
    "init_schema",
    "insert_message",
    "insert_session",
    "list_sessions",
    "search_messages",
    "select_messages",
    "soft_delete_session",
    "touch_session",
    "update_session_title",
]
