"""Tests for ohmystock.screener.cache.

Spec: openspec/changes/screener-tw-universe/specs/screener-tw-universe/spec.md
"""

from __future__ import annotations

import sqlite3

import pytest

from ohmystock.screener.cache import (
    aggregate_universe_rows,
    init_universe_schema,
    insert_universe_rows,
    latest_asof_within,
    select_universe_rows,
)


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    try:
        yield c
    finally:
        c.close()


# ---------- schema ----------


def test_init_schema_creates_universe_daily(conn) -> None:
    init_universe_schema(conn)
    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "universe_daily" in names


def test_init_schema_is_idempotent(conn) -> None:
    init_universe_schema(conn)
    init_universe_schema(conn)  # MUST NOT raise
    count = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
        "AND name = 'universe_daily'"
    ).fetchone()[0]
    assert count == 1


# ---------- aggregator ----------


def test_aggregate_maps_twse_and_tpex() -> None:
    raw = [
        {
            "stock_id": "2330",
            "stock_name": "台積電",
            "industry_category": "Semiconductor",
            "type": "twse",
        },
        {
            "stock_id": "6488",
            "stock_name": "環球晶",
            "industry_category": "Semiconductor",
            "type": "tpex",
        },
    ]
    out = aggregate_universe_rows(raw, asof_date="2026-04-30")
    assert [r["market"] for r in out] == ["TWSE", "OTC"]


def test_aggregate_derives_is_ky_true() -> None:
    raw = [
        {
            "stock_id": "9105KY",
            "stock_name": "泰金寶-DR",
            "industry_category": "Other Electronic",
            "type": "twse",
        }
    ]
    out = aggregate_universe_rows(raw, asof_date="2026-04-30")
    assert out[0]["is_ky"] == 1


def test_aggregate_derives_is_ky_false() -> None:
    raw = [
        {
            "stock_id": "2330",
            "stock_name": "台積電",
            "industry_category": "Semiconductor",
            "type": "twse",
        }
    ]
    out = aggregate_universe_rows(raw, asof_date="2026-04-30")
    assert out[0]["is_ky"] == 0


def test_aggregate_warning_disposal_fully_paid_zero() -> None:
    raw = [
        {
            "stock_id": "2330",
            "stock_name": "台積電",
            "industry_category": "Semiconductor",
            "type": "twse",
        }
    ]
    out = aggregate_universe_rows(raw, asof_date="2026-04-30")
    assert out[0]["is_warning"] == 0
    assert out[0]["is_disposal"] == 0
    assert out[0]["is_fully_paid"] == 0


def test_aggregate_sorts_by_symbol_asc() -> None:
    raw = [
        {"stock_id": "6488", "stock_name": "B", "industry_category": "x", "type": "tpex"},
        {"stock_id": "2330", "stock_name": "A", "industry_category": "x", "type": "twse"},
        {"stock_id": "2454", "stock_name": "C", "industry_category": "x", "type": "twse"},
    ]
    out = aggregate_universe_rows(raw, asof_date="2026-04-30")
    assert [r["symbol"] for r in out] == ["2330", "2454", "6488"]


def test_aggregate_skips_unknown_type() -> None:
    raw = [
        {"stock_id": "AAPL", "stock_name": "Apple", "industry_category": "x", "type": "us"},
        {"stock_id": "2330", "stock_name": "A", "industry_category": "x", "type": "twse"},
    ]
    out = aggregate_universe_rows(raw, asof_date="2026-04-30")
    assert [r["symbol"] for r in out] == ["2330"]


# ---------- insert / select ----------


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


def test_insert_select_round_trip(conn) -> None:
    init_universe_schema(conn)
    rows = [
        _row("2330", "TWSE", name="台積電", industry="Semiconductor"),
        _row("6488", "OTC", name="環球晶", industry="Semiconductor"),
    ]
    written = insert_universe_rows(
        conn, rows, "finmind", "2026-04-30T17:30:00+08:00"
    )
    assert written == 2

    got = select_universe_rows(conn, "2026-04-30")
    assert [r["symbol"] for r in got] == ["2330", "6488"]
    assert got[0]["market"] == "TWSE"
    assert got[1]["market"] == "OTC"


def test_select_market_filter(conn) -> None:
    init_universe_schema(conn)
    insert_universe_rows(
        conn,
        [_row("2330", "TWSE"), _row("6488", "OTC")],
        "finmind",
        "t",
    )
    twse_only = select_universe_rows(conn, "2026-04-30", market_filter="TWSE")
    assert [r["symbol"] for r in twse_only] == ["2330"]


def test_insert_or_ignore_keeps_original(conn) -> None:
    init_universe_schema(conn)
    insert_universe_rows(conn, [_row("2330", "TWSE", name="原始")], "finmind", "t1")
    insert_universe_rows(conn, [_row("2330", "TWSE", name="新名字")], "finmind", "t2")
    got = select_universe_rows(conn, "2026-04-30")
    assert got[0]["name"] == "原始"


def test_insert_empty_returns_zero(conn) -> None:
    init_universe_schema(conn)
    assert insert_universe_rows(conn, [], "finmind", "t") == 0


# ---------- latest_asof_within ----------


def test_latest_asof_within_exact_match(conn) -> None:
    init_universe_schema(conn)
    insert_universe_rows(
        conn, [_row("2330", "TWSE", asof="2026-04-30")], "finmind", "t"
    )
    assert latest_asof_within(conn, "2026-04-30") == "2026-04-30"


def test_latest_asof_within_fallback_picks_most_recent_within_window(conn) -> None:
    init_universe_schema(conn)
    insert_universe_rows(
        conn,
        [
            _row("2330", "TWSE", asof="2026-04-28"),
            _row("2330", "TWSE", asof="2026-04-30"),
        ],
        "finmind",
        "t",
    )
    # Saturday 2026-05-02 -> falls back to most recent <= target
    assert latest_asof_within(conn, "2026-05-02") == "2026-04-30"


def test_latest_asof_within_returns_none_outside_window(conn) -> None:
    init_universe_schema(conn)
    insert_universe_rows(
        conn, [_row("2330", "TWSE", asof="2026-01-01")], "finmind", "t"
    )
    # 2026-04-30 is more than 30 days after 2026-01-01.
    assert latest_asof_within(conn, "2026-04-30", lookback_days=30) is None


def test_latest_asof_within_no_rows_returns_none(conn) -> None:
    init_universe_schema(conn)
    assert latest_asof_within(conn, "2026-04-30") is None
