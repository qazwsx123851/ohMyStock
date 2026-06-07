"""GET /api/admin/settings — read-only redacted Settings snapshot.

Surfaces the live ``Settings`` object grouped into 4 sections so the admin
operator can confirm cold-start state from the browser:

* ``api_keys``: which credential blocks are populated (booleans only;
  no prefix, no length, no hash — see spec §"秘密欄位以布林呈現").
* ``theme``: hardcoded ``{"mode": "system"}`` placeholder per design D4.
* ``safety``: ``auto_execute`` flag and broker mode.
* ``breakers``: 7 auto-execute breaker thresholds, mapped 1:1 from
  ``Settings`` with no clamp / rounding.

The endpoint is GET-only; ``OHMYSTOCK_AUTO_EXECUTE`` and broker mode stay
edited via ``.env`` + restart per ``docs/safety-and-simulation.md`` §2.9
(design D1).

Spec: openspec/changes/web-admin-settings-page/specs/admin-settings-endpoint/spec.md
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
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
from ohmystock.observability.cost_tracker import monthly_cost_summary


router = APIRouter(dependencies=[Depends(require_admin)])

_TPE = ZoneInfo("Asia/Taipei")


def _is_set(value: str | None) -> bool:
    """Truthy iff ``value`` is a non-empty string after ``.strip()``.

    Used as the boolean redactor for every secret-bearing field. Returns
    ``False`` for ``None``, ``""``, and whitespace-only values.
    """

    if value is None:
        return False
    return bool(value.strip())


def _redact(settings: Settings) -> dict[str, Any]:
    """Whitelist + redact ``Settings`` into the 4-section response shape.

    Hand-written whitelist (NOT ``settings.model_dump()``). New fields in
    ``Settings`` therefore do NOT leak through ``/settings`` automatically;
    adding a field is an explicit follow-up (design "Risks / Trade-offs").
    """

    shioaji_set = _is_set(settings.shioaji_api_key) and _is_set(
        settings.shioaji_secret_key
    )

    return {
        "api_keys": {
            "anthropic": _is_set(settings.anthropic_api_key),
            "finmind": _is_set(settings.finmind_token),
            "shioaji": shioaji_set,
        },
        "theme": {"mode": "system"},
        "safety": {
            "auto_execute": settings.ohmystock_auto_execute,
            "broker": settings.ohmystock_broker,
        },
        "breakers": {
            "min_confidence": settings.ohmystock_auto_execute_min_confidence,
            "daily_limit": settings.ohmystock_auto_execute_daily_limit,
            "max_notional_pct": settings.ohmystock_auto_execute_max_notional_pct,
            "max_sizing_deviation": settings.ohmystock_auto_execute_max_sizing_deviation,
            "loss_lockout_hours": settings.ohmystock_auto_execute_loss_lockout_hours,
            "loss_pct_threshold": settings.ohmystock_auto_execute_loss_pct_threshold,
            "account_equity_twd": settings.ohmystock_auto_execute_account_equity_twd,
        },
        "chat": {
            "model_default": settings.ohmystock_chat_model_default,
            "title_model": settings.ohmystock_chat_title_model,
        },
    }


def _budget_block(
    conn: sqlite3.Connection, settings: Settings
) -> dict[str, Any]:
    """Read-only month-to-date LLM spend vs budget + per-model mix (ST-B2).

    Same cost-tracking source as the dashboard cost bar; surfaced here so the
    operator sees remaining quota and where spend is going without leaving
    Settings.
    """
    year_month = datetime.now(_TPE).date().isoformat()[:7]
    used_usd, model_mix = monthly_cost_summary(conn, year_month=year_month)
    budget_usd = settings.ohmystock_monthly_budget_usd
    return {
        "used_usd": used_usd,
        "budget_usd": budget_usd,
        "remaining_usd": max(0.0, budget_usd - used_usd),
        "model_mix": model_mix,
    }


@router.get("/api/admin/settings")
def get_settings(
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:
    try:
        data = _redact(settings)
        data["budget"] = _budget_block(conn, settings)
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    return JSONResponse(status_code=200, content=to_success(data))


# ---------------------------------------------------------------------------
# POST /api/admin/settings/test-connection — lightweight provider ping
# ---------------------------------------------------------------------------

_VALID_PROVIDERS = ("shioaji", "finmind")


class TestConnectionRequest(BaseModel):
    provider: str = Field(..., min_length=1)


def _probe_finmind() -> None:
    """Minimal FinMind query (one symbol, one day) — does not consume notable
    quota. Lazily imports the client so missing optional deps don't break
    module import in test/CLI scopes."""
    from ohmystock.data.finmind_client import FinMindClient

    client = FinMindClient()
    client.get_taiwan_stock_price("2330", "2024-01-02", "2024-01-02")


def _probe_shioaji() -> None:
    """Shioaji sim login only — no order, no snapshot. Lazily imported because
    the shioaji package may be absent in non-broker environments."""
    from ohmystock.paper.shioaji_client import ShioajiPaperClient

    client = ShioajiPaperClient()
    client.login()


_PROBES = {"finmind": _probe_finmind, "shioaji": _probe_shioaji}


@router.post("/api/admin/settings/test-connection")
def post_test_connection(
    req: TestConnectionRequest,
) -> JSONResponse:
    if req.provider not in _VALID_PROVIDERS:
        body = to_error(
            "invalid_input",
            f"provider must be one of {_VALID_PROVIDERS}, got {req.provider!r}",
        )
        return JSONResponse(status_code=400, content=body)

    probe = _PROBES[req.provider]
    start = perf_counter()
    try:
        probe()
    except Exception as exc:  # noqa: BLE001
        # The connectors raise *ConnectionError with messages that describe the
        # transport/login failure but never echo the API key. Cap length so an
        # unexpected verbose error can't bloat the response.
        return JSONResponse(
            status_code=200,
            content=to_success({"ok": False, "error": str(exc)[:300]}),
        )

    latency_ms = int((perf_counter() - start) * 1000)
    return JSONResponse(
        status_code=200,
        content=to_success({"ok": True, "latency_ms": latency_ms}),
    )
