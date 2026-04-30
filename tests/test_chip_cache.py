"""Tests for ohmystock.chip.cache.

Spec: openspec/changes/chip-data-skill/specs/chip-data-skill/spec.md
"""

from __future__ import annotations

import sqlite3

import pytest

from ohmystock.chip.cache import (
    aggregate_three_major,
    init_chip_schema,
    insert_margin_short_rows,
    insert_three_major_rows,
    select_margin_short_rows,
    select_three_major_rows,
)


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    try:
        yield c
    finally:
        c.close()


# ---------- schema ----------


def test_init_chip_schema_creates_both_tables(conn) -> None:
    init_chip_schema(conn)
    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "chip_three_major_daily" in names
    assert "chip_margin_short_daily" in names


def test_init_chip_schema_is_idempotent(conn) -> None:
    init_chip_schema(conn)
    init_chip_schema(conn)  # MUST NOT raise
    count = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
        "AND name IN ('chip_three_major_daily', 'chip_margin_short_daily')"
    ).fetchone()[0]
    assert count == 2


# ---------- aggregator ----------


def test_aggregate_three_major_collapses_legs() -> None:
    raw = [
        {"date": "2026-04-29", "stock_id": "2330", "name": "Foreign_Investor",
         "buy": 10_000_000, "sell": 2_000_000},
        {"date": "2026-04-29", "stock_id": "2330", "name": "Foreign_Dealer_Self",
         "buy": 0, "sell": 0},
        {"date": "2026-04-29", "stock_id": "2330", "name": "Investment_Trust",
         "buy": 1_500_000, "sell": 300_000},
        {"date": "2026-04-29", "stock_id": "2330", "name": "Dealer_self",
         "buy": 500_000, "sell": 300_000},
        {"date": "2026-04-29", "stock_id": "2330", "name": "Dealer_Hedging",
         "buy": 100_000, "sell": 50_000},
    ]
    out = aggregate_three_major(raw)
    assert len(out) == 1
    row = out[0]
    assert row["symbol"] == "2330"
    assert row["date"] == "2026-04-29"
    assert row["foreign_net"] == 8_000_000
    assert row["invest_trust_net"] == 1_200_000
    assert row["prop_dealer_net"] == 250_000


def test_aggregate_three_major_missing_legs_zero() -> None:
    raw = [
        {"date": "2026-04-29", "stock_id": "2330", "name": "Foreign_Investor",
         "buy": 10_000_000, "sell": 2_000_000},
    ]
    out = aggregate_three_major(raw)
    assert out[0]["invest_trust_net"] == 0
    assert out[0]["prop_dealer_net"] == 0


def test_aggregate_three_major_sorts_by_symbol_date() -> None:
    raw = [
        {"date": "2026-04-30", "stock_id": "2330", "name": "Foreign_Investor",
         "buy": 1, "sell": 0},
        {"date": "2026-04-29", "stock_id": "2330", "name": "Foreign_Investor",
         "buy": 1, "sell": 0},
        {"date": "2026-04-29", "stock_id": "1101", "name": "Foreign_Investor",
         "buy": 1, "sell": 0},
    ]
    out = aggregate_three_major(raw)
    keys = [(r["symbol"], r["date"]) for r in out]
    assert keys == [
        ("1101", "2026-04-29"),
        ("2330", "2026-04-29"),
        ("2330", "2026-04-30"),
    ]


def test_aggregate_three_major_unknown_name_yields_zero_row() -> None:
    raw = [
        {"date": "2026-04-29", "stock_id": "2330", "name": "Mystery_Bot",
         "buy": 999, "sell": 0},
    ]
    out = aggregate_three_major(raw)
    assert out == [{"symbol": "2330", "date": "2026-04-29",
                    "foreign_net": 0, "invest_trust_net": 0, "prop_dealer_net": 0}]


# ---------- three-major insert / select ----------


