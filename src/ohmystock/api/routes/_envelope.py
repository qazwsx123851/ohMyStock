"""Success / error envelope helpers shared by every admin action endpoint.

All endpoints in this capability return JSON of one of two shapes:

* Success: ``{"ok": true, "data": <dict>}``
* Error: ``{"ok": false, "error": {"code": <snake_case>, "message": <str>, ...}}``

``map_exception_to_envelope`` centralises the (HTTP status, error code)
mapping defined in design.md Decision 2. The fallback ``internal_error``
deliberately strips the original message — internal exceptions can carry
SQL fragments, absolute paths, or stack-trace snippets that must not
escape to the client (spec §「端點不洩漏內部路徑或 settings 值」).

Spec: openspec/changes/server-action-endpoints-v0/specs/server-action-endpoints/spec.md
"""

from __future__ import annotations

from typing import Any

from ohmystock.api.auth import AuthError
from ohmystock.exit_engine.evaluator import ExitEngineError
from ohmystock.safety.confirm_gate import ConfirmGateError


_GENERIC_INTERNAL_MESSAGE = "internal server error"


def to_success(data: dict[str, Any]) -> dict[str, Any]:
    """Build the success envelope. ``data`` is returned as-is, by reference."""

    return {"ok": True, "data": data}


def to_error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    """Build the error envelope. Optional ``extra`` keys are merged into ``error``."""

    error: dict[str, Any] = {"code": code, "message": message}
    error.update(extra)
    return {"ok": False, "error": error}


def map_exception_to_envelope(exc: BaseException) -> tuple[int, dict[str, Any]]:
    """Map a raised exception to ``(http_status, envelope)``.

    The mapping table mirrors design.md Decision 2. Unknown exceptions
    collapse to a generic 500 ``internal_error`` envelope without leaking
    the original message — see spec scenarios about path/SQL/traceback
    redaction.
    """

    if isinstance(exc, AuthError):
        return 401, to_error(exc.code, exc.message)

    if isinstance(exc, ConfirmGateError):
        if exc.code == "not_found":
            return 404, to_error("not_found", str(exc))
        if exc.code == "not_pending":
            return 409, to_error("not_pending", str(exc))
        if exc.code == "payload_invalid":
            return 409, to_error("payload_invalid", str(exc))
        if exc.code == "qty_exceeds_notional_limit":
            return 409, to_error(
                "qty_exceeds_notional_limit", str(exc), **exc.extra
            )
        if exc.code == "broker_failed":
            return 502, to_error("broker_failed", str(exc))
        return 500, to_error("internal_error", _GENERIC_INTERNAL_MESSAGE)

    if isinstance(exc, ExitEngineError):
        if exc.code == "market_data_unavailable":
            return 503, to_error(
                "market_data_unavailable",
                str(exc),
                failed_symbols=list(exc.failed_symbols),
            )
        return 500, to_error("internal_error", _GENERIC_INTERNAL_MESSAGE)

    if isinstance(exc, ValueError):
        return 400, to_error("invalid_input", str(exc))

    return 500, to_error("internal_error", _GENERIC_INTERNAL_MESSAGE)


_SCREENER_CODE_MAP: dict[str, tuple[int, str]] = {
    "INVALID_INPUT": (400, "invalid_input"),
    "DATA_UNAVAILABLE": (503, "data_unavailable"),
    "RATE_LIMIT": (429, "rate_limit"),
    "AUTH_FAILED": (502, "auth_failed"),
    "UPSTREAM_ERROR": (502, "upstream_error"),
}


def screener_envelope_to_http(
    screener_envelope: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Translate ``screen_universe()``'s envelope to ``(http_status, body)``.

    Success path returns 200 + ``{"ok": true, "data": {...}}`` where ``data``
    inlines ``elapsed_ms`` next to ``asof_date_used`` and ``candidates``.

    Error envelopes use the screener's UPPERCASE codes
    (``INVALID_INPUT``/``DATA_UNAVAILABLE``/``UPSTREAM_ERROR``/``RATE_LIMIT``/
    ``AUTH_FAILED``) which we normalise to snake_case and map per
    design.md Decision 2.
    """

    if screener_envelope.get("ok"):
        data = dict(screener_envelope.get("data") or {})
        elapsed_ms = screener_envelope.get("elapsed_ms")
        if elapsed_ms is not None:
            data["elapsed_ms"] = elapsed_ms
        return 200, to_success(data)

    err = screener_envelope.get("error") or {}
    raw_code = (err.get("code") or "UPSTREAM_ERROR").upper()
    message = err.get("message") or "screener failed"

    status, snake_code = _SCREENER_CODE_MAP.get(
        raw_code, (502, "upstream_error")
    )
    return status, to_error(snake_code, message)
