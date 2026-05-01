"""get_kline orchestrator: cache-first daily OHLCV with adapter fallback.

Spec: openspec/changes/market-data-fetch-cache/specs/market-data-cache/spec.md
"""

from __future__ import annotations

import re
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ohmystock.config import Settings
from ohmystock.data.cache import init_market_data_schema, insert_bars, select_bars
from ohmystock.data.sources.base import BarRow

_VALID_PERIODS = {"1d"}
_ADAPTERS_ORDER = ("finmind", "twstock", "yfinance")

CODE_INVALID_INPUT = "INVALID_INPUT"
CODE_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
CODE_RATE_LIMIT = "RATE_LIMIT"
CODE_UPSTREAM_ERROR = "UPSTREAM_ERROR"
CODE_AUTH_FAILED = "AUTH_FAILED"

# Higher number wins when multiple adapters fail with different classifications.
_CODE_PRIORITY = {
    CODE_AUTH_FAILED: 3,
    CODE_RATE_LIMIT: 2,
    CODE_UPSTREAM_ERROR: 1,
}

_TPE_TZ = timezone(timedelta(hours=8))
_SYMBOL_RE = re.compile(r"^(?:[A-Z]{3,6}|\d{4,6})$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def get_kline(
    symbol: str,
    period: str = "1d",
    bars: int = 250,
    end_date: str | None = None,
    *,
    _conn: sqlite3.Connection | None = None,
    _adapters: list[Any] | None = None,
    _today: str | None = None,
) -> dict:
    started = time.perf_counter()
    try:
        err = _validate_inputs(symbol, period, bars, end_date)
        if err is not None:
            return _error_envelope(CODE_INVALID_INPUT, err, False, started)

        resolved_end = end_date or (_today or _today_iso())
        wanted = _business_day_range(resolved_end, bars)

        owns_conn = _conn is None
        conn = _conn if _conn is not None else _open_db()
        try:
            cached = select_bars(conn, symbol, wanted[0], wanted[-1])
            cached_dates = {row["ts"] for row in cached}
            missing = [d for d in wanted if d not in cached_dates]

            error_code: str | None = None
            error_msg = ""

            if missing:
                fetch_start, fetch_end = missing[0], missing[-1]
                adapters = _adapters if _adapters is not None else _make_adapters()
                fetched_at = datetime.now(_TPE_TZ).isoformat(timespec="seconds")
                for adapter in adapters:
                    try:
                        rows = adapter.fetch_daily(symbol, fetch_start, fetch_end)
                    except Exception as exc:
                        code, _ = _classify_exception(adapter.name, exc)
                        if error_code is None or _CODE_PRIORITY.get(code, 0) > _CODE_PRIORITY.get(error_code, 0):
                            error_code = code
                            error_msg = f"{adapter.name}: {exc}"
                        continue
                    if rows:
                        insert_bars(conn, symbol, rows, adapter.name, fetched_at)
                        error_code = None
                        break

            final_rows = select_bars(conn, symbol, wanted[0], wanted[-1])
        finally:
            if owns_conn:
                conn.close()

        missing_after_fetch = _missing_dates(wanted, [row["ts"] for row in final_rows])
        if not missing_after_fetch:
            return _success_envelope(final_rows, started)

        if error_code is None:
            return _error_envelope(
                CODE_DATA_UNAVAILABLE,
                f"missing data for {symbol} in {wanted[0]}..{wanted[-1]}: "
                f"{_format_missing_dates(missing_after_fetch)}",
                False,
                started,
            )
        retriable = error_code in {CODE_RATE_LIMIT, CODE_UPSTREAM_ERROR}
        return _error_envelope(error_code, error_msg, retriable, started)
    except Exception as exc:
        return _error_envelope(
            CODE_UPSTREAM_ERROR, f"unexpected: {exc}", True, started
        )


def _validate_inputs(
    symbol: str, period: str, bars: int, end_date: str | None
) -> str | None:
    if not isinstance(symbol, str) or not _SYMBOL_RE.match(symbol):
        return (
            f"symbol must be 4-6 digits or a 3-6 letter index code (e.g. TAIEX), "
            f"got {symbol!r}"
        )
    if period not in _VALID_PERIODS:
        return f"period must be one of {sorted(_VALID_PERIODS)}, got {period!r}"
    if not isinstance(bars, int) or isinstance(bars, bool) or bars <= 0 or bars > 5000:
        return f"bars must be a positive int <= 5000, got {bars!r}"
    if end_date is not None:
        if not isinstance(end_date, str) or not _DATE_RE.match(end_date):
            return f"end_date must match YYYY-MM-DD, got {end_date!r}"
        try:
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return f"end_date is not a valid date: {end_date!r}"
    return None


def _classify_exception(adapter_name: str, exc: BaseException) -> tuple[str, bool]:
    msg = str(exc).lower()
    if "429" in msg or "quota" in msg or "rate limit" in msg:
        return CODE_RATE_LIMIT, True
    if "401" in msg or "403" in msg or "unauthorized" in msg or "forbidden" in msg:
        return CODE_AUTH_FAILED, False
    return CODE_UPSTREAM_ERROR, True


def _business_day_range(end_date: str, bars: int) -> list[str]:
    cursor = datetime.strptime(end_date, "%Y-%m-%d").date()
    out: list[date] = []
    while len(out) < bars:
        if cursor.weekday() < 5:  # Mon-Fri
            out.append(cursor)
        cursor -= timedelta(days=1)
    out.reverse()
    return [d.isoformat() for d in out]


def _missing_dates(wanted: list[str], actual: list[str]) -> list[str]:
    actual_dates = set(actual)
    return [d for d in wanted if d not in actual_dates]


def _format_missing_dates(missing: list[str]) -> str:
    if len(missing) <= 5:
        return ", ".join(missing)
    return ", ".join(missing[:5]) + f", ... (+{len(missing) - 5} more)"


def _open_db() -> sqlite3.Connection:
    path = Path(Settings().ohmystock_db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    init_market_data_schema(conn)
    return conn


def _make_adapters() -> list[Any]:
    from ohmystock.data.sources.finmind import FinMindSource
    from ohmystock.data.sources.twstock import TwstockSource
    from ohmystock.data.sources.yfinance import YFinanceSource

    return [FinMindSource(), TwstockSource(), YFinanceSource()]


def _today_iso() -> str:
    return datetime.now(_TPE_TZ).date().isoformat()


def _success_envelope(rows: list[BarRow], started: float) -> dict:
    return {
        "ok": True,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "data": {"bars": list(rows)},
        "error": None,
    }


def _error_envelope(code: str, message: str, retriable: bool, started: float) -> dict:
    return {
        "ok": False,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "data": None,
        "error": {"code": code, "message": message, "retriable": retriable},
    }
