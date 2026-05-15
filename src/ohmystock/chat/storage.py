"""SQLite + FTS5 storage layer for chat sessions and messages.

Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/chat-store/spec.md

Public surface (re-exported by ``ohmystock.chat.__init__``):

* ``init_schema(conn)`` — idempotent DDL bootstrap (tables, index, FTS5,
  triggers). Raises ``RuntimeError`` containing ``"FTS5"`` if the SQLite
  build lacks the FTS5 module.
* ``insert_session`` / ``list_sessions`` / ``get_session`` /
  ``soft_delete_session`` — session-level CRUD. ``soft_delete_session`` is
  idempotent over already-deleted sessions and returns ``False`` for
  unknown ids.
* ``insert_message`` / ``select_messages`` — append-only message log per
  session. Messages are never edited or hard-deleted.
* ``search_messages`` — FTS5 BM25 search across all messages (across both
  active and soft-deleted sessions) with optional date range filtering.
  Results are grouped by ``session_id``.
* ``ChatStoreError`` — single exception type with ``code`` and ``message``
  attributes; ``code`` is one of ``invalid_input`` / ``invalid_query`` /
  ``not_found``.

FTS5 patterns mirror ``ohmystock.memory.{schema,store}`` (see those modules
for additional comments on tokeniser limitations and CJK behaviour). The
notable differences here:

* ``chat_messages`` uses a TEXT primary key (``msg_<12hex>``); FTS5 binds
  to the auto-assigned ``rowid`` via ``content_rowid='rowid'`` (default).
* Date filtering on ``created_at`` uses lexicographic string comparison;
  ISO 8601 with a fixed ``+08:00`` offset is sortable as plain text.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from ohmystock.chat.schema import ChatMessage, ChatSession


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_SESSION_STATUS_CHECK = "status IN ('active','deleted')"
_MESSAGE_ROLE_CHECK = "role IN ('user','assistant','tool_result')"

_DDL_CHAT_SESSIONS = f"""
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL CHECK({_SESSION_STATUS_CHECK}),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_DDL_CHAT_MESSAGES = f"""
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id),
    role TEXT NOT NULL CHECK({_MESSAGE_ROLE_CHECK}),
    content TEXT NOT NULL,
    tool_calls_json TEXT,
    tool_result_for TEXT,
    llm_cost_id TEXT,
    created_at TEXT NOT NULL
)
"""

_DDL_INDEX_MESSAGES = (
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created "
    "ON chat_messages(session_id, created_at)"
)

_DDL_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts USING fts5(
    content,
    content='chat_messages',
    content_rowid='rowid'
)
"""

_DDL_TRIGGER_AI = """
CREATE TRIGGER IF NOT EXISTS chat_messages_ai
AFTER INSERT ON chat_messages BEGIN
    INSERT INTO chat_messages_fts(rowid, content) VALUES (NEW.rowid, NEW.content);
END
"""

_DDL_TRIGGER_AD = """
CREATE TRIGGER IF NOT EXISTS chat_messages_ad
AFTER DELETE ON chat_messages BEGIN
    INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content)
    VALUES ('delete', OLD.rowid, OLD.content);
END
"""

_DDL_TRIGGER_AU = """
CREATE TRIGGER IF NOT EXISTS chat_messages_au
AFTER UPDATE ON chat_messages BEGIN
    INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content)
    VALUES ('delete', OLD.rowid, OLD.content);
    INSERT INTO chat_messages_fts(rowid, content) VALUES (NEW.rowid, NEW.content);
