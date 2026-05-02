"""POST /api/admin/screener/run — wraps ``screen_universe()``.

The handler delegates to ``ohmystock.screener.universe.screen_universe`` and
translates its native envelope (UPPERCASE codes) to the unified admin
envelope via ``screener_envelope_to_http``. We pass the request-scoped
``sqlite3.Connection`` from ``get_db`` so the screener reuses that
connection rather than opening a parallel one.

Spec: openspec/changes/server-action-endpoints-v0/specs/server-action-endpoints/spec.md
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ohmystock.api.routes._deps import get_db
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    screener_envelope_to_http,
)
from ohmystock.screener.universe import screen_universe


router = APIRouter()


class ScreenerRunRequest(BaseModel):
    """Body for ``POST /api/admin/screener/run``.

    ``universe`` mirrors ``screen_universe``'s ``_VALID_UNIVERSES`` set
    ({"TWSE", "OTC", "TWSE+OTC", "custom"}). Pydantic does not enforce
    the literal — the screener returns a structured ``INVALID_INPUT``
    envelope for any unknown value, which the endpoint maps to HTTP 400.
    """

    universe: str = Field(..., min_length=1)
    custom_symbols: list[str] | None = None
    filters: list[dict[str, Any]] | None = None
    asof_date: str | None = None


@router.post("/api/admin/screener/run")
def run_screener(
    req: ScreenerRunRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    try:
        envelope = screen_universe(
            universe=req.universe,
            custom_symbols=req.custom_symbols,
            filters=req.filters,
            asof_date=req.asof_date,
            _conn=conn,
        )
    except Exception as exc:
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    status, body = screener_envelope_to_http(envelope)
    return JSONResponse(status_code=status, content=body)
