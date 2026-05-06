"""Tests for ``ohmystock.sepa.rs`` — covers tasks 2.3 / 3.4 / 4.2.

Spec: openspec/changes/rs-percentile-skill/specs/rs-percentile/spec.md
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

import pytest

from ohmystock.sepa.rs import (
    InsufficientHistoryError,
    RsLineResult,
    _build_universe,
    _percentile_from_rank,
    _rank_min,
    _weighted_score,
    compute_rs_line,
    compute_rs_rating,
    init_schema,
    reset_providers,
    set_universe_closes_loader,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bars_with_dates(closes: list[float], asof: date) -> list[dict]:
    """Return ``len(closes)`` bars ending on ``asof`` (calendar-day stepped).

    `_build_universe` keys off the last bar's `ts == asof_iso`; calendar days
    are fine for the unit-test path where we control the data.
    """
    n = len(closes)
    bars: list[dict] = []
    for i, c in enumerate(closes):
        d = asof - timedelta(days=n - 1 - i)
        bars.append(
            {
                "ts": d.isoformat(),
                "o": c,
                "h": c,
                "l": c,
                "c": c,
                "v": 1_000_000,
            }
        )
    return bars


def _ramp(n: int, start: float, end: float) -> list[float]:
    if n == 1:
        return [start]
    return [start + (end - start) * (i / (n - 1)) for i in range(n)]


@pytest.fixture(autouse=True)
def _restore_loaders():
    yield
    reset_providers()


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    try:
        init_schema(c)
        yield c
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Pure-math layer (3.4 ties + percentile)
# ---------------------------------------------------------------------------


class TestWeightedScore:
    def test_returns_none_when_too_few_bars(self) -> None:
        assert _weighted_score([100.0] * 200) is None

    def test_zero_return_when_flat(self) -> None:
        score = _weighted_score([100.0] * 253)
        assert score == pytest.approx(0.0, abs=1e-12)

    def test_monotonic_ramp_yields_positive(self) -> None:
        score = _weighted_score(_ramp(253, 10.0, 30.0))
        assert score is not None and score > 0

    def test_non_positive_base_returns_none(self) -> None:
        closes = [1.0] * 253
        closes[-(63 + 1)] = 0.0
        assert _weighted_score(closes) is None


class TestRankMin:
    def test_unique_scores_get_dense_ranks(self) -> None:
        assert _rank_min([10.0, 20.0, 30.0, 40.0]) == [1, 2, 3, 4]

    def test_ties_share_lowest_rank(self) -> None:
        assert _rank_min([10.0, 20.0, 20.0, 30.0]) == [1, 2, 2, 4]

    def test_all_tied(self) -> None:
        assert _rank_min([5.0, 5.0, 5.0]) == [1, 1, 1]


class TestPercentileFromRank:
    def test_best_in_universe_of_1000_returns_99(self) -> None:
        assert _percentile_from_rank(1000, 1000) == 99

    def test_median_in_999_returns_50(self) -> None:
        # rank 500 of 999 -> floor(99 * 499 / 999) + 1 = 50
        assert _percentile_from_rank(500, 999) == 50

    def test_worst_returns_1(self) -> None:
        assert _percentile_from_rank(1, 100) == 1

    def test_clamped_to_99_max(self) -> None:
        assert _percentile_from_rank(1, 0) == 1


# ---------------------------------------------------------------------------
# Universe builder (task 2.3)
# ---------------------------------------------------------------------------


class TestBuildUniverse:
    def _info(self, sym: str, listing_iso: str, **extra) -> dict:
        return {"stock_id": sym, "date": listing_iso, "type": "twse", **extra}

    def test_eligible_symbol_passes_all_filters(self) -> None:
        asof = date(2026, 4, 30)
        sym = "2330"
        info = [self._info(sym, "2010-01-01")]
        bars = {sym: _bars_with_dates([100.0] * 22, asof)}
        result = _build_universe(asof, info, bars, set())
        assert result == [sym]

    def test_newly_listed_under_252_days_excluded(self) -> None:
        asof = date(2026, 4, 30)
        sym = "9999"
        listed = (asof - timedelta(days=200)).isoformat()
        info = [self._info(sym, listed)]
        bars = {sym: _bars_with_dates([100.0] * 22, asof)}
        assert _build_universe(asof, info, bars, set()) == []

    def test_illiquid_excluded(self) -> None:
        asof = date(2026, 4, 30)
        sym = "1234"
        info = [self._info(sym, "2010-01-01")]
        # 100 * 1 = NT$100 << NT$100M
        thin_bars = [
            {
                "ts": (asof - timedelta(days=21 - i)).isoformat(),
                "o": 100.0, "h": 100.0, "l": 100.0, "c": 100.0, "v": 1.0,
            }
            for i in range(22)
        ]
        assert _build_universe(asof, info, {sym: thin_bars}, set()) == []

    def test_disposition_flagged_excluded(self) -> None:
        asof = date(2026, 4, 30)
        sym = "5678"
        info = [self._info(sym, "2010-01-01")]
        bars = {sym: _bars_with_dates([100.0] * 22, asof)}
        assert _build_universe(asof, info, bars, {sym}) == []

    def test_suspended_on_asof_excluded(self) -> None:
        """Last bar dated earlier than asof simulates suspension."""
        asof = date(2026, 4, 30)
        sym = "1111"
        info = [self._info(sym, "2010-01-01")]
        # Bars stop one day before asof
        stale = _bars_with_dates([100.0] * 22, asof - timedelta(days=1))
        assert _build_universe(asof, info, {sym: stale}, set()) == []

    def test_etf_industry_category_excluded(self) -> None:
        asof = date(2026, 4, 30)
        info = [self._info("0050", "2010-01-01", industry_category="ETF")]
        bars = {"0050": _bars_with_dates([100.0] * 22, asof)}
        assert _build_universe(asof, info, bars, set()) == []


# ---------------------------------------------------------------------------
# compute_rs_rating + cache (task 3.4)
# ---------------------------------------------------------------------------


def _universe_closes_for_test(
    n_symbols: int, asof: date
) -> dict[str, list[float]]:
    """Build a synthetic universe with monotonically improving returns.

    Symbol ``S{i}`` for i in 0..n-1 has growth 0.01*i over 253 bars, so S0 is
    flat (worst), S{n-1} is steepest (best). 253 bars is the minimum
    `_weighted_score` requires (max lookback 252 + 1).
    """
    out: dict[str, list[float]] = {}
    for i in range(n_symbols):
        growth = 0.01 * i
        out[f"S{i}"] = [100.0 * (1.0 + growth * (k / 252.0)) for k in range(253)]
    return out


class TestComputeRsRating:
    def test_best_in_universe_returns_99(self, conn: sqlite3.Connection) -> None:
        asof = date(2026, 4, 30)
        loader_data = _universe_closes_for_test(100, asof)
        set_universe_closes_loader(lambda _d: loader_data)
        result = compute_rs_rating("S99", asof, conn=conn)
        assert result == 99

    def test_worst_in_universe_returns_1(self, conn: sqlite3.Connection) -> None:
        asof = date(2026, 4, 30)
        loader_data = _universe_closes_for_test(100, asof)
        set_universe_closes_loader(lambda _d: loader_data)
        # S0 is flat; S1..S99 all beat it -> S0 is worst -> percentile 1
        assert compute_rs_rating("S0", asof, conn=conn) == 1

    def test_median_returns_50(self, conn: sqlite3.Connection) -> None:
        """N=99, median symbol at rank 50 -> floor(99 * 49/99) + 1 = 50."""
        asof = date(2026, 4, 30)
        # Use 99 symbols so there's a clean median (rank 50 of 99)
        loader_data = _universe_closes_for_test(99, asof)
        set_universe_closes_loader(lambda _d: loader_data)
        # S49 has 49th-best growth (1-indexed worst-to-best rank = 50)
        result = compute_rs_rating("S49", asof, conn=conn)
        assert result == 50

    def test_ties_share_lowest_rank(self, conn: sqlite3.Connection) -> None:
        asof = date(2026, 4, 30)
        # Two symbols with identical scores at the 70th-out-of-100 spot
        loader_data = _universe_closes_for_test(98, asof)
        # Inject a tied pair at the same growth as S69
        loader_data["TIE_A"] = list(loader_data["S69"])
        loader_data["TIE_B"] = list(loader_data["S69"])
        set_universe_closes_loader(lambda _d: loader_data)
        rating_a = compute_rs_rating("TIE_A", asof, conn=conn)
        rating_b = compute_rs_rating("TIE_B", asof, conn=conn)
        rating_orig = compute_rs_rating("S69", asof, conn=conn)
        assert rating_a == rating_b == rating_orig

    def test_unknown_symbol_returns_none(
        self, conn: sqlite3.Connection
    ) -> None:
        asof = date(2026, 4, 30)
        set_universe_closes_loader(
            lambda _d: _universe_closes_for_test(50, asof)
        )
        assert compute_rs_rating("UNKNOWN", asof, conn=conn) is None

    def test_suspended_symbol_returns_none(
        self, conn: sqlite3.Connection
    ) -> None:
        """Symbol with too few bars is dropped from the rated set -> None."""
        asof = date(2026, 4, 30)
        loader_data = _universe_closes_for_test(50, asof)
        loader_data["SUSPENDED"] = [100.0] * 100  # < 253 -> _weighted_score=None
        set_universe_closes_loader(lambda _d: loader_data)
        assert compute_rs_rating("SUSPENDED", asof, conn=conn) is None

    def test_blank_symbol_returns_none(self, conn: sqlite3.Connection) -> None:
        asof = date(2026, 4, 30)
        set_universe_closes_loader(
            lambda _d: _universe_closes_for_test(10, asof)
        )
        assert compute_rs_rating("", asof, conn=conn) is None
        assert compute_rs_rating("   ", asof, conn=conn) is None

    def test_loader_unconfigured_raises(
        self, conn: sqlite3.Connection
    ) -> None:
        reset_providers()
        with pytest.raises(RuntimeError, match="universe_closes_loader"):
            compute_rs_rating("2330", date(2026, 4, 30), conn=conn)

    def test_cache_hit_skips_loader(self, conn: sqlite3.Connection) -> None:
        """Second call for same asof_date must NOT re-invoke the loader."""
        asof = date(2026, 4, 30)
        call_count = {"n": 0}
        loader_data = _universe_closes_for_test(20, asof)

        def loader(_d):
            call_count["n"] += 1
            return loader_data

        set_universe_closes_loader(loader)
        compute_rs_rating("S5", asof, conn=conn)
        compute_rs_rating("S10", asof, conn=conn)
        compute_rs_rating("S15", asof, conn=conn)
        assert call_count["n"] == 1

    def test_cache_persists_universe_size_and_computed_at(
        self, conn: sqlite3.Connection
    ) -> None:
        asof = date(2026, 4, 30)
        loader_data = _universe_closes_for_test(15, asof)
        set_universe_closes_loader(lambda _d: loader_data)
        compute_rs_rating("S0", asof, conn=conn)
        rows = conn.execute(
            "SELECT asof_date, symbol, rs_rating, universe_size, computed_at "
            "FROM rs_rating_cache WHERE asof_date = ?",
            (asof.isoformat(),),
        ).fetchall()
        assert len(rows) == 15
        for asof_iso, _sym, rating, usize, computed in rows:
            assert asof_iso == "2026-04-30"
            assert 1 <= rating <= 99
            assert usize == 15
            # ISO 8601 UTC; parseable
            datetime.fromisoformat(computed)

    def test_string_asof_accepted(self, conn: sqlite3.Connection) -> None:
        asof = date(2026, 4, 30)
        set_universe_closes_loader(
            lambda _d: _universe_closes_for_test(100, asof)
        )
        result = compute_rs_rating("S99", "2026-04-30", conn=conn)
        assert result == 99


# ---------------------------------------------------------------------------
# compute_rs_line — Mansfield (task 4.2)
# ---------------------------------------------------------------------------


class TestComputeRsLine:
    def _linear(self, growth: float, n: int) -> list[float]:
        """Linear ramp from 100 to 100*(1+growth). Used for setup-error tests."""
        return [100.0 * (1.0 + growth * (i / (n - 1))) for i in range(n)]

    def _accelerating_outperformance(self, n: int) -> list[float]:
        """Symbol closes such that (symbol/flat_benchmark) ratio is concave-up.

        Mansfield value `(ratio_t / SMA52w_ratio_t) - 1` increases monotonically
        only when the ratio itself grows faster than its trailing average — i.e.
        is convex. A pure linear or pure exponential ratio gives Mansfield that
        is flat or decreasing relative to its SMA. Quadratic does the trick.
        """
        # ratio[t] = 1 + (t / (n-1))^2  -> symbol[t] = 100 * ratio[t] when
        # benchmark is flat at 100. Last bar reaches ratio=2.0.
        return [100.0 * (1.0 + (i / (n - 1)) ** 2) for i in range(n)]

    def _accelerating_underperformance(self, n: int) -> list[float]:
        """Mirror of accelerating_outperformance: ratio drops concave-down."""
        return [100.0 * (2.0 - (i / (n - 1)) ** 2) for i in range(n)]

    def test_monotonic_outperformance_at_52w_high_and_positive_slope(
        self,
    ) -> None:
        n = 504  # lookback (252) + sma_window (252)
        symbol_closes = self._accelerating_outperformance(n)
        benchmark_closes = [100.0] * n
        result = compute_rs_line(
            "TEST",
            "2026-04-30",
            symbol_closes=symbol_closes,
            benchmark_closes=benchmark_closes,
        )
        assert isinstance(result, RsLineResult)
        assert result.benchmark_used == "^TWII"
        assert result.at_52w_high is True
        assert result.slope_20d > 0
        assert len(result.series) == 252

    def test_insufficient_history_raises_with_counts(self) -> None:
        symbol_closes = self._linear(1.0, 300)  # 300 bars
        benchmark_closes = self._linear(0.5, 504)  # plenty
        with pytest.raises(InsufficientHistoryError) as exc:
            compute_rs_line(
                "9999",
                "2026-04-30",
                symbol_closes=symbol_closes,
                benchmark_closes=benchmark_closes,
                lookback=252,
            )
        msg = str(exc.value)
        assert "300" in msg
        assert "504" in msg

    def test_insufficient_benchmark_history_raises(self) -> None:
        symbol_closes = self._linear(1.0, 504)
        benchmark_closes = self._linear(0.5, 300)
        with pytest.raises(InsufficientHistoryError, match="benchmark"):
            compute_rs_line(
                "TEST",
                "2026-04-30",
                symbol_closes=symbol_closes,
                benchmark_closes=benchmark_closes,
            )

    def test_underperformance_yields_negative_slope_and_no_high(self) -> None:
        n = 504
        symbol_closes = self._accelerating_underperformance(n)
        benchmark_closes = [100.0] * n
        result = compute_rs_line(
            "LAGGARD",
            "2026-04-30",
            symbol_closes=symbol_closes,
            benchmark_closes=benchmark_closes,
        )
        assert result.slope_20d < 0
        assert result.at_52w_high is False