END
"""


# ---------------------------------------------------------------------------
# Validation helpers (shared with API layer via raised ChatStoreError)
# ---------------------------------------------------------------------------

_LIMIT_MAX_SESSIONS = 200
_LIMIT_MAX_MESSAGES = 200
_LIMIT_MAX_SEARCH = 100
_LIMIT_DEFAULT_SEARCH = 20

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
# Both "fts5: syntax error ..." and the more generic "unterminated string"
# (SQLite's complaint when MATCH receives an unclosed double-quoted phrase)
# are valid FTS5 query-shape failures we want to remap to ``invalid_query``.
_FTS5_SYNTAX_ERR_RE = re.compile(
    r"fts5|syntax error|unterminated|malformed", re.IGNORECASE
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ChatStoreError(RuntimeError):
    """Single exception type for chat storage validation / FTS5 errors.

    ``code`` is one of ``invalid_input`` / ``invalid_query`` / ``not_found``.
    Routes inspect ``error.code`` to build the HTTP envelope.
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        if not self.message:
            return self.code
        return f"{self.code}: {self.message}"


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------


def _probe_fts5(conn: sqlite3.Connection) -> None:
    """Raise ``RuntimeError`` mentioning ``"FTS5"`` if unavailable."""

    try:
        conn.execute("CREATE VIRTUAL TABLE _chat_fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE _chat_fts5_probe")
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            f"FTS5 unavailable on this SQLite build. Original error: {exc}"
        ) from exc


def init_schema(conn: sqlite3.Connection) -> None:
    """Create chat schema (tables + index + FTS5 + triggers) idempotently.

    Raises ``RuntimeError`` if the SQLite build lacks FTS5.
    """

    _probe_fts5(conn)
    with conn:
        conn.execute(_DDL_CHAT_SESSIONS)
        conn.execute(_DDL_CHAT_MESSAGES)
        conn.execute(_DDL_INDEX_MESSAGES)
        conn.execute(_DDL_FTS)
        conn.execute(_DDL_TRIGGER_AI)
        conn.execute(_DDL_TRIGGER_AD)
        conn.execute(_DDL_TRIGGER_AU)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def insert_session(conn: sqlite3.Connection, session: ChatSession) -> None:
    """Insert a new chat session row. Raises ``sqlite3.IntegrityError`` on
    duplicate id; callers SHALL allocate unique ids."""

    conn.execute(
        "INSERT INTO chat_sessions (id, title, model, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            session.id,
            session.title,
            session.model,
            session.status,
            session.created_at,
            session.updated_at,
        ),
    )
    conn.commit()


