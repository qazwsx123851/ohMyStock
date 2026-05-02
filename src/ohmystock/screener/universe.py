"""screen_universe — TW universe selector + structural filters.

Spec: openspec/changes/screener-tw-universe/specs/screener-tw-universe/spec.md
"""

from __future__ import annotations

import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ohmystock.config import Settings
from ohmystock.eventbus import Agent, Event, EventType, safe_emit_sync
from ohmystock.screener.cache import (
    aggregate_universe_rows,
    init_universe_schema,
    insert_universe_rows,
    latest_asof_within,
    select_universe_rows,
)
from ohmystock.screener.filters import apply_negative_filter, apply_volume_filter

CODE_INVALID_INPUT = "INVALID_INPUT"
CODE_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
CODE_RATE_LIMIT = "RATE_LIMIT"
CODE_UPSTREAM_ERROR = "UPSTREAM_ERROR"
CODE_AUTH_FAILED = "AUTH_FAILED"

_VALID_UNIVERSES = {"TWSE", "OTC", "TWSE+OTC", "custom"}
_VALID_FILTER_KINDS = {"negative_filter", "volume_filter"}
_TPE_TZ = timezone(timedelta(hours=8))
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CUSTOM_SYMBOL_RE = re.compile(r"^\d{4,6}(KY)?$")

# Sentinel distinguishing "caller did not pass _client" (default → build a real
# FinMindClient) from "caller passed _client=None" (explicitly no upstream).
# The spec scenarios pass _client=<stub> for present and rely on no-client-wired
# semantics; tests use _client=None to assert DATA_UNAVAILABLE behaviour.
_OMITTED: Any = object()


def screen_universe(
    universe: str,
    custom_symbols: list[str] | None = None,
    filters: list[dict[str, Any]] | None = None,
    asof_date: str | None = None,
    *,
    _conn: sqlite3.Connection | None = None,
    _client: Any = _OMITTED,
    _today: str | None = None,
) -> dict:
    started = time.perf_counter()
    try:
        err = _validate_inputs(universe, custom_symbols, filters, asof_date)
        if err is not None:
            return _error_envelope(CODE_INVALID_INPUT, err, False, started)

        requested = asof_date or (_today or _today_iso())

        owns_conn = _conn is None
        conn = _conn if _conn is not None else _open_db()
        try:
            init_universe_schema(conn)

            asof_used = _resolve_asof_date(conn, requested)

            if asof_used is None:
                client = _resolve_client(_client)
                if client is None:
                    return _error_envelope(
                        CODE_DATA_UNAVAILABLE,
                        f"no universe snapshot for {requested} and no upstream client available",
                        False,
                        started,
                    )
                fetched_at = datetime.now(_TPE_TZ).isoformat(timespec="seconds")
                try:
                    raw = client.get_taiwan_stock_info()
                except Exception as exc:
                    code, retriable = _classify_exception(exc)
                    return _error_envelope(
                        code, f"finmind: {exc}", retriable, started
                    )
                normalised = aggregate_universe_rows(raw, asof_date=requested)
                if not normalised:
                    return _error_envelope(
                        CODE_DATA_UNAVAILABLE,
                        f"upstream returned no rows for {requested}",
                        False,
                        started,
                    )
                insert_universe_rows(conn, normalised, "finmind", fetched_at)
                asof_used = requested

            market_filter = _market_filter_for(universe)
            rows = select_universe_rows(conn, asof_used, market_filter=market_filter)
            if universe == "custom":
                wanted = set(custom_symbols or [])
                rows = [r for r in rows if r["symbol"] in wanted]

            safe_emit_sync(
                Event(
                    event_type=EventType.SCREENER_STARTED,
                    agent=Agent.SCANNER,
                    payload={"universe_size": len(rows)},
                )
            )

            try:
                rows = _apply_filters(rows, filters or [], conn, asof_used)
            except _FilterError as fe:
                return _error_envelope(fe.code, fe.message, False, started)

            candidates = sorted(
                (
                    {
                        "symbol": r["symbol"],
                        "name": r["name"],
                        "sector": r["industry"],
                        "market": r["market"],
                    }
                    for r in rows
                ),
                key=lambda c: c["symbol"],
            )

            safe_emit_sync(
                Event(
                    event_type=EventType.SCREENER_COMPLETED,
                    agent=Agent.SCANNER,
                    payload={
                        "candidate_count": len(candidates),
                        "symbols": [c["symbol"] for c in candidates],
                    },
                )
            )

            return {
                "ok": True,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "data": {"asof_date_used": asof_used, "candidates": candidates},
                "error": None,
            }
        finally:
            if owns_conn:
                conn.close()
    except Exception as exc:
        return _error_envelope(
            CODE_UPSTREAM_ERROR, f"unexpected: {exc}", True, started
        )


# ---------- helpers ----------


