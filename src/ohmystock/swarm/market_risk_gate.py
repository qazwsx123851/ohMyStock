"""Market-level Risk-Off gate → dashboard three-colour light (display only).

Computes the five §0.1 market Risk-Off conditions (SSOT:
``docs/workflow-cheatsheet.md`` §0.1) and maps them to a green / yellow / red
status for the admin dashboard. This is **display only** (web-admin-scenario-gaps
接法 A): it does NOT drive the swarm ``risk_off`` flag or change scoring/trade
behaviour — that path still uses TAIEX-only via ``swarm/_live_market.py``.

Each condition is evaluated independently and resolves to one of:

* ``True``  — the condition fired (Risk-Off contributor)
* ``False`` — evaluated, did not fire
* ``None``  — data unavailable / insufficient bars (unknown ≠ triggered)

Status mapping:

* ``red``    — at least one condition fired
* ``yellow`` — none fired but at least one is unknown (can't fully confirm)
* ``green``  — all five evaluated, none fired

All data access is injected (``kline_fn`` / ``futures_fn``) so the gate is unit
-testable without network calls. The five thresholds below are the SSOT §0.1
values, implemented here for the first time (TAIEX was the only previously wired
condition); they are not duplicated elsewhere.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Literal

from ohmystock.data.market_data import get_kline
from ohmystock.swarm._live_market import _evaluate_taiex_risk_off

# SSOT thresholds — docs/workflow-cheatsheet.md §0.1
_SPY_5D_DROP = -0.03       # SPY past-5-day return below -3%
_VIX_LEVEL = 25.0          # VIX above 25
_VIX_1D_SPIKE = 0.30       # …or a 1-day gain above 30%
_TWD_DEPRECIATION = 0.005  # USD/TWD up >0.5% in a day (TWD weakens)

Condition = Literal[
    "taiex_below_ma60",
    "spy_5d_drop",
    "vix_high",
    "twd_depreciation",
    "taifex_foreign_short_streak",
]

KlineFn = Callable[..., dict]
# futures_fn(asof) -> oldest→newest foreign net-short series, or None if unknown.
FuturesFn = Callable[[str], "list[float] | None"]

Status = Literal["green", "yellow", "red"]


@dataclass(frozen=True)
class RiskGateResult:
    status: Status
    triggers: list[str]
    unknown: list[str]


def _closes(
    kline_fn: KlineFn, symbol: str, bars: int, asof: str
) -> list[float] | None:
    """Return the close series (oldest→newest) or ``None`` on any failure."""
    try:
        env = kline_fn(symbol, bars=bars, end_date=asof)
    except Exception:
        return None
    if not env.get("ok"):
        return None
    rows = (env.get("data") or {}).get("bars") or []
    closes = [float(b["c"]) for b in rows]
    return closes or None


def _eval_taiex(kline_fn: KlineFn, asof: str) -> bool | None:
    closes = _closes(kline_fn, "TAIEX", 80, asof)
    if closes is None:
        return None
    return _evaluate_taiex_risk_off(closes)


def _eval_spy(kline_fn: KlineFn, asof: str) -> bool | None:
    closes = _closes(kline_fn, "SPY", 10, asof)
    if closes is None or len(closes) < 6:
        return None
    five_day_return = closes[-1] / closes[-6] - 1.0
    down_today = closes[-1] < closes[-2]
    return five_day_return < _SPY_5D_DROP and down_today


def _eval_vix(kline_fn: KlineFn, asof: str) -> bool | None:
    closes = _closes(kline_fn, "VIX", 5, asof)
    if closes is None or len(closes) < 2:
        return None
    one_day = closes[-1] / closes[-2] - 1.0
    return closes[-1] > _VIX_LEVEL or one_day > _VIX_1D_SPIKE


def _eval_twd(kline_fn: KlineFn, asof: str) -> bool | None:
    closes = _closes(kline_fn, "USDTWD", 5, asof)
    if closes is None or len(closes) < 2:
        return None
    one_day = closes[-1] / closes[-2] - 1.0
    return one_day > _TWD_DEPRECIATION


def _eval_taifex(futures_fn: FuturesFn | None, asof: str) -> bool | None:
    """Foreign TAIFEX net short making a new high on each of the last 3 days."""
    if futures_fn is None:
        return None
    try:
        series = futures_fn(asof)
    except Exception:
        return None
    if series is None or len(series) < 4:
        return None
    # Each of the last 3 days strictly exceeds the running max of all prior days.
    for k in (3, 2, 1):
        i = len(series) - k
        if series[i] <= max(series[:i]):
            return False
    return True


_FOREIGN_LABELS = ("外資", "外資及陸資", "foreign_investor", "foreign")
_LONG_KEYS = (
    "long_open_interest_balance_volume",
    "long_open_interest_balance",
    "long_open_interest",
)
_SHORT_KEYS = (
    "short_open_interest_balance_volume",
    "short_open_interest_balance",
    "short_open_interest",
)


def _first_num(row: dict, keys: tuple[str, ...]) -> float | None:
    for k in keys:
        if k in row and row[k] is not None:
            try:
                return float(row[k])
            except (TypeError, ValueError):
                return None
    return None


def build_finmind_futures_fn(
    *, futures_id: str = "TX", lookback_days: int = 14
) -> FuturesFn:
    """Default ``futures_fn``: foreign TAIFEX net-short OI series via FinMind.

    Net short = short OI − long OI for the foreign-investor rows, oldest→newest.
    Returns ``None`` on any error or empty data so the gate treats it as
    unknown rather than triggered. FinMind field names vary by dataset version,
    so long/short balances are read defensively from several candidate keys.
    """

    def _fn(asof: str) -> list[float] | None:
        from datetime import date, timedelta

        from ohmystock.data.finmind_client import FinMindClient

        try:
            end = date.fromisoformat(asof)
            start = (end - timedelta(days=lookback_days)).isoformat()
            rows = FinMindClient().get_futures_institutional_investors(
                futures_id, start, end.isoformat()
            )
        except Exception:
            return None

        by_date: dict[str, float] = {}
        for row in rows:
            investor = str(row.get("institutional_investors", ""))
            if not any(lbl in investor for lbl in _FOREIGN_LABELS):
                continue
            long_oi = _first_num(row, _LONG_KEYS)
            short_oi = _first_num(row, _SHORT_KEYS)
            if long_oi is None or short_oi is None:
                continue
            d = str(row.get("date", ""))
            if d:
                by_date[d] = short_oi - long_oi

        if not by_date:
            return None
        return [by_date[d] for d in sorted(by_date)]

    return _fn


def evaluate_risk_gate(
    asof: str,
    *,
    kline_fn: KlineFn = get_kline,
    futures_fn: FuturesFn | None = None,
) -> RiskGateResult:
    """Evaluate all five §0.1 conditions and map to a three-colour status."""
    results: dict[str, bool | None] = {
        "taiex_below_ma60": _eval_taiex(kline_fn, asof),
        "spy_5d_drop": _eval_spy(kline_fn, asof),
        "vix_high": _eval_vix(kline_fn, asof),
        "twd_depreciation": _eval_twd(kline_fn, asof),
        "taifex_foreign_short_streak": _eval_taifex(futures_fn, asof),
    }
    triggers = [c for c, v in results.items() if v is True]
    unknown = [c for c, v in results.items() if v is None]
    if triggers:
        status: Status = "red"
    elif unknown:
        status = "yellow"
    else:
        status = "green"
    return RiskGateResult(status=status, triggers=triggers, unknown=unknown)


# TTL cache so a 30s-polled dashboard doesn't re-hit yfinance/FinMind every
# poll. Keyed by asof date; bounded to one external sweep per ``ttl`` seconds.
_CACHE: dict[str, tuple[float, RiskGateResult]] = {}


def evaluate_risk_gate_cached(
    asof: str,
    *,
    kline_fn: KlineFn = get_kline,
    futures_fn: FuturesFn | None = None,
    ttl: float = 300.0,
) -> RiskGateResult:
    """``evaluate_risk_gate`` memoised per ``asof`` for ``ttl`` seconds."""
    now = time.monotonic()
    hit = _CACHE.get(asof)
    if hit is not None and now - hit[0] < ttl:
        return hit[1]
    result = evaluate_risk_gate(asof, kline_fn=kline_fn, futures_fn=futures_fn)
    _CACHE[asof] = (now, result)
    return result
