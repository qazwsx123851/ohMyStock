"""Read-only ``MemoryStore`` over the SQLite + FTS5 ``memory_rows`` table.

Spec: openspec/changes/web-admin-memory-page-and-store/specs/memory-store/spec.md

Public API (re-exported from ``ohmystock.memory.__init__``):

* ``MemoryRow`` — frozen pydantic model for a single row.
* ``MemoryKind`` — closed ``Literal`` enum of allowed kinds.
* ``ListResult`` — frozen pydantic model holding ``items / total / limit /
  offset / has_more`` for paginated reads.
* ``MemoryStore`` — wraps a ``sqlite3.Connection`` and exposes ``list(...)`` /
  ``search(...)``. Deliberately has NO writers — producers (Phase 5 復盤,
  proposal jobs) will land in their own changes.
* ``MemoryStoreError`` — single exception type. ``code`` is one of
  ``invalid_input`` / ``invalid_query``.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict


MemoryKind = Literal["note", "lesson", "proposal", "review_summary"]

_ALLOWED_KINDS: tuple[str, ...] = ("note", "lesson", "proposal", "review_summary")

_LIMIT_MAX = 200
_LIMIT_DEFAULT = 50

# ASCII control characters (0x00..0x1F + 0x7F). Stripped from FTS5 query input
# before binding so a paste of an accidental NUL or DEL char doesn't reach the
# parser. Anything above 0x7F (including all CJK) passes through verbatim.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")

# Regex to detect FTS5 syntax errors among generic OperationalErrors. SQLite
# wraps FTS5 parser errors as ``OperationalError`` whose message contains
# ``"fts5: syntax error"``; we remap those to a generic ``invalid_query`` so
# the route returns 400 without leaking parser internals.
_FTS5_SYNTAX_ERR_RE = re.compile(r"fts5|syntax error", re.IGNORECASE)


class MemoryStoreError(Exception):
    """Raised by ``MemoryStore`` for input validation and FTS5 syntax errors.

    ``code`` is one of ``invalid_input`` (bad limit/offset/kind/empty q) or
    ``invalid_query`` (FTS5 parser rejected the search expression). Routes
    inspect ``error.code`` to decide the HTTP envelope.
    """

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        if self.message is None:
            return self.code
        return f"{self.code}: {self.message}"


class MemoryRow(BaseModel):
    """Read-only representation of a single ``memory_rows`` row.

    ``tags`` is the already-decoded list (the SQLite column stores it as a
    JSON-encoded string; ``MemoryStore`` decodes once on read).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    kind: MemoryKind
    content: str
    tags: list[str]
    source: str | None
    created_at: str


