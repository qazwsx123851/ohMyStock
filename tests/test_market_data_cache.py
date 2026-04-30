"""Tests for ohmystock.data.cache.

Spec: openspec/changes/market-data-fetch-cache/specs/market-data-cache/spec.md
"""

from __future__ import annotations

import sqlite3

import pytest

from ohmystock.data.cache import (
    init_market_data_schema,
    insert_bars,
    select_bars,
)
from ohmystock.data.sources.base import BarRow


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    try:
        init_market_data_schema(c)
        yield c
    finally:
        c.close()


def _row(date: str, close: float = 905.0) -> BarRow:
    return BarRow(
        ts=date, o=900.0, h=910.0, l=895.0, c=close, v=12345, amount=11_165_000_000
    )


def test_init_market_data_schema_is_idempotent() -> None:
    c = sqlite3.connect(":memory:")
    try:
        init_market_data_schema(c)
        init_market_data_schema(c)

        cur = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bars_daily'"
        )
        assert len(cur.fetchall()) == 1
    finally:
        c.close()


def test_primary_key_prevents_duplicates(conn: sqlite3.Connection) -> None:
    insert_bars(conn, "2330", [_row("2026-04-21")], "finmind", "2026-04-29T20:00:00+08:00")
    insert_bars(
        conn, "2330", [_row("2026-04-21", close=999.0)], "twstock", "2026-04-29T20:01:00+08:00"
    )

    cur = conn.execute(
        "SELECT COUNT(*), c, source FROM bars_daily WHERE symbol=? AND date=?",
        ("2330", "2026-04-21"),
    )
    count, close, source = cur.fetchone()
    assert count == 1
    assert close == 905.0
    assert source == "finmind"


def test_select_bars_range_query_returns_sorted_rows(conn: sqlite3.Connection) -> None:
    insert_bars(
        conn,
        "2330",
        [
            _row("2026-04-23"),
            _row("2026-04-21"),
            _row("2026-04-22"),
            _row("2026-04-25"),
        ],
        "finmind",
        "2026-04-29T20:00:00+08:00",
    )
    insert_bars(conn, "2454", [_row("2026-04-21")], "finmind", "2026-04-29T20:00:00+08:00")

    rows = select_bars(conn, "2330", "2026-04-22", "2026-04-24")

    assert [r["ts"] for r in rows] == ["2026-04-22", "2026-04-23"]
    assert all(set(r.keys()) == {"ts", "o", "h", "l", "c", "v", "amount"} for r in rows)
