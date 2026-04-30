"""get_three_major_investors — cache-first chip-flow fetcher.

Spec: openspec/changes/chip-data-skill/specs/chip-data-skill/spec.md
"""

from __future__ import annotations

import re
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ohmystock.chip.cache import (
    aggregate_three_major,
    init_chip_schema,
    insert_three_major_rows,
    select_three_major_rows,
)
from ohmystock.config import Settings

CODE_INVALID_INPUT = "INVALID_INPUT"
CODE_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
CODE_RATE_LIMIT = "RATE_LIMIT"
CODE_UPSTREAM_ERROR = "UPSTREAM_ERROR"
CODE_AUTH_FAILED = "AUTH_FAILED"

_TPE_TZ = timezone(timedelta(hours=8))
_SYMBOL_RE = re.compile(r"^\d{4,6}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def get_three_major_investors(
    symbol: str,
    days: int = 30,
    end_date: str | None = None,
    *,
    _conn: sqlite3.Connection | None = None,
    _client: Any | None = None,
    _today: str | None = None,
) -> dict:
    started = time.perf_counter()
    try:
        err = _validate_inputs(symbol, days, end_date)
        if err is not None:
            return _error_envelope(CODE_INVALID_INPUT, err, False, started)

        resolved_end = end_date or (_today or _today_iso())
        wanted = _business_day_range(resolved_end, days)

        owns_conn = _conn is None
        conn = _conn if _conn is not None else _open_db()
        try:
            init_chip_schema(conn)
            cached = select_three_major_rows(conn, symbol, wanted[0], wanted[-1])
            cached_dates = {row["date"] for row in cached}
            missing = [d for d in wanted if d not in cached_dates]

            error_code: str | None = None
            error_msg = ""

            if missing:
                client = _client if _client is not None else _make_client()
                fetched_at = datetime.now(_TPE_TZ).isoformat(timespec="seconds")
                try:
                    raw = client.get_institutional_investors_buy_sell(
                        symbol, missing[0], missing[-1]
                    )
                except Exception as exc:
                    error_code, _ = _classify_exception(exc)
                    error_msg = f"finmind: {exc}"
                else:
                    normalised = aggregate_three_major(raw)
                    if normalised:
                        insert_three_major_rows(
                            conn, normalised, "finmind", fetched_at
                        )

            final_rows = select_three_major_rows(conn, symbol, wanted[0], wanted[-1])
        finally:
            if owns_conn:
                conn.close()

        if final_rows:
            return _success_envelope(final_rows, started)

        if error_code is None:
            return _error_envelope(
                CODE_DATA_UNAVAILABLE,
                f"no chip data for {symbol} in {wanted[0]}..{wanted[-1]}",
                False,
                started,
            )
        retriable = error_code in {CODE_RATE_LIMIT, CODE_UPSTREAM_ERROR}
        return _error_envelope(error_code, error_msg, retriable, started)
    except Exception as exc:
        return _error_envelope(
            CODE_UPSTREAM_ERROR, f"unexpected: {exc}", True, started
        )


def _validate_inputs(symbol: str, days: int, end_date: str | None) -> str | None:
    if not isinstance(symbol, str) or not _SYMBOL_RE.match(symbol):
        return f"symbol must be 4-6 digits, got {symbol!r}"
    if not isinstance(days, int) or isinstance(days, bool) or days <= 0 or days > 5000:
        return f"days must be a positive int <= 5000, got {days!r}"
    if end_date is not None:
        if not isinstance(end_date, str) or not _DATE_RE.match(end_date):
            return f"end_date must match YYYY-MM-DD, got {end_date!r}"
        try:
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return f"end_date is not a valid date: {end_date!r}"
    return None


def _classify_exception(exc: BaseException) -> tuple[str, bool]:
    msg = str(exc).lower()
    if "429" in msg or "quota" in msg or "rate limit" in msg:
        return CODE_RATE_LIMIT, True
    if "401" in msg or "403" in msg or "unauthorized" in msg or "forbidden" in msg:
        return CODE_AUTH_FAILED, False
    return CODE_UPSTREAM_ERROR, True


def _business_day_range(end_date: str, days: int) -> list[str]:
    cursor = datetime.strptime(end_date, "%Y-%m-%d").date()
    out: list[date] = []
    while len(out) < days:
        if cursor.weekday() < 5:  # Mon-Fri
            out.append(cursor)
        cursor -= timedelta(days=1)
    out.reverse()
    return [d.isoformat() for d in out]


def _open_db() -> sqlite3.Connection:
    path = Path(Settings().ohmystock_db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _make_client() -> Any:
    from ohmystock.data.finmind_client import FinMindClient

    return FinMindClient()


def _today_iso() -> str:
    return datetime.now(_TPE_TZ).date().isoformat()


def _to_lots(shares: int) -> int:
    """Convert shares to 張 (1 張 = 1000 shares). Truncates toward zero."""
    if shares >= 0:
        return shares // 1000
    return -((-shares) // 1000)


def _success_envelope(rows: list[dict[str, Any]], started: float) -> dict:
    out_rows = [
        {
            "date": r["date"],
            "foreign_net": _to_lots(r["foreign_net"]),
            "invest_trust_net": _to_lots(r["invest_trust_net"]),
            "prop_dealer_net": _to_lots(r["prop_dealer_net"]),
        }
        for r in rows
    ]
    return {
        "ok": True,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "data": {"rows": out_rows},
        "error": None,
    }


def _error_envelope(code: str, message: str, retriable: bool, started: float) -> dict:
    return {
        "ok": False,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "data": None,
        "error": {"code": code, "message": message, "retriable": retriable},
    }
