"""RS Rating skill — cross-sectional percentile + Mansfield RS line.

Spec: openspec/changes/rs-percentile-skill/specs/rs-percentile/spec.md
Design: openspec/changes/rs-percentile-skill/design.md (Decisions 1, 3, 4, 6, 7)

Single producer of RS Rating for ohMyStock. The 7-point sub-scorer in
``ohmystock.scoring.subscorers.rs_percentile`` and the c8 condition in the
trend template both call ``compute_rs_rating`` so the same number flows to
both consumers.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable, Iterable

from ohmystock.sepa.types import InsufficientHistoryError

__all__ = [
    "RsLineResult",
    "init_schema",
    "compute_rs_rating",
    "compute_rs_line",
    "set_universe_closes_loader",
    "reset_providers",
]


# ---------------------------------------------------------------------------
# Constants & types
# ---------------------------------------------------------------------------

_MIN_LIQUIDITY_TWD: float = 100_000_000.0
_MIN_LISTING_DAYS: int = 252
_LIQUIDITY_WINDOW: int = 20
_RS_LOOKBACKS: tuple[int, ...] = (63, 126, 189, 252)
_RS_WEIGHTS: tuple[float, ...] = (0.25, 0.25, 0.25, 0.25)
_DEFAULT_BENCHMARK: str = "^TWII"
_MANSFIELD_SMA_WINDOW: int = 252
_MANSFIELD_SLOPE_WINDOW: int = 20


@dataclass(frozen=True)
class RsLineResult:
    """Mansfield RS line + slope + 52-week-high flag."""

    series: tuple[float, ...]
    slope_20d: float
    at_52w_high: bool
    benchmark_used: str


# ---------------------------------------------------------------------------
# SQLite schema (Decision 7: inline init_schema, no migrations dir)
# ---------------------------------------------------------------------------

_DDL_CACHE = """
CREATE TABLE IF NOT EXISTS rs_rating_cache (
    asof_date     TEXT    NOT NULL,
    symbol        TEXT    NOT NULL,
    rs_rating     INTEGER NOT NULL,
    universe_size INTEGER NOT NULL,
    computed_at   TEXT    NOT NULL,
    PRIMARY KEY (asof_date, symbol)
)
""".strip()

_DDL_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_rs_rating_asof "
    "ON rs_rating_cache(asof_date)"
)


def init_schema(conn: sqlite3.Connection) -> None:
    """Create ``rs_rating_cache`` table + index. Idempotent. Single transaction."""
    with conn:
        conn.execute(_DDL_CACHE)
        conn.execute(_DDL_INDEX)


# ---------------------------------------------------------------------------
# Pure math: weighted score + percentile rank with method="min"
# ---------------------------------------------------------------------------


def _weighted_score(closes: list[float]) -> float | None:
    """0.25 * R63 + 0.25 * R126 + 0.25 * R189 + 0.25 * R252.

    Returns ``None`` if any required base close is missing or non-positive.
    Requires ``len(closes) >= 253`` (one more than the longest lookback so
    we can compute close[-1] / close[-253] for R252).
    """
    if len(closes) < max(_RS_LOOKBACKS) + 1:
        return None
    last = closes[-1]
    if last <= 0:
        return None
    score = 0.0
    for n, w in zip(_RS_LOOKBACKS, _RS_WEIGHTS):
        base = closes[-(n + 1)]
        if base <= 0:
            return None
        score += w * (last / base - 1.0)
    return score


def _rank_min(scores: list[float]) -> list[int]:
    """Return 1-indexed worst-to-best ranks with ``method='min'`` ties.

    Tied scores receive the lowest rank in their tie group. Example:
    [10, 20, 20, 30] -> [1, 2, 2, 4].
    """
    n = len(scores)
    order = sorted(range(n), key=lambda i: scores[i])
    ranks = [0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        rank = i + 1
        for k in range(i, j + 1):
            ranks[order[k]] = rank
        i = j + 1
    return ranks


def _percentile_from_rank(rank: int, n: int) -> int:
    """Map 1-indexed worst-to-best rank to integer percentile in [1, 99].

    Formula: ``floor(99 * (rank - 1) / N) + 1``, clamped to ``[1, 99]``.
    Best (rank=N) -> 99, median (rank ~ N/2) -> 50. Spec scenarios pinned.
    """
    if n <= 0:
        return 1
    pct = math.floor(99 * (rank - 1) / n) + 1
    return max(1, min(99, pct))


def _compute_universe_ratings(
    closes_by_symbol: dict[str, list[float]],
) -> dict[str, int]:
    """Score every symbol, rank-percentile to 1..99 with ``method='min'`` ties.

    Symbols whose ``_weighted_score`` returns ``None`` are excluded — they
    don't make it into the cached set and ``compute_rs_rating`` returns
    ``None`` for them.
    """
    symbols: list[str] = []
    scores: list[float] = []
    for sym, closes in closes_by_symbol.items():
        s = _weighted_score(closes)
        if s is None:
            continue
        symbols.append(sym)
        scores.append(s)
    if not symbols:
        return {}
    ranks = _rank_min(scores)
    n = len(symbols)
    return {sym: _percentile_from_rank(r, n) for sym, r in zip(symbols, ranks)}


# ---------------------------------------------------------------------------
# Universe builder (pure: given inputs, returns eligible symbols)
# ---------------------------------------------------------------------------


def _build_universe(
    asof: date,
    info_rows: Iterable[dict],
    bars_by_symbol: dict[str, list[dict]],
    disposition_set: set[str],
) -> list[str]:
    """Return TWSE+OTC common-stock symbols eligible on ``asof``.

    Inputs are passed in (not fetched) so this function stays pure and
    unit-testable. Production code wires real connectors above this layer.

    Filters (spec.md "Eligible universe defined by liquidity and listing rules"):
      - Listed on/before ``asof - 252 trading days``
      - 20-day average ``close * volume`` over [asof-20, asof-1] >= NT$100M
      - Not in ``disposition_set``
      - Has a valid close on ``asof`` (last bar's date == asof and close > 0)
    """
    asof_iso = asof.isoformat()
    eligible: list[str] = []

    listing_dates: dict[str, str] = {}
    valid_types = {"twse", "otc"}
    for row in info_rows:
        sym = str(row.get("stock_id") or row.get("symbol") or "").strip()
        if not sym:
            continue
        market = str(row.get("type", "")).strip().lower()
        if market and market not in valid_types:
            continue
        if str(row.get("industry_category", "")).lower() in {"etf", "warrant", "reit"}:
            continue
        listing_dates[sym] = str(row.get("date") or row.get("listing_date") or "")

    for sym, listing_date in listing_dates.items():
        if sym in disposition_set:
            continue
        bars = bars_by_symbol.get(sym, [])
        if not bars:
            continue
        if not _listed_long_enough(listing_date, asof, _MIN_LISTING_DAYS):
            continue
        last = bars[-1]
        if str(last.get("ts") or last.get("date") or "") != asof_iso:
            continue
        if float(last.get("c", 0.0) or 0.0) <= 0:
            continue
        if not _liquid_enough(bars, _LIQUIDITY_WINDOW, _MIN_LIQUIDITY_TWD):
            continue
        eligible.append(sym)

    eligible.sort()
    return eligible


def _listed_long_enough(listing_date: str, asof: date, min_days: int) -> bool:
    if not listing_date:
        return False
    try:
        listed = datetime.strptime(listing_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return False
    return (asof - listed).days >= min_days


def _liquid_enough(
    bars: list[dict], window: int, threshold_twd: float
) -> bool:
    if len(bars) < window + 1:
        return False
    sample = bars[-(window + 1):-1]
    total = 0.0
    for b in sample:
        c = float(b.get("c", 0.0) or 0.0)
        v = float(b.get("v", 0.0) or 0.0)
        total += c * v
    return (total / window) >= threshold_twd


# ---------------------------------------------------------------------------
# Cache + public API
# ---------------------------------------------------------------------------

# Test injection point. Production wiring (Phase 1 backfill + screener)
# overrides via ``set_universe_closes_loader`` to plug in real FinMind /
# market_data fetches. Default ``None`` makes ``compute_rs_rating`` raise
# loudly until wired.
_universe_closes_loader: (
    Callable[[date], dict[str, list[float]]] | None
) = None


def set_universe_closes_loader(
    loader: Callable[[date], dict[str, list[float]]],
) -> None:
    """Inject a function that returns ``{symbol: closes[]}`` for ``asof``.

    The returned closes must include enough history for ``_weighted_score``
    (>= 253 bars ending at ``asof``). Symbols are presumed already filtered
    by the caller's universe rules; this loader is the single source of
    truth for what's in the cache for a given ``asof``.
    """
    global _universe_closes_loader
    if not callable(loader):
        raise TypeError(f"loader must be callable, got {loader!r}")
    _universe_closes_loader = loader


def reset_providers() -> None:
    """Restore default state. Used by tests."""
    global _universe_closes_loader
    _universe_closes_loader = None


def _open_cache_conn() -> sqlite3.Connection:
    from ohmystock.api.db import get_connection

    conn = get_connection()
    init_schema(conn)
    return conn


def _read_cached(
    conn: sqlite3.Connection, asof_iso: str
) -> dict[str, int] | None:
    rows = conn.execute(
        "SELECT symbol, rs_rating FROM rs_rating_cache WHERE asof_date = ?",
        (asof_iso,),
    ).fetchall()
    if not rows:
        return None
    return {sym: int(r) for sym, r in rows}


def _write_cache(
    conn: sqlite3.Connection,
    asof_iso: str,
    ratings: dict[str, int],
) -> None:
    if not ratings:
        return
    universe_size = len(ratings)
    computed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = [
        (asof_iso, sym, rating, universe_size, computed_at)
        for sym, rating in ratings.items()
    ]
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO rs_rating_cache "
            "(asof_date, symbol, rs_rating, universe_size, computed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            payload,
        )


def compute_rs_rating(
    symbol: str,
    asof: str | date,
    *,
    conn: sqlite3.Connection | None = None,
) -> int | None:
    """Return cross-sectional RS percentile (1..99) or ``None`` if ineligible.

    On cache miss for ``asof_date``, computes the entire universe in one
    transaction. Subsequent calls for the same ``asof_date`` hit cache.
    """
    asof_iso = _to_iso(asof)
    sym = str(symbol).strip()
    if not sym:
        return None

    owns_conn = conn is None
    if conn is None:
        conn = _open_cache_conn()
    else:
        init_schema(conn)
    try:
        cached = _read_cached(conn, asof_iso)
        if cached is not None:
            return cached.get(sym)

        if _universe_closes_loader is None:
            raise RuntimeError(
                "rs_percentile_calc: universe_closes_loader not configured. "
                "Call set_universe_closes_loader(...) at startup or in tests."
            )
        asof_date = _parse_iso(asof_iso)
        closes_by_symbol = _universe_closes_loader(asof_date)
        ratings = _compute_universe_ratings(closes_by_symbol)
        _write_cache(conn, asof_iso, ratings)
        return ratings.get(sym)
    finally:
        if owns_conn:
            conn.close()


def compute_rs_line(
    symbol: str,
    asof: str | date,
    benchmark: str = _DEFAULT_BENCHMARK,
    lookback: int = 252,
    *,
    symbol_closes: list[float] | None = None,
    benchmark_closes: list[float] | None = None,
) -> RsLineResult:
    """Mansfield RS line + slope + 52-week-high flag.

    ``symbol_closes`` and ``benchmark_closes`` are optional injection points
    for tests / callers that already have bars in hand. When omitted, the
    module-level loader (set via ``set_universe_closes_loader``) is consulted
    — if that's also absent, ``RuntimeError`` is raised.

    Raises ``InsufficientHistoryError`` if either series has fewer than
    ``lookback + 252`` bars (need 252 extra for the SMA52w warmup).
    """
    sym = str(symbol).strip()
    asof_iso = _to_iso(asof)
    asof_date = _parse_iso(asof_iso)
    needed = lookback + _MANSFIELD_SMA_WINDOW

    s_closes = symbol_closes
    b_closes = benchmark_closes
    if s_closes is None or b_closes is None:
        if _universe_closes_loader is None:
            raise RuntimeError(
                "compute_rs_line: pass symbol_closes / benchmark_closes "
                "directly or configure set_universe_closes_loader."
            )
        loaded = _universe_closes_loader(asof_date)
        if s_closes is None:
            if sym not in loaded:
                raise InsufficientHistoryError(
                    f"{sym} not in loaded universe; need >= {needed} bars"
                )
            s_closes = loaded[sym]
        if b_closes is None:
            if benchmark not in loaded:
                raise InsufficientHistoryError(
                    f"benchmark {benchmark} not in loaded universe; "
                    f"need >= {needed} bars"
                )
            b_closes = loaded[benchmark]

    s_len = len(s_closes)
    b_len = len(b_closes)
    if s_len < needed:
        raise InsufficientHistoryError(
            f"{sym}: have {s_len} bars, need {needed} "
            f"(lookback={lookback} + sma_window={_MANSFIELD_SMA_WINDOW})"
        )
    if b_len < needed:
        raise InsufficientHistoryError(
            f"benchmark {benchmark}: have {b_len} bars, need {needed}"
        )

    series = _mansfield_series(s_closes, b_closes, lookback)
    slope = _least_squares_slope(series[-_MANSFIELD_SLOPE_WINDOW:])
    at_high = series[-1] >= max(series)
    return RsLineResult(
        series=tuple(series),
        slope_20d=slope,
        at_52w_high=at_high,
        benchmark_used=benchmark,
    )


def _mansfield_series(
    s_closes: list[float], b_closes: list[float], lookback: int
) -> list[float]:
    """Return Mansfield RS values for the last ``lookback`` bars.

    ``RS_t = (close_s_t / close_b_t) / SMA52w(price_ratio_t) - 1``
    where ``SMA52w`` is the 252-day simple moving average of the price
    ratio ending at ``t``.
    """
    take = lookback + _MANSFIELD_SMA_WINDOW
    s = s_closes[-take:]
    b = b_closes[-take:]
    ratios = [s[i] / b[i] if b[i] != 0 else 0.0 for i in range(len(s))]
    series: list[float] = []
    for i in range(_MANSFIELD_SMA_WINDOW, len(ratios)):
        window = ratios[i - _MANSFIELD_SMA_WINDOW + 1: i + 1]
        sma = sum(window) / _MANSFIELD_SMA_WINDOW
        if sma == 0:
            series.append(0.0)
            continue
        series.append(ratios[i] / sma - 1.0)
    return series


def _least_squares_slope(ys: list[float]) -> float:
    """Slope of best-fit line y = a + b*x with x = [0, 1, ..., n-1]."""
    n = len(ys)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(ys) / n
    num = 0.0
    den = 0.0
    for i, y in enumerate(ys):
        dx = i - mean_x
        num += dx * (y - mean_y)
        den += dx * dx
    return num / den if den != 0 else 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_iso(asof: str | date) -> str:
    if isinstance(asof, date):
        return asof.isoformat()
    s = str(asof).strip()
    _parse_iso(s)
    return s


def _parse_iso(asof_iso: str) -> date:
    return datetime.strptime(asof_iso, "%Y-%m-%d").date()
