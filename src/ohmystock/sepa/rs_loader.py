"""Production loader for ``compute_rs_rating`` — wires ``universe_daily`` + ``bars_daily``.

Spec: openspec/changes/rs-percentile-finmind-wiring/specs/rs-percentile/spec.md
      ("Production universe-closes loader sources symbols from `universe_daily` and closes from `bars_daily`")

Read-only by design. The loader does not instantiate ``FinMindClient`` or
any other upstream connector. ``bars_daily`` is filled by the screener
pipeline / Phase 1 ``data_pipeline_skill``; this module simply consumes
what's there. A symbol whose ``bars_daily`` history contains fewer than
253 closes ending at ``asof`` is omitted from the returned dict.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Callable

from ohmystock.api.db import get_connection
from ohmystock.data.cache import init_market_data_schema, select_bars
from ohmystock.screener.cache import init_universe_schema, select_universe_rows

__all__ = ["build_universe_closes_loader"]


_MIN_CLOSES: int = 253
_DEFAULT_HISTORY_CALENDAR_DAYS: int = 520


def build_universe_closes_loader(
    conn: sqlite3.Connection | None = None,
    *,
    disposition_fetcher: Callable[[date], set[str]] | None = None,
    history_calendar_days: int = _DEFAULT_HISTORY_CALENDAR_DAYS,
) -> Callable[[date], dict[str, list[float]]]:
    """Return a closure that yields ``{symbol: closes[]}`` for an ``asof``.

    The closure:

    * Reads the symbol roster from ``universe_daily`` for the requested
      ``asof``. If the roster is empty (screener hasn't run for that day),
      returns ``{}`` — callers SHOULD ensure the screener has populated
      ``universe_daily`` before invoking ``compute_rs_rating``.
    * Optionally removes disposition-flagged symbols (when
      ``disposition_fetcher`` is provided).
    * Reads ``history_calendar_days`` of trailing daily closes from
      ``bars_daily`` per symbol via ``data.cache.select_bars``.
    * Drops symbols with fewer than 253 closes (the floor for the
      ``_weighted_score`` R252 lookback). ``compute_rs_line`` requires more
      (504); it raises ``InsufficientHistoryError`` itself for shorter
      series — this loader does not gate on that bound.

    ``conn``: optional shared connection. ``None`` (production) means open
    a fresh ``sqlite3.Connection`` per loader call via
    ``ohmystock.api.db.get_connection``. Pass a conn from tests or batched
    callers (e.g., backfill) to amortize connection setup.

    ``disposition_fetcher``: optional callable returning the disposition
    set for ``asof``. ``None`` (Batch 1 default) means no disposition
    filter is applied — Batch 2 wires ``data.disposition.fetch_disposition_set``.

    ``history_calendar_days``: how far back to read bars per symbol. The
    default (520 calendar days) covers ~370 trading days, comfortably
    enough for both R252 (needs 253) and Mansfield SMA52w (needs 504).
    """

    bound_conn = conn

    def loader(asof: date) -> dict[str, list[float]]:
        owns_conn = bound_conn is None
        c = get_connection() if owns_conn else bound_conn
        try:
            init_universe_schema(c)
            init_market_data_schema(c)

            asof_iso = asof.isoformat()
            rows = select_universe_rows(c, asof_iso)
            if not rows:
                return {}

            symbols = [r["symbol"] for r in rows]
            if disposition_fetcher is not None:
                disposition = disposition_fetcher(asof)
                if disposition:
                    symbols = [s for s in symbols if s not in disposition]

            start_iso = (asof - timedelta(days=history_calendar_days)).isoformat()

            out: dict[str, list[float]] = {}
            for sym in symbols:
                bars = select_bars(c, sym, start_iso, asof_iso)
                if len(bars) < _MIN_CLOSES:
                    continue
                out[sym] = [float(b["c"]) for b in bars]
            return out
        finally:
            if owns_conn:
                c.close()

    return loader
