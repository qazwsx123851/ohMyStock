"""Confirm Gate admin endpoints — list / confirm / reject / sweep-expired.

Each endpoint wraps a function from ``ohmystock.safety.confirm_gate`` and
translates ``ConfirmGateError`` / ``ValueError`` into the unified envelope
via ``map_exception_to_envelope``. The ``confirm`` handler instantiates a
``FakePaperBroker`` per design Decision 4 — Shioaji wiring is a future
change.

Spec: openspec/changes/server-action-endpoints-v0/specs/server-action-endpoints/spec.md
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ohmystock.api.auth import require_admin
from ohmystock.api.routes._deps import get_db, get_settings_dep
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_error,
    to_success,
)
from ohmystock.config import Settings
from ohmystock.paper import FakePaperBroker
from ohmystock.safety.confirm_gate import (
    _compute_qty,
    confirm,
    list_pending,
    reject,
    sweep_expired,
    system_clock,
)


router = APIRouter(dependencies=[Depends(require_admin)])


class ConfirmRequest(BaseModel):
    decision_id: str = Field(..., min_length=1)
    user: str = Field(..., min_length=1)
    # CG-B1: optional human override of the system-sized quantity (shares).
    # The server is the sole arbiter — it still applies the sizing clamp
    # defenses regardless of what the dialog sends.
    override_qty: int | None = Field(default=None, gt=0)


class RejectRequest(BaseModel):
    decision_id: str = Field(..., min_length=1)
    user: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class SweepExpiredRequest(BaseModel):
    timeout_minutes: int | None = None


# ---------------------------------------------------------------------------
# GET /api/admin/confirm-gate/pending
# ---------------------------------------------------------------------------


@router.get("/api/admin/confirm-gate/pending")
def get_pending(
    timeout_minutes: int | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:
    effective = (
        timeout_minutes
        if timeout_minutes is not None
        else settings.ohmystock_confirm_timeout_minutes
    )
    if effective <= 0:
        body = to_error(
            "invalid_input",
            f"timeout_minutes must be positive, got {effective}",
        )
        return JSONResponse(status_code=400, content=body)

    try:
        items = list_pending(conn, timeout_minutes=effective, clock=system_clock)
    except Exception as exc:
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    serialised = [
        {
            "decision_id": p.decision_id,
            "symbol": p.symbol,
            "created_at": p.created_at,
            "age_seconds": p.age_seconds,
            "ttl_seconds": p.ttl_seconds,
            "current_price": p.current_price,
            "final_sizing_pct": p.final_sizing_pct,
            # CG-B1: system-sized suggestion (shares) so the confirm dialog can
            # pre-fill 建議張數 without the frontend needing the capital base.
            "suggested_qty": (
                _compute_qty(
                    settings.ohmystock_default_capital_twd,
                    p.final_sizing_pct,
                    p.current_price,
                )
                if p.current_price > 0
                else 0
            ),
        }
        for p in items
    ]
    return JSONResponse(
        status_code=200,
        content=to_success({"items": serialised, "timeout_minutes": effective}),
    )


# ---------------------------------------------------------------------------
# POST /api/admin/confirm-gate/confirm
# ---------------------------------------------------------------------------


@router.post("/api/admin/confirm-gate/confirm")
def post_confirm(
    req: ConfirmRequest,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:
    broker = FakePaperBroker(clock=system_clock)
    try:
        result = confirm(
            conn,
            decision_id=req.decision_id,
            broker=broker,
            default_capital_twd=settings.ohmystock_default_capital_twd,
            user=req.user,
            auto_executed=False,
            override_qty=req.override_qty,
            max_notional_pct=settings.ohmystock_auto_execute_max_notional_pct,
            max_sizing_deviation=settings.ohmystock_auto_execute_max_sizing_deviation,
            clock=system_clock,
        )
    except Exception as exc:
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    return JSONResponse(
        status_code=200,
        content=to_success(
            {
                "decision_id": result.decision_id,
                "fill": asdict(result.fill),
                "qty": result.qty,
                "clamped": result.clamped,
            }
        ),
    )


# ---------------------------------------------------------------------------
# POST /api/admin/confirm-gate/reject
# ---------------------------------------------------------------------------


@router.post("/api/admin/confirm-gate/reject")
def post_reject(
    req: RejectRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    if not req.reason.strip():
        body = to_error("invalid_input", "reason must be a non-empty string")
        return JSONResponse(status_code=400, content=body)

    try:
        result = reject(
            conn,
            decision_id=req.decision_id,
            reason=req.reason,
            user=req.user,
            clock=system_clock,
        )
    except Exception as exc:
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    return JSONResponse(
        status_code=200,
        content=to_success(
            {
                "decision_id": result.decision_id,
                "reject_row_id": result.reject_row_id,
            }
        ),
    )


# ---------------------------------------------------------------------------
# POST /api/admin/confirm-gate/sweep-expired
# ---------------------------------------------------------------------------


@router.post("/api/admin/confirm-gate/sweep-expired")
def post_sweep_expired(
    req: SweepExpiredRequest,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:
    effective = (
        req.timeout_minutes
        if req.timeout_minutes is not None
        else settings.ohmystock_confirm_timeout_minutes
    )
    if effective <= 0:
        body = to_error(
            "invalid_input",
            f"timeout_minutes must be positive, got {effective}",
        )
        return JSONResponse(status_code=400, content=body)

    try:
        swept_ids = sweep_expired(
            conn, timeout_minutes=effective, clock=system_clock
        )
    except Exception as exc:
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    return JSONResponse(
        status_code=200,
        content=to_success(
            {
                "swept_decision_ids": swept_ids,
                "swept_count": len(swept_ids),
                "timeout_minutes": effective,
            }
        ),
    )