def list_sessions(
    conn: sqlite3.Connection,
    *,
    limit: int,
    offset: int,
    status: str | None = "active",
) -> tuple[list[dict[str, Any]], int]:
    """Paginated session list ordered by ``updated_at DESC, id DESC``.

    Returns ``(items, total)``. Each item carries a derived ``message_count``
    from a LEFT JOIN COUNT over ``chat_messages``. ``status=None`` lists
    every session regardless of soft-delete state (used by the FTS5 search
    route).
    """

    if limit < 1 or limit > _LIMIT_MAX_SESSIONS:
        raise ChatStoreError(
            "invalid_input",
            f"limit must be in 1..{_LIMIT_MAX_SESSIONS}, got {limit}",
        )
    if offset < 0:
        raise ChatStoreError(
            "invalid_input", f"offset must be non-negative, got {offset}"
        )

    where_sql = ""
    params: list[Any] = []
    if status is not None:
        where_sql = " WHERE status = ?"
        params.append(status)

    total_row = conn.execute(
        f"SELECT COUNT(*) FROM chat_sessions{where_sql}", params
    ).fetchone()
    total = int(total_row[0]) if total_row is not None else 0

    rows = conn.execute(
        f"""
        SELECT
            s.id, s.title, s.model, s.status, s.created_at, s.updated_at,
            (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id)
                AS message_count
        FROM chat_sessions s{where_sql}
        ORDER BY s.updated_at DESC, s.id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()

    items: list[dict[str, Any]] = [
        {
            "id": r[0],
            "title": r[1],
            "model": r[2],
            "status": r[3],
            "created_at": r[4],
            "updated_at": r[5],
            "message_count": int(r[6]),
        }
        for r in rows
    ]
    return items, total


def get_session(
    conn: sqlite3.Connection, session_id: str
) -> ChatSession | None:
    """Fetch a session by id. Returns ``None`` if no row matches."""

    row = conn.execute(
        "SELECT id, title, model, status, created_at, updated_at "
        "FROM chat_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return ChatSession(
        id=row[0],
        title=row[1],
        model=row[2],
        status=row[3],
        created_at=row[4],
        updated_at=row[5],
    )


def soft_delete_session(
    conn: sqlite3.Connection, session_id: str, now: str
) -> bool:
    """Mark a session ``status='deleted'`` idempotently.

    Returns ``True`` if the session exists (whether or not it was already
    deleted) and ``False`` if no row matched. When already deleted the
    function is a no-op — ``updated_at`` is NOT bumped on the second call
    so callers can distinguish original deletion time from re-tries.
    """

    existing = conn.execute(
        "SELECT status FROM chat_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if existing is None:
        return False
    if existing[0] == "deleted":
        return True

    conn.execute(
        "UPDATE chat_sessions SET status='deleted', updated_at=? WHERE id=?",
        (now, session_id),
    )
    conn.commit()
    return True


def touch_session(
    conn: sqlite3.Connection, session_id: str, now: str
) -> None:
    """Bump ``updated_at`` to ``now`` for an active session.

    No-op if the session does not exist. Used after each user / assistant
    message INSERT so the session list re-orders correctly.
    """

    conn.execute(
        "UPDATE chat_sessions SET updated_at=? WHERE id=?",
        (now, session_id),
    )
    conn.commit()


def update_session_title(
    conn: sqlite3.Connection, session_id: str, title: str
) -> None:
    """Replace ``title``. Used by the title autogen path; ``title`` length
    is validated by ``ChatSession`` upstream — this helper trusts the input."""

    conn.execute(
        "UPDATE chat_sessions SET title=? WHERE id=?", (title, session_id)
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------


def _normalise_tool_calls_json(value: Any) -> str | None:
    """Best-effort serialisation for ``tool_calls_json``.

    The agent runtime may hand the storage layer a partial / malformed
    payload mid-cancel. Rather than rejecting the whole message we degrade
    gracefully:

    * ``None`` → ``None``
    * already-serialised str that round-trips through ``json.loads`` → kept
    * arbitrary object that survives ``json.dumps`` → serialised
    * anything else → ``None``
    """

    if value is None:
        return None
    if isinstance(value, str):
        try:
            json.loads(value)
        except json.JSONDecodeError:
            return None
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return None


def insert_message(conn: sqlite3.Connection, msg: ChatMessage) -> None:
    """Append a single message row.

    Pydantic already validates id format / role / session_id; this helper
    only normalises ``tool_calls_json``.
    """

    conn.execute(
        "INSERT INTO chat_messages "
        "(id, session_id, role, content, tool_calls_json, tool_result_for, "
        " llm_cost_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            msg.id,
            msg.session_id,
            msg.role,
            msg.content,
            _normalise_tool_calls_json(msg.tool_calls_json),
            msg.tool_result_for,
            msg.llm_cost_id,
            msg.created_at,
        ),
    )
    conn.commit()


def select_messages(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    limit: int = _LIMIT_MAX_MESSAGES,
) -> list[ChatMessage]:
    """Return messages for one session in creation order (oldest first)."""

    if limit < 1 or limit > _LIMIT_MAX_MESSAGES:
        raise ChatStoreError(
            "invalid_input",
            f"limit must be in 1..{_LIMIT_MAX_MESSAGES}, got {limit}",
        )

    rows = conn.execute(
        "SELECT id, session_id, role, content, tool_calls_json, "
        "tool_result_for, llm_cost_id, created_at "
        "FROM chat_messages "
        "WHERE session_id = ? "
        "ORDER BY created_at ASC, id ASC "
        "LIMIT ?",
        (session_id, limit),
    ).fetchall()

    return [
        ChatMessage(
            id=r[0],
            session_id=r[1],
            role=r[2],
            content=r[3],
            tool_calls_json=r[4],
            tool_result_for=r[5],
            llm_cost_id=r[6],
            created_at=r[7],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# FTS5 search
# ---------------------------------------------------------------------------


def _sanitise_q(q: str) -> str:
    """Strip control chars and whitespace; raise on empty result."""

    cleaned = _CONTROL_CHAR_RE.sub("", q.strip())
    if not cleaned:
        raise ChatStoreError("invalid_input", "query cannot be empty")
    return cleaned


def _validate_date(value: str | None, *, field: str) -> str | None:
    """Validate a YYYY-MM-DD string; return it unchanged or ``None``."""

    if value is None:
        return None
    if not _DATE_RE.match(value):
        raise ChatStoreError(
            "invalid_input", f"{field} must be YYYY-MM-DD, got {value!r}"
        )
    return value


def _date_bounds(
    date_from: str | None, date_to: str | None
) -> tuple[str | None, str | None]:
    """Validate ``date_from <= date_to``; the storage layer treats both as
    inclusive day-boundaries and lets the SQL ``<`` operator drop messages
    on / after ``date_to+1`` thanks to lexicographic ISO 8601 ordering."""

    df = _validate_date(date_from, field="date_from")
    dt = _validate_date(date_to, field="date_to")
    if df is not None and dt is not None and df > dt:
        raise ChatStoreError(
            "invalid_input", f"date_from {df!r} > date_to {dt!r}"
        )
    return df, dt


def _next_day(iso_date: str) -> str:
    """Return the next-day YYYY-MM-DD string for an inclusive ``date_to``.

    Implemented with ``datetime`` rather than string arithmetic so month /
    year boundaries are correct.
    """

    from datetime import date, timedelta

    y, m, d = (int(part) for part in iso_date.split("-"))
    return (date(y, m, d) + timedelta(days=1)).isoformat()


def search_messages(
    conn: sqlite3.Connection,
    *,
    q: str,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = _LIMIT_DEFAULT_SEARCH,
) -> list[dict[str, Any]]:
    """FTS5 BM25 search across ``chat_messages.content``, grouped by session.

    Returns a list of ``{session_id, session_title, session_status, hits}``
    dicts ordered by the best-ranked hit within each group. Each hit carries
    ``message_id``, ``snippet`` (with ``<mark>...</mark>`` highlighting),
    and ``created_at``.
    """

    cleaned_q = _sanitise_q(q)
    df, dt = _date_bounds(date_from, date_to)
    if limit < 1 or limit > _LIMIT_MAX_SEARCH:
        raise ChatStoreError(
            "invalid_input",
            f"limit must be in 1..{_LIMIT_MAX_SEARCH}, got {limit}",
        )

    sql_where = ["chat_messages_fts MATCH ?"]
    params: list[Any] = [cleaned_q]
    if df is not None:
        sql_where.append("m.created_at >= ?")
        params.append(df)
    if dt is not None:
        sql_where.append("m.created_at < ?")
        params.append(_next_day(dt))
    where_sql = " AND ".join(sql_where)

    try:
        rows = conn.execute(
            f"""
            SELECT
                m.id, m.session_id, s.title, s.status, m.created_at,
                snippet(chat_messages_fts, 0, '<mark>', '</mark>', '...', 12)
                    AS snippet,
                bm25(chat_messages_fts) AS rank
            FROM chat_messages m
            JOIN chat_messages_fts ON chat_messages_fts.rowid = m.rowid
            JOIN chat_sessions s ON s.id = m.session_id
            WHERE {where_sql}
            ORDER BY rank ASC, m.id ASC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if _FTS5_SYNTAX_ERR_RE.search(str(exc)):
            raise ChatStoreError(
                "invalid_query", "FTS5 query syntax error"
            ) from None
        raise

    # Preserve BM25 order across groups: first time we see a session_id,
    # record its position in the output list.
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for r in rows:
        sid = r[1]
        if sid not in groups:
            groups[sid] = {
                "session_id": sid,
                "session_title": r[2],
                "session_status": r[3],
                "hits": [],
            }
            order.append(sid)
        groups[sid]["hits"].append(
            {
                "message_id": r[0],
                "snippet": r[5],
                "created_at": r[4],
            }
        )

    return [groups[sid] for sid in order]


__all__ = [
    "ChatStoreError",
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
