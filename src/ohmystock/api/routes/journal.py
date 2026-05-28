"""Read-only journal admin endpoints.

* ``GET /api/admin/journal/rows`` — paginated list with ``kind`` /
  ``symbol`` / ``date_from`` / ``date_to`` / ``limit`` / ``offset``
  filters; ``ORDER BY created_at DESC, id DESC``; ``limit`` defaults
  to 100, silently clamps to 500.
* ``GET /api/admin/journal/decisions/{decision_id}`` — every row that
  shares the given ``decision_id``, ordered ASC; ``not_found`` 404 when
  no row exists.

Both handlers route ``ValueError`` (from input validation) and any
unexpected ``Exception`` through ``map_exception_to_envelope`` so the
unified envelope and redaction rules are honoured.

Spec: openspec/changes/read-side-admin-endpoints-v0/specs/admin-read-endpoints/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from ohmystock.api.auth import require_admin
from ohmystock.api.routes._deps import get_db
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_error,
    to_success,
)
from ohmystock.eventbus import Agent, Event, EventType, safe_emit_sync


def _build_query_repr(
    *,
    kind: str | None,
    symbol: str | None,
    date_from: str | None,
    date_to: str | None,
) -> str:
    parts: list[str] = []
    if kind is not None:
        parts.append(f"kind={kind}")
    if symbol is not None:
        parts.append(f"symbol={symbol}")
    if date_from is not None:
        parts.append(f"date_from={date_from}")
    if date_to is not None:
        parts.append(f"date_to={date_to}")
    return "&".join(parts) if parts else "all"


router = APIRouter(dependencies=[Depends(require_admin)])


_VALID_KINDS = frozenset(
    {"entry", "exit", "reject", "expire", "auto_execute_audit"}
)
_DEFAULT_LIMIT = 100
_MAX_LIMIT = 500


class JournalRowItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    decision_id: str
    kind: str
    symbol: str
    created_at: str
    payload: dict[str, Any]


class JournalRowsData(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[JournalRowItem]
    total: int
    limit: int
    offset: int
    has_more: bool


class DecisionDetailData(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_id: str
    rows: list[JournalRowItem]


def _parse_payload(payload_json: str, row_id: int) -> dict[str, Any]:
    """Decode ``payload_json`` to a dict; ``ValueError`` on malformed JSON."""
    try:
        parsed = json.loads(payload_json)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"corrupt payload_json id={row_id}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"corrupt payload_json id={row_id}")
    return parsed


def _validate_kind(kind: str | None) -> str | None:
    if kind is None:
        return None
    if kind not in _VALID_KINDS:
        raise ValueError(
            f"invalid kind {kind!r}; expected one of "
            f"{sorted(_VALID_KINDS)}"
        )
    return kind


def _validate_date(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"invalid {name}: {value!r}") from exc
    return value


def _build_filters(
    *,
    kind: str | None,
    symbol: str | None,
    date_from: str | None,
    date_to: str | None,
) -> tuple[str, list[Any]]:
    """Return ``(where_clause, params)`` — empty clause when no filter."""
    clauses: list[str] = []
    params: list[Any] = []
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    if symbol is not None:
        clauses.append("symbol = ?")
        params.append(symbol)
    if date_from is not None:
        clauses.append("substr(created_at, 1, 10) >= ?")
        params.append(date_from)
    if date_to is not None:
        clauses.append("substr(created_at, 1, 10) <= ?")
        params.append(date_to)
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def _row_to_item(row: tuple[Any, ...]) -> JournalRowItem:
    row_id, decision_id, kind, symbol, created_at, payload_json = row
    return JournalRowItem(
        id=int(row_id),
        decision_id=str(decision_id),
        kind=str(kind),
        symbol=str(symbol),
        created_at=str(created_at),
        payload=_parse_payload(str(payload_json), int(row_id)),
    )


# ---------------------------------------------------------------------------
# GET /api/admin/journal/rows
# ---------------------------------------------------------------------------


@router.get("/api/admin/journal/rows")
def get_journal_rows(
    kind: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT),
    offset: int = Query(default=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    try:
        kind_v = _validate_kind(kind)
        date_from_v = _validate_date(date_from, "date_from")
        date_to_v = _validate_date(date_to, "date_to")
        if (
            date_from_v is not None
            and date_to_v is not None
            and date_from_v > date_to_v
        ):
            raise ValueError(
                f"date_from > date_to: {date_from_v!r} > {date_to_v!r}"
            )
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        if offset < 0:
            raise ValueError(f"offset must be non-negative, got {offset}")
        effective_limit = min(limit, _MAX_LIMIT)

        where, params = _build_filters(
            kind=kind_v,
            symbol=symbol,
            date_from=date_from_v,
            date_to=date_to_v,
        )

        total_row = conn.execute(
            f"SELECT COUNT(*) FROM journal_entries{where}", params
        ).fetchone()
        total = int(total_row[0]) if total_row is not None else 0

        rows = conn.execute(
            (
                "SELECT id, decision_id, kind, symbol, created_at, "
                f"payload_json FROM journal_entries{where} "
                "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
            ),
            [*params, effective_limit, offset],
        ).fetchall()

        items = [_row_to_item(r) for r in rows]
        data = JournalRowsData(
            items=items,
            total=total,
            limit=effective_limit,
            offset=offset,
            has_more=offset + len(items) < total,
        )
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    safe_emit_sync(
        Event(
            event_type=EventType.JOURNAL_QUERIED,
            agent=Agent.LIBRARIAN,
            payload={
                "query": _build_query_repr(
                    kind=kind_v,
                    symbol=symbol,
                    date_from=date_from_v,
                    date_to=date_to_v,
                ),
                "result_count": len(items),
            },
        )
    )

    return JSONResponse(
        status_code=200,
        content=to_success(data.model_dump(mode="json")),
    )


# ---------------------------------------------------------------------------
# GET /api/admin/journal/decisions/{decision_id}
# ---------------------------------------------------------------------------


@router.get("/api/admin/journal/decisions/{decision_id}")
def get_decision_detail(
    decision_id: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    try:
        rows = conn.execute(
            (
                "SELECT id, decision_id, kind, symbol, created_at, "
                "payload_json FROM journal_entries "
                "WHERE decision_id = ? "
                "ORDER BY created_at ASC, id ASC"
            ),
            (decision_id,),
        ).fetchall()

        if not rows:
            return JSONResponse(
                status_code=404,
                content=to_error(
                    "not_found", f"decision_id {decision_id} not found"
                ),
            )

        items = [_row_to_item(r) for r in rows]
        data = DecisionDetailData(decision_id=decision_id, rows=items)
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    safe_emit_sync(
        Event(
            event_type=EventType.JOURNAL_QUERIED,
            agent=Agent.LIBRARIAN,
            payload={
                "query": f"decision_id={decision_id}",
                "result_count": len(items),
            },
        )
    )

    return JSONResponse(
        status_code=200,
        content=to_success(data.model_dump(mode="json")),
    )
