"""Per-candidate technical-snapshot derivation from cached daily bars.

Five fields the swarm-input-assembler expects for each candidate:
``current_price``, ``ema20_distance_pct``, ``atr_14_pct``,
``distance_from_52w_high_pct``, ``distance_from_52w_low_pct``.

This module reads bars via ``get_kline`` (cache-first) and computes the
technical metrics with the existing pure-function indicators. It performs
no other I/O.

Spec: openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations

from dataclasses import dataclass

from ohmystock.data.market_data import get_kline
from ohmystock.data.sources.base import BarRow
from ohmystock.indicators import atr, ema
from ohmystock.swarm._errors import LiveProviderError


_BARS_REQUESTED = 300
_EMA_PERIOD = 20
_ATR_PERIOD = 14
_FIFTY_TWO_WEEK_BARS = 252


@dataclass(frozen=True)
class CandidateLiveSnapshot:
    current_price: float
    ema20_distance_pct: float
    atr_14_pct: float
    distance_from_52w_high_pct: float
    distance_from_52w_low_pct: float


def live_candidate_snapshot(symbol: str, asof: str) -> CandidateLiveSnapshot:
    """Derive the five technical fields for ``symbol`` as of ``asof``.

    Raises ``LiveProviderError`` (mirroring ``get_kline``'s code) if bars
    cannot be loaded. Computes each metric over the most recent
    ``min(252, available)`` daily bars ending at ``asof`` — never pads.
    """
    env = get_kline(symbol, bars=_BARS_REQUESTED, end_date=asof)
    if not env.get("ok"):
        err = env.get("error") or {}
        code = err.get("code", "UPSTREAM_ERROR")
        message = err.get("message", "get_kline failed")
        if code in ("INVALID_INPUT", "RATE_LIMIT"):
            # Map code values outside LiveProviderError's closed set to
            # UPSTREAM_ERROR so the typed exception is well-formed.
            code = "UPSTREAM_ERROR"
        raise LiveProviderError(
            code=code,
            message=f"{symbol}@{asof}: {message}",
        )

    bars: list[BarRow] = list(env["data"]["bars"])
    if not bars:
        raise LiveProviderError(
            code="DATA_UNAVAILABLE",
            message=f"{symbol}@{asof}: no bars returned by get_kline",
        )

    closes = [float(b["c"]) for b in bars]
    current_price = closes[-1]
    if current_price <= 0:
        raise LiveProviderError(
            code="DATA_UNAVAILABLE",
            message=f"{symbol}@{asof}: non-positive close {current_price}",
        )

    # EMA20 — distance is undefined until period bars accumulate.
    ema20_series = ema(closes, _EMA_PERIOD)
    ema20 = ema20_series[-1] if ema20_series else None
    if ema20 is None or ema20 <= 0:
        ema20_distance_pct = 0.0
    else:
        ema20_distance_pct = (current_price - ema20) / ema20 * 100.0

    # ATR14 as % of close.
    atr_series = atr(bars, _ATR_PERIOD)
    atr14 = atr_series[-1] if atr_series else None
    if atr14 is None:
        atr_14_pct = 0.0
    else:
        atr_14_pct = (atr14 / current_price) * 100.0

    # 52-week window — the most recent up-to-252 bars ending at asof.
    window = closes[-_FIFTY_TWO_WEEK_BARS:]
    high_52 = max(window)
    low_52 = min(window)
    distance_from_52w_high_pct = (
        (current_price / high_52 - 1.0) * 100.0 if high_52 > 0 else 0.0
    )
    distance_from_52w_low_pct = (
        (current_price / low_52 - 1.0) * 100.0 if low_52 > 0 else 0.0
    )

    return CandidateLiveSnapshot(
        current_price=current_price,
        ema20_distance_pct=ema20_distance_pct,
        atr_14_pct=atr_14_pct,
        distance_from_52w_high_pct=distance_from_52w_high_pct,
        distance_from_52w_low_pct=distance_from_52w_low_pct,
    )
