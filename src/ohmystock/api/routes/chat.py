"""``/api/admin/chat/*`` — Bearer-auth chat endpoints.

Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/admin-chat-endpoints/spec.md

Endpoints:

* ``GET    /sessions``                 — paginated active session list
* ``POST   /sessions``                 — create empty session
* ``GET    /sessions/{id}``            — session + last 200 messages
* ``POST   /sessions/{id}/messages``   — append user message, stream assistant
* ``DELETE /sessions/{id}``            — idempotent soft delete
* ``GET    /search``                   — FTS5 cross-session search

All routes use the shared ``{ok, data, error}`` envelope. The streaming
POST endpoint is the only exception: a successful response is
``text/event-stream`` framed as ``event: <kind>\\ndata: <json>\\n\\n``.
Pre-stream validation errors still come back as the JSON envelope so
the client can distinguish "no stream available" from "stream
terminated early".
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from anthropic import Anthropic
from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ohmystock.api.auth import require_admin
from ohmystock.api.routes._deps import get_db, get_settings_dep
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_error,
    to_success,
)
from ohmystock.chat import (
    ChatMessage,
    ChatSession,
    ChatStoreError,
    get_session,
    insert_message,
    insert_session,
    list_sessions,
    search_messages,
    select_messages,
    soft_delete_session,
    touch_session,
    update_session_title,
)
from ohmystock.chat.agent import ChatAgent
from ohmystock.chat.title import FALLBACK_TITLE, autogen_title
from ohmystock.config import Settings


router = APIRouter(dependencies=[Depends(require_admin)])


# ---------------------------------------------------------------------------
# Constants & test seams
# ---------------------------------------------------------------------------

_TPE = timezone(timedelta(hours=8))
_INVALID_NAME_TOKENS: tuple[str, ...] = ("/", "\\", "..", os.sep)

_SESSIONS_LIST_MAX = 200
_SESSIONS_LIST_DEFAULT = 50
_SEARCH_LIMIT_MAX = 100
_SEARCH_LIMIT_DEFAULT = 20
_MESSAGES_PER_SESSION_MAX = 200


def _anthropic_client_factory(api_key: str) -> Any:
    """Indirection so tests can monkeypatch
    ``routes.chat._anthropic_client_factory`` without touching SDK imports."""

    return Anthropic(api_key=api_key)


_ANTHROPIC_CLIENT_FACTORY = _anthropic_client_factory


def _now_iso() -> str:
    return datetime.now(_TPE).isoformat()


def _new_session_id() -> str:
    return "chat_" + secrets.token_hex(4)


def _new_message_id() -> str:
    return "msg_" + secrets.token_hex(6)


def _reject_path_traversal(value: str) -> JSONResponse | None:
    """Return a 400 envelope if ``value`` contains a path-traversal token."""

    for bad in _INVALID_NAME_TOKENS:
        if bad in value:
            return JSONResponse(
                status_code=400,
                content=to_error(
                    "invalid_input",
                    f"path-traversal token {bad!r} in id",
                ),
            )
    return None


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ChatSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=120)
    model: str | None = Field(default=None, min_length=1)


class ChatMessageSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summary_from_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Project a storage row dict to the public ``ChatSessionSummary`` shape."""

    return {
        "id": row["id"],
        "title": row["title"],
        "model": row["model"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "message_count": int(row.get("message_count", 0)),
    }


def _summary_from_session(
    session: ChatSession, message_count: int
) -> dict[str, Any]:
    return {
        "id": session.id,
        "title": session.title,
        "model": session.model,
        "status": session.status,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "message_count": message_count,
    }


def _message_to_json(msg: ChatMessage) -> dict[str, Any]:
    return {
        "id": msg.id,
        "session_id": msg.session_id,
        "role": msg.role,
        "content": msg.content,
        "tool_calls_json": msg.tool_calls_json,
        "tool_result_for": msg.tool_result_for,
        "llm_cost_id": msg.llm_cost_id,
        "created_at": msg.created_at,
    }


def _format_sse(event: str, data: dict[str, Any]) -> bytes:
    body = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {body}\n\n".encode("utf-8")


# ---------------------------------------------------------------------------
# GET /api/admin/chat/sessions — list
# ---------------------------------------------------------------------------


@router.get("/api/admin/chat/sessions")
def get_chat_sessions(
    limit: int = Query(default=_SESSIONS_LIST_DEFAULT),
    offset: int = Query(default=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    try:
        items, total = list_sessions(
            conn, limit=limit, offset=offset, status="active"
        )
    except ChatStoreError as exc:
        return JSONResponse(
            status_code=400,
            content=to_error(exc.code, exc.message or exc.code),
        )
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    has_more = offset + len(items) < total
    return JSONResponse(
        status_code=200,
        content=to_success(
            {
                "items": [_summary_from_dict(it) for it in items],
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
            }
        ),
    )


# ---------------------------------------------------------------------------
# POST /api/admin/chat/sessions — create
# ---------------------------------------------------------------------------


@router.post("/api/admin/chat/sessions")
def create_chat_session(
    body: ChatSessionCreateRequest,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:
    try:
        now = _now_iso()
        session = ChatSession(
            id=_new_session_id(),
            title=body.title or FALLBACK_TITLE,
            model=body.model or settings.ohmystock_chat_model_default,
            status="active",
            created_at=now,
            updated_at=now,
        )
        insert_session(conn, session)
    except Exception as exc:  # noqa: BLE001
        status, env = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=env)

    return JSONResponse(
        status_code=200,
        content=to_success(_summary_from_session(session, message_count=0)),
    )


# ---------------------------------------------------------------------------
# GET /api/admin/chat/sessions/{id} — fetch
# ---------------------------------------------------------------------------


@router.get("/api/admin/chat/sessions/{session_id:path}")
def get_chat_session_detail(
    session_id: str = Path(...),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    rejection = _reject_path_traversal(session_id)
    if rejection is not None:
        return rejection

    try:
        session = get_session(conn, session_id)
    except Exception as exc:  # noqa: BLE001
        status, env = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=env)

    if session is None:
        return JSONResponse(
            status_code=404,
            content=to_error(
                "not_found", f"chat session not found: {session_id}"
            ),
        )

    if session.status == "deleted":
        return JSONResponse(
            status_code=422,
            content=to_error(
                "session_deleted", f"chat session deleted: {session_id}"
            ),
        )

    try:
        msgs = select_messages(
            conn, session_id, limit=_MESSAGES_PER_SESSION_MAX
        )
    except ChatStoreError as exc:
        return JSONResponse(
            status_code=400,
            content=to_error(exc.code, exc.message or exc.code),
        )

    return JSONResponse(
        status_code=200,
        content=to_success(
            {
                "session": _summary_from_session(
                    session, message_count=len(msgs)
                ),
                "messages": [_message_to_json(m) for m in msgs],
            }
        ),
    )


# ---------------------------------------------------------------------------
# DELETE /api/admin/chat/sessions/{id} — soft delete
# ---------------------------------------------------------------------------


@router.delete("/api/admin/chat/sessions/{session_id:path}")
def delete_chat_session(
    session_id: str = Path(...),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    rejection = _reject_path_traversal(session_id)
    if rejection is not None:
        return rejection

    try:
        ok = soft_delete_session(conn, session_id, _now_iso())
    except Exception as exc:  # noqa: BLE001
        status, env = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=env)

    if not ok:
        return JSONResponse(
            status_code=404,
            content=to_error(
                "not_found", f"chat session not found: {session_id}"
            ),
        )

    return JSONResponse(status_code=200, content=to_success({"deleted": True}))


# ---------------------------------------------------------------------------
# POST /api/admin/chat/sessions/{id}/messages — streaming
# ---------------------------------------------------------------------------


@router.post("/api/admin/chat/sessions/{session_id:path}/messages")
async def send_chat_message(
    body: ChatMessageSendRequest,
    request: Request,
    session_id: str = Path(...),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> Any:
    rejection = _reject_path_traversal(session_id)
    if rejection is not None:
        return rejection

    session = get_session(conn, session_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content=to_error(
                "not_found", f"chat session not found: {session_id}"
            ),
        )
    if session.status == "deleted":
        return JSONResponse(
            status_code=422,
            content=to_error(
                "session_deleted", f"chat session deleted: {session_id}"
            ),
        )

    api_key = (settings.anthropic_api_key or "").strip()
    if not api_key:
        return JSONResponse(
            status_code=422,
            content=to_error(
                "missing_api_key", "ANTHROPIC_API_KEY is not configured"
            ),
        )

    # Persist the user message BEFORE the stream starts so it's visible on
    # reload even if the assistant turn aborts.
    user_msg = ChatMessage(
        id=_new_message_id(),
        session_id=session_id,
        role="user",
        content=body.content,
        tool_calls_json=None,
        tool_result_for=None,
        llm_cost_id=None,
        created_at=_now_iso(),
    )
    insert_message(conn, user_msg)
    touch_session(conn, session_id, user_msg.created_at)

    history = select_messages(
        conn, session_id, limit=_MESSAGES_PER_SESSION_MAX
    )

    client = _ANTHROPIC_CLIENT_FACTORY(api_key)
    agent = ChatAgent(
        model=session.model,
        anthropic_client=client,
        conn=conn,
    )

    assistant_partial_text: list[str] = []
    assistant_tool_calls: list[dict[str, Any]] = []
    final_event: dict[str, Any] | None = None
    cancelled = False

    async def event_stream() -> AsyncIterator[bytes]:
        nonlocal final_event, cancelled

        try:
            async for ev in agent.stream(history):
                if await request.is_disconnected():
                    cancelled = True
                    break
                if ev["event"] == "delta":
                    assistant_partial_text.append(ev.get("text", ""))
                elif ev["event"] == "tool_call":
                    assistant_tool_calls.append(
                        {
                            "id": ev.get("id", ""),
                            "name": ev.get("name", ""),
                            "args": ev.get("args", {}),
                        }
                    )
                elif ev["event"] == "done":
                    final_event = ev
                yield _format_sse(ev["event"], _strip_internal_fields(ev))
                if ev["event"] in {"error", "done"}:
                    break
        finally:
            _commit_assistant_turn(
                conn,
                session_id=session_id,
                final_event=final_event,
                partial_text="".join(assistant_partial_text),
                tool_calls=assistant_tool_calls,
                cancelled=cancelled,
                title_model=settings.ohmystock_chat_title_model,
                anthropic_client=client,
            )

    return StreamingResponse(
        event_stream(), media_type="text/event-stream"
    )


def _strip_internal_fields(ev: dict[str, Any]) -> dict[str, Any]:
    """Remove server-internal fields from a ``done`` event before SSE."""

    if ev.get("event") != "done":
        # delta/tool_call/tool_result/error — drop the discriminator only.
        return {k: v for k, v in ev.items() if k != "event"}
    return {
        "message_id": ev.get("message_id"),
        "elapsed_ms": ev.get("elapsed_ms"),
        "input_tokens": ev.get("input_tokens"),
        "output_tokens": ev.get("output_tokens"),
        "cost_usd": ev.get("cost_usd"),
    }


def _commit_assistant_turn(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    final_event: dict[str, Any] | None,
    partial_text: str,
    tool_calls: list[dict[str, Any]],
    cancelled: bool,
    title_model: str,
    anthropic_client: Any,
) -> None:
    """Persist the assistant message row when the stream ends or is aborted.

    Handles three cases:

    * happy path — ``final_event`` is a ``done`` event with the full text
      and tool-call manifest; we trust those.
    * cancel — ``cancelled=True``; we save what we accumulated and tag the
      content with ``[訊息已中斷]`` so the user sees what happened.
    * error event — ``final_event`` is None; we save partial text only if
      there was any.
    """

    has_content = bool(partial_text.strip()) or bool(tool_calls)
    if not (final_event or has_content):
        return  # error before any text — nothing to persist

    if final_event is not None:
        msg_id = final_event.get("message_id") or _new_message_id()
        content = final_event.get("assistant_text") or partial_text
        tool_calls_payload = final_event.get("tool_calls") or tool_calls
        llm_cost_id = final_event.get("llm_cost_id")
    else:
        msg_id = _new_message_id()
        content = partial_text
        tool_calls_payload = tool_calls
        llm_cost_id = None

    if cancelled:
        content = (content or "") + "\n\n[訊息已中斷]"

    try:
        tool_calls_json = (
            json.dumps(tool_calls_payload, ensure_ascii=False)
            if tool_calls_payload
            else None
        )
    except (TypeError, ValueError):
        tool_calls_json = None

    try:
        assistant_msg = ChatMessage(
            id=msg_id,
            session_id=session_id,
            role="assistant",
            content=content,
            tool_calls_json=tool_calls_json,
            tool_result_for=None,
            llm_cost_id=str(llm_cost_id) if llm_cost_id is not None else None,
            created_at=_now_iso(),
        )
    except Exception:  # noqa: BLE001 — best effort
        return

    insert_message(conn, assistant_msg)
    touch_session(conn, session_id, assistant_msg.created_at)

    # Fire-and-forget title autogen — only when the session still has the
    # default title and we have a finished assistant turn.
    sess = get_session(conn, session_id)
    if (
        sess is not None
        and sess.status == "active"
        and sess.title == FALLBACK_TITLE
        and final_event is not None
        and not cancelled
    ):
        history = select_messages(
            conn, session_id, limit=_MESSAGES_PER_SESSION_MAX
        )
        try:
            asyncio.get_running_loop().create_task(
                _update_title_in_background(
                    conn=conn,
                    session_id=session_id,
                    history=history,
                    model=title_model,
                    anthropic_client=anthropic_client,
                )
            )
        except RuntimeError:
            # No running loop (test code path) — skip silently.
            pass


async def _update_title_in_background(
    *,
    conn: sqlite3.Connection,
    session_id: str,
    history: list[ChatMessage],
    model: str,
    anthropic_client: Any,
) -> None:
    title = await autogen_title(
        history, model=model, anthropic_client=anthropic_client
    )
    if title and title != FALLBACK_TITLE:
        update_session_title(conn, session_id, title)


# ---------------------------------------------------------------------------
# GET /api/admin/chat/search
# ---------------------------------------------------------------------------


@router.get("/api/admin/chat/search")
def search_chat(
    q: str = Query(..., min_length=1, max_length=200),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=_SEARCH_LIMIT_DEFAULT),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    if limit < 1 or limit > _SEARCH_LIMIT_MAX:
        return JSONResponse(
            status_code=400,
            content=to_error(
                "invalid_input",
                f"limit must be in 1..{_SEARCH_LIMIT_MAX}, got {limit}",
            ),
        )

    try:
        groups = search_messages(
            conn,
            q=q,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
    except ChatStoreError as exc:
        if exc.code == "invalid_input":
            return JSONResponse(
                status_code=400,
                content=to_error(
                    "invalid_input", exc.message or "invalid input"
                ),
            )
        if exc.code == "invalid_query":
            return JSONResponse(
                status_code=400,
                content=to_error(
                    "invalid_query", "FTS5 query syntax error"
                ),
            )
        status, env = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=env)
    except Exception as exc:  # noqa: BLE001
        status, env = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=env)

    total_hits = sum(len(g["hits"]) for g in groups)
    return JSONResponse(
        status_code=200,
        content=to_success({"groups": groups, "total_hits": total_hits}),
    )
