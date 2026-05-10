"""GET /api/admin/memory/rows + GET /api/admin/memory/search.

Surfaces the read-only ``MemoryStore`` from the web-admin UI. Two endpoints:

* ``/rows`` — paginated recency-sorted listing with optional ``kind`` /
  ``tag`` filters.
* ``/search`` — FTS5 BM25-ranked search over ``content``.

Both endpoints sit on router-level ``Depends(require_admin)``, take a
per-request SQLite connection via ``Depends(get_db)``, and wrap success in
``to_success(...)`` / failures in ``to_error(...)``. ``MemoryStoreError``
codes (``invalid_input`` / ``invalid_query``) translate to HTTP 400 with
the same code in the envelope; anything else collapses to 500
``internal_error`` via ``map_exception_to_envelope`` (which also strips
the message — never leak SQLite parser text to the client).

Spec: openspec/changes/web-admin-memory-page-and-store/specs/admin-memory-endpoints/spec.md
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from ohmystock.api.auth import require_admin
from ohmystock.api.routes._deps import get_db
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_error,
    to_success,
)
from ohmystock.memory import MemoryRow, MemoryStore, MemoryStoreError


_PREVIEW_LIMIT = 200


router = APIRouter(dependencies=[Depends(require_admin)])


def _row_to_json(row: MemoryRow) -> dict[str, Any]:
    """Map a ``MemoryRow`` to the JSON shape with ``content_preview`` flag."""

    return {
        "id": row.id,
        "kind": row.kind,
        "content": row.content,
        "content_preview": row.content[:_PREVIEW_LIMIT],
        "content_truncated": len(row.content) > _PREVIEW_LIMIT,
        "tags": list(row.tags),
        "source": row.source,
        "created_at": row.created_at,
    }


def _result_payload(
    items: list[MemoryRow],
    *,
    total: int,
    limit: int,
    offset: int,
    has_more: bool,
) -> dict[str, Any]:
    return {
        "items": [_row_to_json(r) for r in items],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }


@router.get("/api/admin/memory/rows")
def list_memory_rows(
    kind: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    try:
        result = MemoryStore(conn).list(
            kind=kind,  # type: ignore[arg-type]
            tag=tag,
            limit=limit,
            offset=offset,
        )
    except MemoryStoreError as exc:
        if exc.code == "invalid_input":
            return JSONResponse(
                status_code=400,
                content=to_error("invalid_input", str(exc.message or exc.code)),
            )
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)
    except Exception as exc:  # noqa: BLE001 — generic mapper redacts message
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    return JSONResponse(
        status_code=200,
        content=to_success(
            _result_payload(
                result.items,
                total=result.total,
                limit=result.limit,
                offset=result.offset,
                has_more=result.has_more,
            )
        ),
    )


@router.get("/api/admin/memory/search")
def search_memory_rows(
    q: str = Query(...),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    try:
        result = MemoryStore(conn).search(q=q, limit=limit, offset=offset)
    except MemoryStoreError as exc:
        if exc.code == "invalid_input":
            return JSONResponse(
                status_code=400,
                content=to_error("invalid_input", str(exc.message or exc.code)),
            )
        if exc.code == "invalid_query":
            return JSONResponse(
                status_code=400,
                content=to_error("invalid_query", "FTS5 query syntax error"),
            )
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    return JSONResponse(
        status_code=200,
        content=to_success(
            _result_payload(
                result.items,
                total=result.total,
                limit=result.limit,
                offset=result.offset,
                has_more=result.has_more,
            )
        ),
    )
