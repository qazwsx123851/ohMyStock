"""Unit tests for ``ohmystock.api.routes._envelope`` mapping table.

Covers all 10 rows of design.md Decision 2 plus the no-leak guarantees
from spec §「端點不洩漏內部路徑或 settings 值」.
"""

from __future__ import annotations

import json

import pytest

from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    screener_envelope_to_http,
    to_error,
    to_success,
)
from ohmystock.exit_engine.evaluator import ExitEngineError
from ohmystock.safety.confirm_gate import ConfirmGateError


# ---------------------------------------------------------------------------
# to_success / to_error
# ---------------------------------------------------------------------------


def test_to_success_shape() -> None:
    env = to_success({"foo": "bar"})
    assert env == {"ok": True, "data": {"foo": "bar"}}


def test_to_error_shape() -> None:
    env = to_error("not_found", "missing")
    assert env == {"ok": False, "error": {"code": "not_found", "message": "missing"}}


def test_to_error_merges_extra_into_error() -> None:
    env = to_error("market_data_unavailable", "msg", failed_symbols=["2330"])
    assert env["ok"] is False
    assert env["error"]["code"] == "market_data_unavailable"
    assert env["error"]["failed_symbols"] == ["2330"]


# ---------------------------------------------------------------------------
# map_exception_to_envelope (4 ConfirmGateError + 1 ExitEngineError +
# ValueError + fallback)
# ---------------------------------------------------------------------------


def test_confirm_gate_not_found_maps_to_404() -> None:
    status, env = map_exception_to_envelope(
        ConfirmGateError("not_found", "no entry for d_xxx")
    )
    assert status == 404
    assert env["ok"] is False
    assert env["error"]["code"] == "not_found"
    assert env["error"]["message"]


def test_confirm_gate_not_pending_maps_to_409() -> None:
    status, env = map_exception_to_envelope(
        ConfirmGateError("not_pending", "entry status is 'confirmed'")
    )
    assert status == 409
    assert env["error"]["code"] == "not_pending"


def test_confirm_gate_payload_invalid_maps_to_409() -> None:
    status, env = map_exception_to_envelope(
        ConfirmGateError("payload_invalid", "missing final_sizing_pct")
    )
    assert status == 409
    assert env["error"]["code"] == "payload_invalid"


def test_confirm_gate_broker_failed_maps_to_502() -> None:
    status, env = map_exception_to_envelope(
        ConfirmGateError("broker_failed", "paper broker rejected")
    )
    assert status == 502
    assert env["error"]["code"] == "broker_failed"


def test_exit_engine_market_data_unavailable_maps_to_503_with_failed_symbols() -> None:
    status, env = map_exception_to_envelope(
        ExitEngineError(
            "market_data_unavailable",
            "lookup failed",
            failed_symbols=["2330", "2454"],
        )
    )
    assert status == 503
    assert env["error"]["code"] == "market_data_unavailable"
    assert env["error"]["failed_symbols"] == ["2330", "2454"]


def test_value_error_maps_to_400_invalid_input() -> None:
    status, env = map_exception_to_envelope(ValueError("bad date"))
    assert status == 400
    assert env["error"]["code"] == "invalid_input"
    assert env["error"]["message"] == "bad date"


def test_unknown_exception_falls_back_to_500_internal_error() -> None:
    status, env = map_exception_to_envelope(RuntimeError("boom: SELECT * FROM x"))
    assert status == 500
    assert env["error"]["code"] == "internal_error"
    assert "SELECT" not in env["error"]["message"]
    assert "boom" not in env["error"]["message"]


def test_generic_exception_message_is_redacted() -> None:
    status, env = map_exception_to_envelope(
        Exception('File "/Users/mark/secret.py", line 42, in foo')
    )
    assert status == 500
    assert env["error"]["code"] == "internal_error"
    assert "/Users/" not in env["error"]["message"]
    assert "File \"" not in env["error"]["message"]


# ---------------------------------------------------------------------------
# screener_envelope_to_http (3 error rows + success)
# ---------------------------------------------------------------------------


def test_screener_envelope_success_returns_200_with_elapsed_ms() -> None:
    src = {
        "ok": True,
        "elapsed_ms": 12,
        "data": {"asof_date_used": "2026-05-02", "candidates": []},
        "error": None,
    }
    status, env = screener_envelope_to_http(src)
    assert status == 200
    assert env["ok"] is True
    assert env["data"]["asof_date_used"] == "2026-05-02"
    assert env["data"]["candidates"] == []
    assert env["data"]["elapsed_ms"] == 12


def test_screener_envelope_invalid_input_maps_to_400() -> None:
    src = {
        "ok": False,
        "elapsed_ms": 0,
        "data": None,
        "error": {"code": "INVALID_INPUT", "message": "bad universe", "retriable": False},
    }
    status, env = screener_envelope_to_http(src)
    assert status == 400
    assert env["error"]["code"] == "invalid_input"


def test_screener_envelope_data_unavailable_maps_to_503() -> None:
    src = {
        "ok": False,
        "elapsed_ms": 0,
        "data": None,
        "error": {"code": "DATA_UNAVAILABLE", "message": "no snapshot", "retriable": False},
    }
    status, env = screener_envelope_to_http(src)
    assert status == 503
    assert env["error"]["code"] == "data_unavailable"


def test_screener_envelope_upstream_error_maps_to_502() -> None:
    src = {
        "ok": False,
        "elapsed_ms": 0,
        "data": None,
        "error": {"code": "UPSTREAM_ERROR", "message": "finmind: timeout", "retriable": True},
    }
    status, env = screener_envelope_to_http(src)
    assert status == 502
    assert env["error"]["code"] == "upstream_error"


def test_screener_envelope_rate_limit_maps_to_429() -> None:
    src = {
        "ok": False,
        "elapsed_ms": 0,
        "data": None,
        "error": {"code": "RATE_LIMIT", "message": "too many", "retriable": True},
    }
    status, env = screener_envelope_to_http(src)
    assert status == 429
    assert env["error"]["code"] == "rate_limit"


def test_screener_envelope_auth_failed_maps_to_502() -> None:
    src = {
        "ok": False,
        "elapsed_ms": 0,
        "data": None,
        "error": {"code": "AUTH_FAILED", "message": "bad token", "retriable": False},
    }
    status, env = screener_envelope_to_http(src)
    assert status == 502
    assert env["error"]["code"] == "auth_failed"


# ---------------------------------------------------------------------------
# Spec §「端點不洩漏內部路徑或 settings 值」 guarantees on envelopes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError(
            'Traceback (most recent call last):\n  File "/Users/mark/x.py", line 1'
        ),
        Exception("near 'SELECT': syntax error in INSERT INTO journal_entries"),
        Exception("OHMYSTOCK_DB_PATH=/Users/mark/.ohmystock/journal.db"),
    ],
)
def test_internal_error_envelope_never_leaks_sensitive_substrings(
    exc: BaseException,
) -> None:
    status, env = map_exception_to_envelope(exc)
    assert status == 500
    body = json.dumps(env)
    for needle in ("/Users/", "/home/", "C:\\", "SELECT", "INSERT", "Traceback", "File \""):
        assert needle not in body, f"leaked substring: {needle!r}"
