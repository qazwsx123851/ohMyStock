"""GET /api/admin/market/symbols/{symbol} — per-symbol market aggregator.

One round-trip composes ``bars_daily`` slice, derived ``quote``, latest
``rs_rating_cache`` value, fresh SEPA stage classification, last 5
trading days of three-major institutional flows, and the most recent
pattern-detection rows from ``journal_entries`` (capped to 30 calendar
days, 20 rows).

Fail-soft: any sub-source missing data degrades to ``null`` / ``[]``;
only a missing ``bars_daily`` slice yields 404 ``market_symbol_not_found``.

Spec: openspec/changes/web-admin-market-pages/specs/admin-market-symbol-endpoint/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from ohmystock.api.auth import require_admin
from ohmystock.api.routes._deps import get_db
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_error,
    to_success,
)
from ohmystock.chip.cache import init_chip_schema, select_three_major_rows
from ohmystock.data.cache import init_market_data_schema, select_bars
from ohmystock.data.sources.base import BarRow
from ohmystock.sepa.rs import init_schema as init_rs_schema
from ohmystock.sepa.stage import classify_stage


router = APIRouter(dependencies=[Depends(require_admin)])

_TPE = ZoneInfo("Asia/Taipei")
_DEFAULT_DAYS = 60
_MAX_DAYS = 252
_INSTITUTIONAL_TRADING_DAYS = 5
_INSTITUTIONAL_CAL_WINDOW_DAYS = 14
_PATTERN_CAL_WINDOW_DAYS = 30
_PATTERN_LIMIT = 20


class Quote(BaseModel):
    model_config = ConfigDict(frozen=True)

    price: float
    change: float | None
    change_pct: float | None
    volume: int
    asof: str


class MarketBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class RsRating(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: int
    asof: str


class SepaInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: int
    since: str | None


class InstitutionalRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: str
    foreign: int
    trust: int
    dealer: int
    total: int


class RecentPattern(BaseModel):
    model_config = ConfigDict(frozen=True)

    ts: str
    pattern: str
    score: float
    outcome: str


class MarketSymbolData(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    quote: Quote
    bars_daily: list[MarketBar]
    rs: RsRating | None
    sepa: SepaInfo | None
    institutional: list[InstitutionalRow]
    recent_patterns: list[RecentPattern]


class _InvalidDaysError(Exception):
    """Sentinel for days out-of-range; mapped to 400 invalid_days."""


def _validate_days(days: int) -> int:
    if days < 1 or days > _MAX_DAYS:
        raise _InvalidDaysError(
            f"days must be in [1, {_MAX_DAYS}], got {days}"
        )
    return days


def _to_lots(shares: int) -> int:
    """Convert shares to 張 (1 張 = 1000 shares); truncate toward zero."""
    if shares >= 0:
        return shares // 1000
    return -((-shares) // 1000)


def _fetch_bars(
    conn: sqlite3.Connection, symbol: str, days: int, today: date
) -> list[BarRow]:
    init_market_data_schema(conn)
    calendar_window = max(int(days * 1.6) + 14, days + 14)
    start = today - timedelta(days=calendar_window)
    bars = select_bars(conn, symbol, start.isoformat(), today.isoformat())
    return bars[-days:]


def _build_quote(bars: list[BarRow]) -> Quote:
    last = bars[-1]
    price = float(last["c"])
    volume = int(last["v"])
    if len(bars) >= 2:
        prev_close = float(bars[-2]["c"])
        change: float | None = price - prev_close
        change_pct: float | None = (
            (change / prev_close) if prev_close != 0 else None
        )
    else:
        change = None
        change_pct = None
    return Quote(
        price=price,
        change=change,
        change_pct=change_pct,
        volume=volume,
        asof=str(last["ts"]),
    )


def _build_market_bars(bars: list[BarRow]) -> list[MarketBar]:
    return [
        MarketBar(
            date=str(b["ts"]),
            open=float(b["o"]),
            high=float(b["h"]),
            low=float(b["l"]),
            close=float(b["c"]),
            volume=int(b["v"]),
        )
        for b in bars
    ]


def _fetch_rs(conn: sqlite3.Connection, symbol: str) -> RsRating | None:
    init_rs_schema(conn)
    row = conn.execute(
        "SELECT asof_date, rs_rating FROM rs_rating_cache "
        "WHERE symbol = ? ORDER BY asof_date DESC LIMIT 1",
        (symbol,),
    ).fetchone()
    if row is None:
        return None
    return RsRating(value=int(row[1]), asof=str(row[0]))


def _classify_sepa(bars: list[BarRow]) -> SepaInfo | None:
    try:
        result = classify_stage(bars)
    except Exception:  # noqa: BLE001 — fail-soft per spec D7
        return None
    if result is None:
        return None
    return SepaInfo(stage=int(result.stage), since=None)


def _fetch_institutional(
    conn: sqlite3.Connection, symbol: str, today: date
) -> list[InstitutionalRow]:
    init_chip_schema(conn)
    start = today - timedelta(days=_INSTITUTIONAL_CAL_WINDOW_DAYS)
    raw = select_three_major_rows(
        conn, symbol, start.isoformat(), today.isoformat()
    )
    if not raw:
        return []
    last_n = raw[-_INSTITUTIONAL_TRADING_DAYS:]
    out: list[InstitutionalRow] = []
    for r in last_n:
        f = _to_lots(int(r["foreign_net"]))
        t = _to_lots(int(r["invest_trust_net"]))
        d = _to_lots(int(r["prop_dealer_net"]))
        out.append(
            InstitutionalRow(
                date=str(r["date"]),
                foreign=f,
                trust=t,
                dealer=d,
                total=f + t + d,
            )
        )
    return out


def _parse_pattern_payload(payload_json: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(payload_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("pattern") is None:
        return None
    return payload


def _format_outcome(pct: float, suffix: str) -> str:
    sign = "+" if pct >= 0 else "-"
    return f"{sign}{abs(pct):.1f}% {suffix}"


def _compute_outcome(
    conn: sqlite3.Connection,
    symbol: str,
    pattern_ts: str,
    last_close: float | None,
) -> str:
    entry = conn.execute(
        "SELECT decision_id, payload_json, created_at FROM journal_entries "
        "WHERE symbol = ? AND kind = 'entry' AND created_at > ? "
        "ORDER BY created_at ASC LIMIT 1",
        (symbol, pattern_ts),
    ).fetchone()
    if entry is None:
        return "未進場"
    decision_id, entry_payload_json, _entry_ts = entry
    try:
        entry_payload = json.loads(entry_payload_json) or {}
    except (TypeError, ValueError):
        entry_payload = {}
    entry_price_raw = entry_payload.get("actual_entry_price")
    if entry_price_raw is None:
        return "未進場"
    try:
        entry_price = float(entry_price_raw)
    except (TypeError, ValueError):
        return "未進場"
    if entry_price <= 0:
        return "未進場"

    exit_row = conn.execute(
        "SELECT payload_json FROM journal_entries "
        "WHERE decision_id = ? AND kind = 'exit' "
        "ORDER BY created_at ASC LIMIT 1",
        (str(decision_id),),
    ).fetchone()
    if exit_row is not None:
        try:
            exit_payload = json.loads(exit_row[0]) or {}
        except (TypeError, ValueError):
            exit_payload = {}
        exit_price_raw = exit_payload.get("actual_exit_price")
        try:
            exit_price = (
                float(exit_price_raw) if exit_price_raw is not None else None
            )
        except (TypeError, ValueError):
            exit_price = None
        if exit_price is not None:
            pct = (exit_price - entry_price) / entry_price * 100.0
            return _format_outcome(pct, "出場")

    if last_close is None:
        return "未進場"
    pct = (last_close - entry_price) / entry_price * 100.0
    return _format_outcome(pct, "持有中")


def _fetch_recent_patterns(
    conn: sqlite3.Connection,
    symbol: str,
    today: date,
    last_close: float | None,
) -> list[RecentPattern]:
    start = today - timedelta(days=_PATTERN_CAL_WINDOW_DAYS)
    cursor = conn.execute(
        "SELECT created_at, payload_json FROM journal_entries "
        "WHERE symbol = ? "
        "AND substr(created_at, 1, 10) >= ? "
        "AND substr(created_at, 1, 10) <= ? "
        "AND json_extract(payload_json, '$.pattern') IS NOT NULL "
        "ORDER BY created_at DESC LIMIT ?",
        (symbol, start.isoformat(), today.isoformat(), _PATTERN_LIMIT),
    )
    rows = cursor.fetchall()
    out: list[RecentPattern] = []
    for created_at, payload_json in rows:
        payload = _parse_pattern_payload(str(payload_json))
        if payload is None:
            continue
        pattern_name = str(payload.get("pattern") or "")
        score_raw = payload.get("score", 0)
        try:
            score_val = float(score_raw)
        except (TypeError, ValueError):
            score_val = 0.0
        outcome = _compute_outcome(
            conn, symbol, str(created_at), last_close
        )
        out.append(
            RecentPattern(
                ts=str(created_at),
                pattern=pattern_name,
                score=score_val,
                outcome=outcome,
            )
        )
    return out


def aggregate_symbol(
    conn: sqlite3.Connection,
    symbol: str,
    days: int = _DEFAULT_DAYS,
    *,
    today: date | None = None,
) -> MarketSymbolData | None:
    """Compose the full ``MarketSymbolData`` aggregate for one symbol.

    Returns ``None`` if no ``bars_daily`` rows exist (the route maps that
    to 404 ``market_symbol_not_found``; other callers — e.g. the chat
    tool wrapper — translate it to their own ``not_found`` shape).

    ``days`` is validated against ``_validate_days`` so invalid values
    surface as :class:`_InvalidDaysError` before any DB I/O.
    """

    days_v = _validate_days(int(days))
    today_v = today if today is not None else datetime.now(_TPE).date()
    bars = _fetch_bars(conn, symbol, days_v, today_v)
    if not bars:
        return None

    last_close = float(bars[-1]["c"])
    return MarketSymbolData(
        symbol=symbol,
        quote=_build_quote(bars),
        bars_daily=_build_market_bars(bars),
        rs=_fetch_rs(conn, symbol),
        sepa=_classify_sepa(bars),
        institutional=_fetch_institutional(conn, symbol, today_v),
        recent_patterns=_fetch_recent_patterns(
            conn, symbol, today_v, last_close
        ),
    )


@router.get("/api/admin/market/symbols/{symbol}")
def get_market_symbol(
    symbol: str,
    days: int = Query(default=_DEFAULT_DAYS),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    try:
        try:
            data = aggregate_symbol(conn, symbol, days)
        except _InvalidDaysError as exc:
            return JSONResponse(
                status_code=400,
                content=to_error("invalid_days", str(exc)),
            )

        if data is None:
            return JSONResponse(
                status_code=404,
                content=to_error(
                    "market_symbol_not_found",
                    f"no bars_daily rows for symbol {symbol!r}",
                ),
            )
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    return JSONResponse(
        status_code=200,
        content=to_success(data.model_dump(mode="json")),
    )
