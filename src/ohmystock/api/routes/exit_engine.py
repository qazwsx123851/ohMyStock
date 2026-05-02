"""POST /api/admin/exit-engine/run — wraps ``evaluate_open_positions()``.

The default ``MarketDataLookup`` reads close prices from the
``bars_daily`` cache (``ohmystock.data.cache.select_bars``); tests
override the dependency to inject a deterministic dict-based lookup.

Spec: openspec/changes/server-action-endpoints-v0/specs/server-action-endpoints/spec.md
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ohmystock.api.routes._deps import get_db
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_error,
    to_success,
)
from ohmystock.data.cache import select_bars
from ohmystock.exit_engine.evaluator import (
    MarketDataLookup,
    evaluate_open_positions,
)
from ohmystock.safety.confirm_gate import system_clock


router = APIRouter()

_TPE_TZ = timezone(timedelta(hours=8))


class ExitEngineRunRequest(BaseModel):
    asof_date: str | None = None
    symbol: str | None = None


class _SqliteMarketDataLookup:
    """Default ``MarketDataLookup`` reading from the ``bars_daily`` cache."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_close(self, symbol: str, asof: date) -> float | None:
        iso = asof.isoformat()
        bars = select_bars(self._conn, symbol, iso, iso)
        if not bars:
            return None
        return float(bars[0]["c"])


def get_market_data(
    conn: sqlite3.Connection = Depends(get_db),
) -> MarketDataLookup:
    """FastAPI dependency producing the default lookup. Tests override this."""

    return _SqliteMarketDataLookup(conn)


def _parse_asof(asof_date: str | None) -> date:
    if asof_date is None:
        return datetime.now(_TPE_TZ).date()
    try:
        return date.fromisoformat(asof_date)
    except ValueError as exc:
        raise ValueError(
            f"asof_date must be 'YYYY-MM-DD', got {asof_date!r}: {exc}"
        ) from exc


def _serialise_result(result) -> dict:
    decision = result.decision
    return {
        "decision_id": result.decision_id,
        "action": result.action,
        "decision": asdict(decision) if decision is not None else None,
    }


@router.post("/api/admin/exit-engine/run")
def run_exit_engine(
    req: ExitEngineRunRequest,
    conn: sqlite3.Connection = Depends(get_db),
    market_data: MarketDataLookup = Depends(get_market_data),
) -> JSONResponse:
    try:
        asof = _parse_asof(req.asof_date)
    except ValueError as exc:
        body = to_error("invalid_input", str(exc))
        return JSONResponse(status_code=400, content=body)

    try:
        results = evaluate_open_positions(
            conn,
            market_data=market_data,
            asof=asof,
            clock=system_clock,
            symbol_filter=req.symbol,
        )
    except Exception as exc:
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    serialised = [_serialise_result(r) for r in results]
    closed_count = sum(1 for r in results if r.action == "closed")
    held_count = sum(1 for r in results if r.action == "held")

    return JSONResponse(
        status_code=200,
        content=to_success(
            {
                "results": serialised,
                "evaluated_count": len(results),
                "closed_count": closed_count,
                "held_count": held_count,
                "asof_date_used": asof.isoformat(),
            }
        ),
    )
