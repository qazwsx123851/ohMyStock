"""TAIEX-derived MarketSnapshot for the swarm input assembler.

``compute_taiex_snapshot`` reads TAIEX daily bars via ``get_kline``,
evaluates the v1 Risk-Off condition (TAIEX vs MA60), and reads
``monthly_pnl_pct`` from the trade journal. Other Risk-Off signals
(SPY, VIX, FX, TAIFEX) are recorded in a diagnostics dict as
``"unknown"`` — the CLI surfaces them as warnings but they never flip
``risk_off`` to True on their own.

Spec: openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from ohmystock.config import Settings
from ohmystock.data.market_data import get_kline
from ohmystock.indicators import sma
from ohmystock.journal.repository import monthly_realized_pnl_pct
from ohmystock.swarm._adapters import MarketSnapshot
from ohmystock.swarm._errors import LiveProviderError


_TAIEX_SYMBOL = "TAIEX"
_BARS_REQUESTED = 80
_MA_PERIOD = 60
_MA_SLOPE_LOOKBACK = 5
_STALE_BUSINESS_DAYS = 5

_UNWIRED_SIGNALS: tuple[str, ...] = (
    "spy_5d_return",
    "vix",
    "twd_usd",
    "taifex_foreign_short",
)


def compute_taiex_snapshot(
    asof: str,
    *,
    conn: sqlite3.Connection | None = None,
    starting_equity: float | None = None,
) -> tuple[MarketSnapshot, dict[str, str]]:
    """Build the TAIEX-derived ``MarketSnapshot`` plus a diagnostics dict.

    ``conn`` (when provided) is used to read realized monthly P&L from
    the trade journal. When ``conn`` is ``None``, ``monthly_pnl_pct`` is
    reported as ``0.0`` (no closed trades visible).

    Raises ``LiveProviderError`` when TAIEX bars are missing or stale.
    """
    env = get_kline(_TAIEX_SYMBOL, bars=_BARS_REQUESTED, end_date=asof)
    if not env.get("ok"):
        err = env.get("error") or {}
        code = err.get("code", "UPSTREAM_ERROR")
        message = err.get("message", "get_kline failed")
        if code in ("INVALID_INPUT", "RATE_LIMIT"):
            code = "UPSTREAM_ERROR"
        raise LiveProviderError(
            code=code,
            message=f"TAIEX@{asof}: {message}",
        )

    bars = list(env["data"]["bars"])
    if not bars:
        raise LiveProviderError(
            code="DATA_UNAVAILABLE",
            message=f"TAIEX@{asof}: no bars returned by get_kline",
        )

    last_bar = bars[-1]
    last_ts = str(last_bar["ts"])
    if _business_days_between(last_ts, asof) > _STALE_BUSINESS_DAYS:
        raise LiveProviderError(
            code="STALE_DATA",
            message=(
                f"TAIEX last bar {last_ts} is more than "
                f"{_STALE_BUSINESS_DAYS} business days older than asof {asof}"
            ),
        )

    closes = [float(b["c"]) for b in bars]
    taiex_close = closes[-1]
    if len(closes) >= 2 and closes[-2] > 0:
        taiex_change_pct = (closes[-1] / closes[-2] - 1.0) * 100.0
    else:
        taiex_change_pct = 0.0

    risk_off = _evaluate_taiex_risk_off(closes)

    if starting_equity is None:
        starting_equity = float(Settings().starting_equity_twd)
    if conn is not None:
        monthly_pnl_pct = monthly_realized_pnl_pct(conn, asof, starting_equity)
    else:
        monthly_pnl_pct = 0.0

    diagnostics = {sig: "unknown" for sig in _UNWIRED_SIGNALS}

    snap = MarketSnapshot(
        taiex_close=taiex_close,
        taiex_change_pct=taiex_change_pct,
        risk_off=risk_off,
        monthly_pnl_pct=monthly_pnl_pct,
    )
    return snap, diagnostics


def _evaluate_taiex_risk_off(closes: list[float]) -> bool:
    """Risk-Off when TAIEX close < MA60 AND MA60 is flat-or-falling.

    Returns ``False`` when there are not enough bars to compute MA60 plus
    the slope window (unknown ≠ triggered).
    """
    ma_series = sma(closes, _MA_PERIOD)
    ma60 = ma_series[-1]
    if ma60 is None:
        return False
    close = closes[-1]
    if close >= ma60:
        return False
    if len(ma_series) < _MA_SLOPE_LOOKBACK + 1:
        return False
    ma60_prev = ma_series[-1 - _MA_SLOPE_LOOKBACK]
    if ma60_prev is None:
        return False
    return ma60 <= ma60_prev


def _business_days_between(start_ts: str, end_ts: str) -> int:
    """Count Mon-Fri days strictly between ``start_ts`` and ``end_ts``.

    Both arguments are ``YYYY-MM-DD`` strings. Returns ``0`` when
    ``start_ts >= end_ts``.
    """
    s = date.fromisoformat(start_ts)
    e = date.fromisoformat(end_ts)
    if s >= e:
        return 0
    days = 0
    cursor = s
    while cursor < e:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            days += 1
    return days
