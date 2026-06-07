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
from ohmystock.api.routes._deps import get_db, get_settings_dep
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_success,
)
from ohmystock.config import Settings
from ohmystock.journal.repository import monthly_realized_pnl_pct
from ohmystock.observability.cost_tracker import monthly_cost_summary


router = APIRouter(dependencies=[Depends(require_admin)])

_TPE = ZoneInfo("Asia/Taipei")


class MonthlyBreaker(BaseModel):
    model_config = ConfigDict(frozen=True)

    tripped: bool
    month_pnl_pct: float


class CostInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    used_usd: float
    budget_usd: float
    pct: float


class StatsTodayData(BaseModel):
    model_config = ConfigDict(frozen=True)

    asof_date: str
    decisions_made: int
    entries_pending: int
    entries_filled: int
    rejects: int
    expires: int
    auto_execute_audits: int
    monthly_breaker: MonthlyBreaker
    cost: CostInfo


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
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:
    try:
        now = datetime.now(_TPE)
        today_str = now.date().isoformat()
        now_iso = now.isoformat()
        row = conn.execute(_AGGREGATE_SQL, (today_str,)).fetchone()
        if row is None:
            counts = (0, 0, 0, 0, 0, 0)
        else:
            counts = tuple(int(v or 0) for v in row)

        # Monthly circuit-breaker — display only (enforcement out of scope).
        # Threshold + PnL formula are SSOT (workflow-cheatsheet §0); we only
        # read the computed value and compare, never re-derive the formula.
        month_pnl_pct = monthly_realized_pnl_pct(
            conn, asof=now_iso, starting_equity=settings.starting_equity_twd
        )
        breaker = MonthlyBreaker(
            tripped=month_pnl_pct <= settings.ohmystock_monthly_breaker_pct,
            month_pnl_pct=month_pnl_pct,
        )

        # Month-to-date LLM cost vs budget ceiling.
        used_usd, _ = monthly_cost_summary(conn, year_month=today_str[:7])
        budget_usd = settings.ohmystock_monthly_budget_usd
        cost = CostInfo(
            used_usd=used_usd,
            budget_usd=budget_usd,
            pct=(used_usd / budget_usd * 100.0) if budget_usd > 0 else 0.0,
        )

        data = StatsTodayData(
            asof_date=today_str,
            decisions_made=counts[0],
            entries_pending=counts[1],
            entries_filled=counts[2],
            rejects=counts[3],
            expires=counts[4],
            auto_execute_audits=counts[5],
            monthly_breaker=breaker,
            cost=cost,
        )
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    return JSONResponse(
        status_code=200,
        content=to_success(data.model_dump(mode="json")),
    )
