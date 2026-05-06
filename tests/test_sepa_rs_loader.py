"""Tests for ``ohmystock.sepa.rs_loader`` — covers task 1.4.

Spec: openspec/changes/rs-percentile-finmind-wiring/specs/rs-percentile/spec.md
      ("Production universe-closes loader sources symbols from `universe_daily` and closes from `bars_daily`")
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from ohmystock.data.cache import init_market_data_schema, insert_bars
from ohmystock.screener.cache import (
    init_universe_schema,
    insert_universe_rows,
)
from ohmystock.sepa.rs_loader import build_universe_closes_loader


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    try:
        init_universe_schema(c)
        init_market_data_schema(c)
        yield c
    finally:
        c.close()


def _seed_universe(conn: sqlite3.Connection, asof: date, symbols: list[str]) -> None:
    rows = [
        {
            "asof_date": asof.isoformat(),
            "symbol": s,
            "market": "TWSE",
            "name": f"Stock {s}",
            "industry": "Test",
            "is_warning": 0,
            "is_disposal": 0,
            "is_fully_paid": 0,
            "is_ky": 0,
        }
        for s in symbols
    ]
    insert_universe_rows(conn, rows, source="test", fetched_at=asof.isoformat())


def _seed_bars(
    conn: sqlite3.Connection,
    symbol: str,
    asof: date,
    closes: list[float],
) -> None:
    """Insert ``len(closes)`` bars ending on ``asof``, one per calendar day."""
    n = len(closes)
    rows = []
    for i, c in enumerate(closes):
        d = asof - timedelta(days=n - 1 - i)
        rows.append(
            {
                "ts": d.isoformat(),
                "o": c,
                "h": c,
                "l": c,
                "c": c,
                "v": 1_000_000,
                "amount": int(c * 1_000_000),
            }
        )
    insert_bars(conn, symbol, rows, source="test", fetched_at=asof.isoformat())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildUniverseClosesLoader:
    """Spec: 'Production universe-closes loader …'."""

    def test_liquid_symbol_with_full_history_returns_closes(
        self, conn: sqlite3.Connection
    ) -> None:
        asof = date(2026, 4, 30)
        _seed_universe(conn, asof, ["2330"])
        _seed_bars(conn, "2330", asof, [100.0 + i for i in range(260)])

        loader = build_universe_closes_loader(conn)
        result = loader(asof)

        assert "2330" in result
        assert len(result["2330"]) >= 253
        # Closes are in ascending date order; last value matches the asof bar.
        assert result["2330"][-1] == pytest.approx(100.0 + 259)

    def test_symbol_with_insufficient_bars_is_omitted(
        self, conn: sqlite3.Connection
    ) -> None:
        asof = date(2026, 4, 30)
        _seed_universe(conn, asof, ["9999"])
        # Only 100 closes — well below the 253-floor.
        _seed_bars(conn, "9999", asof, [50.0] * 100)

        loader = build_universe_closes_loader(conn)
        result = loader(asof)

        assert "9999" not in result

    def test_empty_universe_for_asof_returns_empty_dict(
        self, conn: sqlite3.Connection
    ) -> None:
        asof = date(2026, 4, 30)
        # No universe_daily rows for this asof.

        loader = build_universe_closes_loader(conn)
        result = loader(asof)

        assert result == {}

    def test_disposition_filter_excludes_flagged_symbol(
        self, conn: sqlite3.Connection
    ) -> None:
        asof = date(2026, 4, 30)
        _seed_universe(conn, asof, ["2330", "5678"])
        _seed_bars(conn, "2330", asof, [100.0 + i for i in range(260)])
        _seed_bars(conn, "5678", asof, [50.0 + i for i in range(260)])

        loader = build_universe_closes_loader(
            conn, disposition_fetcher=lambda _asof: {"5678"}
        )
        result = loader(asof)

        assert "2330" in result
        assert "5678" not in result

    def test_loader_does_not_instantiate_finmind_client(
        self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spec scenario: 'Loader does not bypass the bars_daily cache'."""
        asof = date(2026, 4, 30)
        _seed_universe(conn, asof, ["2330"])
        _seed_bars(conn, "2330", asof, [100.0] * 260)

        # If the loader ever constructs a FinMindClient, this raises and the
        # test fails. Patch __init__ on the class so any call to
        # ``FinMindClient()`` blows up.
        from ohmystock.data.finmind_client import FinMindClient

        def _boom(self):  # pragma: no cover - must not be invoked
            raise AssertionError("loader instantiated FinMindClient")

        monkeypatch.setattr(FinMindClient, "__init__", _boom)

        loader = build_universe_closes_loader(conn)
        result = loader(asof)

        assert "2330" in result

    def test_loader_uses_provided_conn_does_not_open_its_own(
        self, conn: sqlite3.Connection
    ) -> None:
        """When a conn is passed, the closure does not open another."""
        asof = date(2026, 4, 30)
        _seed_universe(conn, asof, ["2330"])
        _seed_bars(conn, "2330", asof, [100.0 + i for i in range(260)])

        loader = build_universe_closes_loader(conn)
        # Two consecutive calls must not throw "database is locked" or close
        # the user-provided conn.
        result1 = loader(asof)
        result2 = loader(asof)

        assert "2330" in result1 and "2330" in result2
        # The provided conn is still usable after the loader returns.
        cur = conn.execute(
            "SELECT COUNT(*) FROM bars_daily WHERE symbol = ?", ("2330",)
        )
        assert cur.fetchone()[0] >= 253
