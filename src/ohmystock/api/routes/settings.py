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

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ohmystock.api.auth import require_admin
from ohmystock.api.routes._deps import get_settings_dep
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_success,
)
from ohmystock.config import Settings


router = APIRouter(dependencies=[Depends(require_admin)])


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


@router.get("/api/admin/settings")
def get_settings(
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:
    try:
        data = _redact(settings)
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    return JSONResponse(status_code=200, content=to_success(data))
