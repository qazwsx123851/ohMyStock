"""Tests for ohmystock.screener.universe.screen_universe.

Spec: openspec/changes/screener-tw-universe/specs/screener-tw-universe/spec.md
"""

from __future__ import annotations

import sqlite3
from typing import Any

import httpx
import pytest

from ohmystock.data.cache import init_market_data_schema, insert_bars
from ohmystock.data.sources.base import BarRow
from ohmystock.screener.cache import init_universe_schema, insert_universe_rows
from ohmystock.screener.universe import screen_universe


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    init_universe_schema(c)
    init_market_data_schema(c)
    try:
        yield c
    finally:
        c.close()


def _row(symbol: str, market: str, asof: str = "2026-04-30", **kw):
    return {
        "asof_date": asof,
        "symbol": symbol,
        "market": market,
        "name": kw.get("name", "X"),
        "industry": kw.get("industry", ""),
        "is_warning": kw.get("is_warning", 0),
        "is_disposal": kw.get("is_disposal", 0),
        "is_fully_paid": kw.get("is_fully_paid", 0),
        "is_ky": kw.get("is_ky", 0),
    }


def _seed_universe(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    insert_universe_rows(conn, rows, "finmind", "2026-04-30T17:30:00+08:00")


# ---------- success paths ----------


def test_exact_day_cache_hit_uses_requested_date(conn) -> None:
    _seed_universe(
        conn,
        [
            _row("2330", "TWSE", name="台積電", industry="Semiconductor"),
            _row("2454", "TWSE", name="聯發科", industry="Semiconductor"),
            _row("6488", "OTC", name="環球晶", industry="Semiconductor"),
        ],
    )

    class _NeverCalledClient:
        def get_taiwan_stock_info(self):  # pragma: no cover - must not be called
            raise AssertionError("FinMind should not be called on cache hit")

    result = screen_universe(
        "TWSE+OTC",
        asof_date="2026-04-30",
        _conn=conn,
        _client=_NeverCalledClient(),
    )
    assert result["ok"] is True
    assert result["error"] is None
    assert result["data"]["asof_date_used"] == "2026-04-30"
    symbols = [c["symbol"] for c in result["data"]["candidates"]]
    assert symbols == ["2330", "2454", "6488"]
    first = result["data"]["candidates"][0]
    assert set(first) == {"symbol", "name", "sector", "market"}
    assert first["sector"] == "Semiconductor"


def test_twse_selector_excludes_otc(conn) -> None:
    _seed_universe(conn, [_row("2330", "TWSE"), _row("6488", "OTC")])
    result = screen_universe("TWSE", asof_date="2026-04-30", _conn=conn, _client=None)
    assert [c["symbol"] for c in result["data"]["candidates"]] == ["2330"]


def test_weekend_fallback_to_most_recent_cache_day(conn) -> None:
    _seed_universe(conn, [_row("2330", "TWSE", asof="2026-04-30")])
    result = screen_universe(
        "TWSE", asof_date="2026-05-02", _conn=conn, _client=None
    )
    assert result["ok"] is True
    assert result["data"]["asof_date_used"] == "2026-04-30"


def test_cache_miss_with_client_writes_through(conn) -> None:
    class _StubClient:
        def get_taiwan_stock_info(self) -> list[dict]:
            return [
                {"stock_id": "2330", "stock_name": "台積電",
                 "industry_category": "Semiconductor", "type": "twse"},
                {"stock_id": "2454", "stock_name": "聯發科",
                 "industry_category": "Semiconductor", "type": "twse"},
                {"stock_id": "6488", "stock_name": "環球晶",
                 "industry_category": "Semiconductor", "type": "tpex"},
            ]

    result = screen_universe(
        "TWSE+OTC", asof_date="2026-04-30", _conn=conn, _client=_StubClient()
    )
    assert result["ok"] is True
    assert result["data"]["asof_date_used"] == "2026-04-30"
    assert [c["symbol"] for c in result["data"]["candidates"]] == [
        "2330", "2454", "6488"
    ]
    written = conn.execute(
        "SELECT COUNT(*) FROM universe_daily WHERE asof_date = ?", ("2026-04-30",)
    ).fetchone()[0]
    assert written == 3


def test_cache_miss_without_client_returns_data_unavailable(conn) -> None:
    result = screen_universe(
        "TWSE", asof_date="2026-04-30", _conn=conn, _client=None
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "DATA_UNAVAILABLE"
    assert result["data"] is None


def test_custom_universe_intersection(conn) -> None:
    _seed_universe(
        conn,
        [
            _row("2330", "TWSE", name="台積電"),
            _row("2454", "TWSE"),
            _row("6488", "OTC"),
        ],
    )
    result = screen_universe(
        "custom",
        custom_symbols=["2330", "9999"],
        asof_date="2026-04-30",
        _conn=conn,
        _client=None,
    )
    assert [c["symbol"] for c in result["data"]["candidates"]] == ["2330"]


def test_ky_exclusion_drops_ky_symbols(conn) -> None:
    _seed_universe(
        conn,
        [
            _row("2330", "TWSE", name="台積電", is_ky=0),
            _row("9105KY", "TWSE", name="泰金寶-DR", is_ky=1),
        ],
    )
    result = screen_universe(
        "TWSE+OTC",
        filters=[{"kind": "negative_filter", "exclude": ["KY"]}],
        asof_date="2026-04-30",
        _conn=conn,
        _client=None,
    )
    assert [c["symbol"] for c in result["data"]["candidates"]] == ["2330"]


def test_empty_universe_after_filter_returns_success_with_empty(conn) -> None:
    _seed_universe(conn, [_row("9105KY", "TWSE", is_ky=1)])
    result = screen_universe(
        "TWSE",
        filters=[{"kind": "negative_filter", "exclude": ["KY"]}],
        asof_date="2026-04-30",
        _conn=conn,
        _client=None,
    )
    assert result["ok"] is True
    assert result["data"]["candidates"] == []


def test_volume_filter_below_threshold_drops_symbol(conn) -> None:
    _seed_universe(conn, [_row("2330", "TWSE")])
    bars = [
        BarRow(ts="2026-04-24", o=1, h=1, l=1, c=1, v=1, amount=80_000_000),
        BarRow(ts="2026-04-25", o=1, h=1, l=1, c=1, v=1, amount=80_000_000),
        BarRow(ts="2026-04-28", o=1, h=1, l=1, c=1, v=1, amount=80_000_000),
        BarRow(ts="2026-04-29", o=1, h=1, l=1, c=1, v=1, amount=80_000_000),
        BarRow(ts="2026-04-30", o=1, h=1, l=1, c=1, v=1, amount=80_000_000),
    ]
    insert_bars(conn, "2330", bars, "finmind", "t")
    result = screen_universe(
        "TWSE",
        filters=[{"kind": "volume_filter", "min_avg_dollar_volume_5d": 100_000_000}],
        asof_date="2026-04-30",
        _conn=conn,
        _client=None,
    )
    assert result["ok"] is True
    assert [c["symbol"] for c in result["data"]["candidates"]] == []


# ---------- INVALID_INPUT ----------


def test_unknown_universe_rejected(conn) -> None:
    result = screen_universe("US", _conn=conn, _client=None)
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_custom_missing_symbols_rejected(conn) -> None:
    result = screen_universe("custom", custom_symbols=None, _conn=conn, _client=None)
    assert result["error"]["code"] == "INVALID_INPUT"


def test_custom_bad_symbol_rejected(conn) -> None:
    result = screen_universe("custom", custom_symbols=["AAPL"], _conn=conn, _client=None)
    assert result["error"]["code"] == "INVALID_INPUT"


def test_unknown_filter_kind_rejected(conn) -> None:
    result = screen_universe(
        "TWSE",
        filters=[{"kind": "trend_template_filter"}],
        asof_date="2026-04-30",
        _conn=conn,
        _client=None,
    )
    assert result["error"]["code"] == "INVALID_INPUT"


def test_malformed_asof_date_rejected(conn) -> None:
    result = screen_universe(
        "TWSE", asof_date="2026/04/30", _conn=conn, _client=None
    )
    assert result["error"]["code"] == "INVALID_INPUT"


def test_unknown_negative_flag_returns_invalid_input(conn) -> None:
    _seed_universe(conn, [_row("2330", "TWSE")])
    result = screen_universe(
        "TWSE",
        filters=[{"kind": "negative_filter", "exclude": ["foo"]}],
        asof_date="2026-04-30",
        _conn=conn,
        _client=None,
    )
    assert result["error"]["code"] == "INVALID_INPUT"


def test_volume_filter_fail_fast_with_missing_bars_returns_data_unavailable(conn) -> None:
    _seed_universe(conn, [_row("2330", "TWSE")])
    bars = [
        BarRow(ts="2026-04-29", o=1, h=1, l=1, c=1, v=1, amount=200_000_000),
        BarRow(ts="2026-04-30", o=1, h=1, l=1, c=1, v=1, amount=200_000_000),
    ]
    insert_bars(conn, "2330", bars, "finmind", "t")
    result = screen_universe(
        "TWSE",
        filters=[
            {
                "kind": "volume_filter",
                "min_avg_dollar_volume_5d": 100_000_000,
                "error_policy": "fail_fast",
            }
        ],
        asof_date="2026-04-30",
        _conn=conn,
        _client=None,
    )
    assert result["error"]["code"] == "DATA_UNAVAILABLE"


# ---------- UPSTREAM_ERROR ----------


def test_upstream_connect_error_caught_as_envelope(conn) -> None:
    class _BoomClient:
        def get_taiwan_stock_info(self):
            raise httpx.ConnectError("boom")

    result = screen_universe(
        "TWSE", asof_date="2026-04-30", _conn=conn, _client=_BoomClient()
    )
    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == "UPSTREAM_ERROR"
    assert result["error"]["retriable"] is True