class ListResult(BaseModel):
    """Paginated read result (shared by ``list`` and ``search``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[MemoryRow]
    total: int
    limit: int
    offset: int
    has_more: bool


def _clamp_limit(limit: int) -> int:
    """Validate + clamp pagination ``limit``.

    ``<= 0`` raises ``invalid_input``; ``> 200`` is silently clamped to 200.
    """

    if limit <= 0:
        raise MemoryStoreError(
            "invalid_input", f"limit must be positive, got {limit}"
        )
    return min(limit, _LIMIT_MAX)


def _validate_offset(offset: int) -> int:
    """Validate ``offset`` is non-negative."""

    if offset < 0:
        raise MemoryStoreError(
            "invalid_input", f"offset must be non-negative, got {offset}"
        )
    return offset


def _validate_kind(kind: str | None) -> str | None:
    """Validate ``kind`` against the closed enum (None passes through)."""

    if kind is None:
        return None
    if kind not in _ALLOWED_KINDS:
        allowed = ", ".join(_ALLOWED_KINDS)
        raise MemoryStoreError(
            "invalid_input",
            f"kind must be one of [{allowed}], got {kind!r}",
        )
    return kind


def _sanitise_q(q: str) -> str:
    """Strip whitespace + ASCII control chars from FTS5 ``q``.

    Empty result raises ``invalid_input`` so the route can return 400 BEFORE
    SQLite sees an empty ``MATCH`` (which would itself raise an error).
    """

    cleaned = _CONTROL_CHAR_RE.sub("", q.strip())
    if not cleaned:
        raise MemoryStoreError(
            "invalid_input", "query string must not be empty"
        )
    return cleaned


def _row_to_model(row: tuple) -> MemoryRow:
    """Map a raw SQL row tuple to a ``MemoryRow``.

    Row layout: ``(id, kind, content, tags_json, source, created_at)``.
    ``tags_json`` is decoded once here; if decode fails the
    ``json.JSONDecodeError`` propagates and the route maps it to 500.
    """

    tags = json.loads(row[3]) if row[3] else []
    return MemoryRow(
        id=int(row[0]),
        kind=row[1],
        content=row[2],
        tags=list(tags),
        source=row[4],
        created_at=row[5],
    )


_SELECT_COLS = "id, kind, content, tags, source, created_at"


class MemoryStore:
    """Read-only API over ``memory_rows`` + ``memory_rows_fts``.

    Construction takes a ``sqlite3.Connection`` (the route layer hands one
    via ``Depends(get_db)``); the store does NOT manage the connection
    lifecycle. NO writer methods are exposed by design — see spec
    "Requirement: 不暴露寫入 API".
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list(
        self,
        *,
        kind: MemoryKind | None = None,
        tag: str | None = None,
        limit: int = _LIMIT_DEFAULT,
        offset: int = 0,
    ) -> ListResult:
        """Recency-sorted list with optional ``kind`` / ``tag`` filters."""

        kind_v = _validate_kind(kind)
        tag_v = tag if tag else None  # treat empty string as absent
        effective_limit = _clamp_limit(limit)
        effective_offset = _validate_offset(offset)

        where_clauses: list[str] = []
        params: list[object] = []
        if kind_v is not None:
            where_clauses.append("kind = ?")
            params.append(kind_v)
        if tag_v is not None:
            where_clauses.append(
                "EXISTS (SELECT 1 FROM json_each(memory_rows.tags) "
                "WHERE value = ?)"
            )
            params.append(tag_v)
        where_sql = (
            f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        )

        total_row = self._conn.execute(
            f"SELECT COUNT(*) FROM memory_rows{where_sql}", params
        ).fetchone()
        total = int(total_row[0]) if total_row is not None else 0

        rows = self._conn.execute(
            f"SELECT {_SELECT_COLS} FROM memory_rows{where_sql} "
            "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            [*params, effective_limit, effective_offset],
        ).fetchall()

        items = [_row_to_model(r) for r in rows]
        return ListResult(
            items=items,
            total=total,
            limit=effective_limit,
            offset=effective_offset,
            has_more=effective_offset + len(items) < total,
        )

    def search(
        self,
        *,
        q: str,
        limit: int = _LIMIT_DEFAULT,
        offset: int = 0,
    ) -> ListResult:
        """FTS5 BM25-ranked search over ``memory_rows.content``."""

        cleaned_q = _sanitise_q(q)
        effective_limit = _clamp_limit(limit)
        effective_offset = _validate_offset(offset)

        try:
            total_row = self._conn.execute(
                "SELECT COUNT(*) FROM memory_rows_fts "
                "WHERE memory_rows_fts MATCH ?",
                (cleaned_q,),
            ).fetchone()
            total = int(total_row[0]) if total_row is not None else 0

            rows = self._conn.execute(
                "SELECT memory_rows.id, memory_rows.kind, memory_rows.content, "
                "memory_rows.tags, memory_rows.source, memory_rows.created_at "
                "FROM memory_rows "
                "JOIN memory_rows_fts ON memory_rows_fts.rowid = memory_rows.id "
                "WHERE memory_rows_fts MATCH ? "
                "ORDER BY bm25(memory_rows_fts) ASC, memory_rows.id ASC "
                "LIMIT ? OFFSET ?",
                (cleaned_q, effective_limit, effective_offset),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if _FTS5_SYNTAX_ERR_RE.search(str(exc)):
                raise MemoryStoreError(
                    "invalid_query", "FTS5 query syntax error"
                ) from None
            raise

        items = [_row_to_model(r) for r in rows]
        return ListResult(
            items=items,
            total=total,
            limit=effective_limit,
            offset=effective_offset,
            has_more=effective_offset + len(items) < total,
        )
