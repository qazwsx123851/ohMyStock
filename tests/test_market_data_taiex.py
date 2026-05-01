"""Tests for get_kline accepting alphabetic index codes (TAIEX).

Spec: openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations

import sqlite3

import pytest

from ohmystock.data.cache import init_market_data_schema, select_bars
from ohmystock.data.market_data import CODE_INVALID_INPUT, get_kline
from ohmystock.data.sources.base import BarRow


def _bar(ts: str, c: float) -> BarRow:
    return BarRow(ts=ts, o=c, h=c, l=c, c=c, v=1000, amount=int(c * 1_000_000))


class _FakeFinMindIndex:
    name = "finmind"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def fetch_daily(self, symbol: str, start: str, end: str) -> list[BarRow]:
        self.calls.append((symbol, start, end))
        # Return three synthetic TAIEX-shaped daily bars.
        return [
            _bar("2026-04-22", 20100.0),
            _bar("2026-04-23", 20150.0),
            _bar("2026-04-24", 20200.0),
        ]


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_market_data_schema(c)
    try:
        yield c
    finally:
        c.close()


def test_taiex_symbol_accepted_by_validator(conn: sqlite3.Connection) -> None:
    fake = _FakeFinMindIndex()
    env = get_kline(
        "TAIEX",
        bars=3,
        end_date="2026-04-24",
        _conn=conn,
        _adapters=[fake],
        _today="2026-04-24",
    )
    assert env["ok"] is True
    assert env["error"] is None
    assert len(env["data"]["bars"]) == 3
    assert fake.calls and fake.calls[0][0] == "TAIEX"


def test_taiex_bars_cached_under_taiex_symbol(conn: sqlite3.Connection) -> None:
    fake = _FakeFinMindIndex()
    get_kline(
        "TAIEX",
        bars=3,
        end_date="2026-04-24",
        _conn=conn,
        _adapters=[fake],
        _today="2026-04-24",
    )
    cached = select_bars(conn, "TAIEX", "2026-04-22", "2026-04-24")
    assert [r["ts"] for r in cached] == [
        "2026-04-22",
        "2026-04-23",
        "2026-04-24",
    ]


def test_lowercase_alphabetic_symbol_rejected(conn: sqlite3.Connection) -> None:
    env = get_kline("taiex", bars=3, _conn=conn)
    assert env["ok"] is False
    assert env["error"]["code"] == CODE_INVALID_INPUT


def test_three_letter_index_accepted(conn: sqlite3.Connection) -> None:
    fake = _FakeFinMindIndex()
    env = get_kline(
        "OTC",
        bars=3,
        end_date="2026-04-24",
        _conn=conn,
        _adapters=[fake],
        _today="2026-04-24",
    )
    assert env["ok"] is True


def test_existing_numeric_symbol_still_works(conn: sqlite3.Connection) -> None:
    fake = _FakeFinMindIndex()
    env = get_kline(
        "2330",
        bars=3,
        end_date="2026-04-24",
        _conn=conn,
        _adapters=[fake],
        _today="2026-04-24",
    )
    assert env["ok"] is True


def test_two_letter_alphabetic_symbol_rejected(conn: sqlite3.Connection) -> None:
    env = get_kline("AB", bars=3, _conn=conn)
    assert env["ok"] is False
    assert env["error"]["code"] == CODE_INVALID_INPUT