class _FilterError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _validate_inputs(
    universe: str,
    custom_symbols: list[str] | None,
    filters: list[dict[str, Any]] | None,
    asof_date: str | None,
) -> str | None:
    if not isinstance(universe, str) or universe not in _VALID_UNIVERSES:
        return f"universe must be one of {sorted(_VALID_UNIVERSES)}, got {universe!r}"

    if universe == "custom":
        if not isinstance(custom_symbols, list) or not custom_symbols:
            return "custom_symbols must be a non-empty list when universe == 'custom'"
        for s in custom_symbols:
            if not isinstance(s, str) or not _CUSTOM_SYMBOL_RE.match(s):
                return f"invalid custom symbol {s!r}"
    else:
        if custom_symbols is not None:
            return "custom_symbols must be None when universe != 'custom'"

    if asof_date is not None:
        if not isinstance(asof_date, str) or not _DATE_RE.match(asof_date):
            return f"asof_date must match YYYY-MM-DD, got {asof_date!r}"
        try:
            datetime.strptime(asof_date, "%Y-%m-%d")
        except ValueError:
            return f"asof_date is not a real calendar date: {asof_date!r}"

    if filters is not None:
        if not isinstance(filters, list):
            return "filters must be a list of dicts"
        for f in filters:
            if not isinstance(f, dict) or "kind" not in f:
                return f"filter must be a dict with 'kind' key, got {f!r}"
            if f["kind"] not in _VALID_FILTER_KINDS:
                return f"unknown filter kind: {f['kind']!r}"

    return None


def _resolve_asof_date(conn: sqlite3.Connection, requested: str) -> str | None:
    """Return cached asof_date <= requested within 30d, else None for cache miss."""
    exact = conn.execute(
        "SELECT 1 FROM universe_daily WHERE asof_date = ? LIMIT 1",
        (requested,),
    ).fetchone()
    if exact is not None:
        return requested
    return latest_asof_within(conn, requested, lookback_days=30)


def _market_filter_for(universe: str) -> str | None:
    if universe == "TWSE":
        return "TWSE"
    if universe == "OTC":
        return "OTC"
    return None  # TWSE+OTC and custom: no market filter


def _apply_filters(
    rows: list[dict[str, Any]],
    filter_specs: list[dict[str, Any]],
    conn: sqlite3.Connection,
    asof_used: str,
) -> list[dict[str, Any]]:
    out = rows
    for spec in filter_specs:
        kind = spec["kind"]
        if kind == "negative_filter":
            exclude = spec.get("exclude", [])
            if not isinstance(exclude, list):
                raise _FilterError(
                    CODE_INVALID_INPUT,
                    f"negative_filter.exclude must be a list, got {exclude!r}",
                )
            try:
                out = apply_negative_filter(out, exclude)
            except ValueError as e:
                raise _FilterError(CODE_INVALID_INPUT, str(e)) from e
        elif kind == "volume_filter":
            min_avg = spec.get("min_avg_dollar_volume_5d")
            if (
                not isinstance(min_avg, int)
                or isinstance(min_avg, bool)
                or min_avg < 0
            ):
                raise _FilterError(
                    CODE_INVALID_INPUT,
                    "volume_filter.min_avg_dollar_volume_5d must be a non-negative int, "
                    f"got {min_avg!r}",
                )
            error_policy = spec.get("error_policy", "skip_missing")
            if error_policy not in {"skip_missing", "fail_fast"}:
                raise _FilterError(
                    CODE_INVALID_INPUT,
                    "volume_filter.error_policy must be 'skip_missing' or 'fail_fast', "
                    f"got {error_policy!r}",
                )
            try:
                out = apply_volume_filter(
                    out, conn, min_avg, asof_used, error_policy=error_policy
                )
            except ValueError as e:
                msg = str(e)
                if "data unavailable" in msg.lower():
                    raise _FilterError(CODE_DATA_UNAVAILABLE, msg) from e
                raise _FilterError(CODE_INVALID_INPUT, msg) from e
    return out


def _classify_exception(exc: BaseException) -> tuple[str, bool]:
    """Mirror chip.three_major._classify_exception (kept inline to avoid
    cross-importing chip internals)."""
    msg = str(exc).lower()
    if "429" in msg or "quota" in msg or "rate limit" in msg:
        return CODE_RATE_LIMIT, True
    if "401" in msg or "403" in msg or "unauthorized" in msg or "forbidden" in msg:
        return CODE_AUTH_FAILED, False
    return CODE_UPSTREAM_ERROR, True


def _resolve_client(_client: Any) -> Any | None:
    """Translate the test/production seam:

    - `_OMITTED` (default): build a real FinMindClient.
    - `None`: caller explicitly disabled the upstream client.
    - other value: use as-is (a stub or real client supplied by the caller).
    """
    if _client is _OMITTED:
        from ohmystock.data.finmind_client import FinMindClient

        return FinMindClient()
    return _client


def _open_db() -> sqlite3.Connection:
    path = Path(Settings().ohmystock_db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _today_iso() -> str:
    return datetime.now(_TPE_TZ).date().isoformat()


def _error_envelope(
    code: str, message: str, retriable: bool, started: float
) -> dict:
    return {
        "ok": False,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "data": None,
        "error": {"code": code, "message": message, "retriable": retriable},
    }
