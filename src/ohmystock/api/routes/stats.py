"""GET /api/admin/stats/today — daily KPI counters from ``journal_entries``.

Single SQL aggregate over today's TPE calendar day. Six counters:
``decisions_made``, ``entries_pending``, ``entries_filled``, ``rejects``,
``expires``, ``auto_execute_audits``. Empty-table case yields all zeros
via ``COALESCE(SUM(...), 0)``.

Spec: openspec/changes/read-side-admin-endpoints-v0/specs/admin-read-endpoints/spec.md
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
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


router = APIRouter(dependencies=[Depends(require_admin)])

_TPE = ZoneInfo("Asia/Taipei")


class StatsTodayData(BaseModel):
    model_config = ConfigDict(frozen=True)

    asof_date: str
    decisions_made: int
    entries_pending: int
    entries_filled: int
    rejects: int
    expires: int
    auto_execute_audits: int


_AGGREGATE_SQL = """
    SELECT
        COALESCE(SUM(CASE WHEN kind = 'entry' THEN 1 ELSE 0 END), 0)
            AS decisions_made,
        COALESCE(SUM(CASE WHEN kind = 'entry'
            AND json_extract(payload_json, '$.actual_entry_price') IS NULL
            THEN 1 ELSE 0 END), 0) AS entries_pending,
        COALESCE(SUM(CASE WHEN kind = 'entry'
            AND json_extract(payload_json, '$.actual_entry_price') IS NOT NULL
            THEN 1 ELSE 0 END), 0) AS entries_filled,
        COALESCE(SUM(CASE WHEN kind = 'reject' THEN 1 ELSE 0 END), 0)
            AS rejects,
        COALESCE(SUM(CASE WHEN kind = 'expire' THEN 1 ELSE 0 END), 0)
            AS expires,
        COALESCE(SUM(CASE WHEN kind = 'auto_execute_audit' THEN 1 ELSE 0 END), 0)
            AS auto_execute_audits
    FROM journal_entries
    WHERE substr(created_at, 1, 10) = ?
"""


@router.get("/api/admin/stats/today")
def get_stats_today(
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    try:
        today_str = datetime.now(_TPE).date().isoformat()
        row = conn.execute(_AGGREGATE_SQL, (today_str,)).fetchone()
        if row is None:
            counts = (0, 0, 0, 0, 0, 0)
        else:
            counts = tuple(int(v or 0) for v in row)

        data = StatsTodayData(
            asof_date=today_str,
            decisions_made=counts[0],
            entries_pending=counts[1],
            entries_filled=counts[2],
            rejects=counts[3],
            expires=counts[4],
            auto_execute_audits=counts[5],
        )
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    return JSONResponse(
        status_code=200,
        content=to_success(data.model_dump(mode="json")),
    )
