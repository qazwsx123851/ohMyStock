"""GET /api/admin/positions/open — open paper-trading positions.

Delegates the entry∖exit anti-join to
``ohmystock.journal.repository.open_positions(conn, asof=now_iso)`` and
enriches each result with ``hold_days`` plus the optional protective
levels (``stop_loss``, ``t1_target``, ``time_stop_date``) lifted from
the entry row's ``payload_json`` via a single bulk fetch.

Spec: openspec/changes/read-side-admin-endpoints-v0/specs/admin-read-endpoints/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from ohmystock.api.auth import require_admin
from ohmystock.api.routes._deps import get_db
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_success,
)
from ohmystock.journal.repository import open_positions


router = APIRouter(dependencies=[Depends(require_admin)])

_TPE = ZoneInfo("Asia/Taipei")


class PositionItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_id: str
    symbol: str
    sector: str
    entry_price: float
    qty_lots: int
    entry_ts: str
    hold_days: int
    stop_loss: float | None
    t1_target: float | None
    time_stop_date: str | None


class PositionsOpenData(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[PositionItem]
    asof_iso: str
    count: int


def _bulk_fetch_payloads(
    conn: sqlite3.Connection, decision_ids: list[str]
) -> dict[str, dict[str, Any]]:
    if not decision_ids:
        return {}
    placeholders = ",".join("?" * len(decision_ids))
    rows = conn.execute(
        (
            "SELECT decision_id, payload_json FROM journal_entries "
            f"WHERE kind = 'entry' AND decision_id IN ({placeholders})"
        ),
        decision_ids,
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for did, payload_json in rows:
        try:
            parsed = json.loads(payload_json)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            out[str(did)] = parsed
    return out


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


@router.get("/api/admin/positions/open")
def get_open_positions(
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    try:
        now = datetime.now(_TPE)
        now_iso = now.isoformat()
        today = now.date()

        positions = open_positions(conn, asof=now_iso)
        decision_ids = [p.decision_id for p in positions]
        payloads = _bulk_fetch_payloads(conn, decision_ids)

        items: list[PositionItem] = []
        for p in positions:
            payload = payloads.get(p.decision_id, {})
            try:
                entry_date = date.fromisoformat(p.entry_ts[:10])
                hold_days = max(0, (today - entry_date).days)
            except ValueError:
                hold_days = 0
            items.append(
                PositionItem(
                    decision_id=p.decision_id,
                    symbol=p.symbol,
                    sector=p.sector,
                    entry_price=p.entry_price,
                    qty_lots=p.qty_lots,
                    entry_ts=p.entry_ts,
                    hold_days=hold_days,
                    stop_loss=_to_float_or_none(payload.get("stop_loss")),
                    t1_target=_to_float_or_none(payload.get("t1_target")),
                    time_stop_date=_to_str_or_none(
                        payload.get("time_stop_date")
                    ),
                )
            )

        data = PositionsOpenData(
            items=items, asof_iso=now_iso, count=len(items)
        )
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    return JSONResponse(
        status_code=200,
        content=to_success(data.model_dump(mode="json")),
    )