def test_insert_select_three_major_round_trip(conn) -> None:
    init_chip_schema(conn)
    rows = [
        {"symbol": "2330", "date": "2026-04-28",
         "foreign_net": 1_000_000, "invest_trust_net": 0, "prop_dealer_net": 0},
        {"symbol": "2330", "date": "2026-04-29",
         "foreign_net": 8_000_000, "invest_trust_net": 1_200_000, "prop_dealer_net": 250_000},
    ]
    written = insert_three_major_rows(
        conn, rows, "finmind", "2026-04-29T17:30:00+08:00"
    )
    assert written == 2

    got = select_three_major_rows(conn, "2330", "2026-04-28", "2026-04-29")
    assert got == [
        {"date": "2026-04-28", "foreign_net": 1_000_000,
         "invest_trust_net": 0, "prop_dealer_net": 0},
        {"date": "2026-04-29", "foreign_net": 8_000_000,
         "invest_trust_net": 1_200_000, "prop_dealer_net": 250_000},
    ]


def test_insert_three_major_or_ignore(conn) -> None:
    init_chip_schema(conn)
    rows = [{"symbol": "2330", "date": "2026-04-29",
             "foreign_net": 100, "invest_trust_net": 0, "prop_dealer_net": 0}]
    insert_three_major_rows(conn, rows, "finmind", "t1")
    rows2 = [{"symbol": "2330", "date": "2026-04-29",
              "foreign_net": 999, "invest_trust_net": 0, "prop_dealer_net": 0}]
    insert_three_major_rows(conn, rows2, "finmind", "t2")
    got = select_three_major_rows(conn, "2330", "2026-04-29", "2026-04-29")
    assert got[0]["foreign_net"] == 100  # original kept


def test_insert_three_major_empty_returns_zero(conn) -> None:
    init_chip_schema(conn)
    assert insert_three_major_rows(conn, [], "finmind", "t") == 0


# ---------- margin / short insert / select ----------


def test_insert_margin_short_computes_ratio(conn) -> None:
    init_chip_schema(conn)
    raw = [
        {"date": "2026-04-29", "stock_id": "2330",
         "MarginPurchaseTodayBalance": 100_000,
         "MarginPurchaseYesterdayBalance": 98_500,
         "ShortSaleTodayBalance": 4_200,
         "ShortSaleYesterdayBalance": 4_300},
    ]
    insert_margin_short_rows(conn, raw, "finmind", "2026-04-29T17:30:00+08:00")
    got = select_margin_short_rows(conn, "2330", "2026-04-29", "2026-04-29")
    assert len(got) == 1
    row = got[0]
    assert row["margin_balance"] == 100_000
    assert row["margin_change"] == 1_500
    assert row["short_balance"] == 4_200
    assert row["short_change"] == -100
    assert row["short_to_margin_ratio"] == 4.2


def test_insert_margin_short_zero_margin_balance_safe(conn) -> None:
    init_chip_schema(conn)
    raw = [
        {"date": "2026-04-29", "stock_id": "9999",
         "MarginPurchaseTodayBalance": 0,
         "MarginPurchaseYesterdayBalance": 0,
         "ShortSaleTodayBalance": 100,
         "ShortSaleYesterdayBalance": 0},
    ]
    insert_margin_short_rows(conn, raw, "finmind", "t")
    got = select_margin_short_rows(conn, "9999", "2026-04-29", "2026-04-29")
    assert got[0]["short_to_margin_ratio"] == 0.0


def test_insert_margin_short_or_ignore(conn) -> None:
    init_chip_schema(conn)
    raw = [
        {"date": "2026-04-29", "stock_id": "2330",
         "MarginPurchaseTodayBalance": 100_000,
         "MarginPurchaseYesterdayBalance": 100_000,
         "ShortSaleTodayBalance": 4_000,
         "ShortSaleYesterdayBalance": 4_000},
    ]
    insert_margin_short_rows(conn, raw, "finmind", "t1")
    raw2 = [
        {"date": "2026-04-29", "stock_id": "2330",
         "MarginPurchaseTodayBalance": 999,
         "MarginPurchaseYesterdayBalance": 999,
         "ShortSaleTodayBalance": 1,
         "ShortSaleYesterdayBalance": 1},
    ]
    insert_margin_short_rows(conn, raw2, "finmind", "t2")
    got = select_margin_short_rows(conn, "2330", "2026-04-29", "2026-04-29")
    assert got[0]["margin_balance"] == 100_000  # original kept
