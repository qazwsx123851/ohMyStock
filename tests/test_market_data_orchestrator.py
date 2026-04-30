"""Tests for ohmystock.data.market_data.get_kline orchestrator.

Spec: openspec/changes/market-data-fetch-cache/specs/market-data-cache/spec.md
"""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from ohmystock.data.cache import init_market_data_schema, insert_bars
from ohmystock.data.market_data import (
    CODE_AUTH_FAILED,
    CODE_DATA_UNAVAILABLE,
    CODE_INVALID_INPUT,
    CODE_RATE_LIMIT,
    CODE_UPSTREAM_ERROR,
    _business_day_range,
    get_kline,
)
from ohmystock.data.sources.base import BarRow

END = "2026-04-24"  # Friday
TODAY = "2026-04-24"
WANTED = ["2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23", "2026-04-24"]


def _bar(ts: str, c: float = 105.0) -> BarRow:
    return BarRow(ts=ts, o=100.0, h=110.0, l=95.0, c=c, v=12345, amount=1_295_000_000)


class _FakeAdapter:
    def __init__(self, name: str, response: Any = None, exc: BaseException | None = None) -> None:
        self.name = name
        self._response = response if response is not None else []
        self._exc = exc
        self.calls: list[tuple[str, str, str]] = []

    def fetch_daily(self, symbol: str, start: str, end: str) -> list[BarRow]:
        self.calls.append((symbol, start, end))
        if self._exc is not None:
            raise self._exc
        return list(self._response)


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    try:
        init_market_data_schema(c)
        yield c
    finally:
        c.close()


# --- §8.1 spec scenarios -----------------------------------------------------


def test_success_returns_envelope_with_bars(conn: sqlite3.Connection) -> None:
    finmind = _FakeAdapter("finmind", response=[_bar(d) for d in WANTED])
    result = get_kline(
        "2330", bars=5, end_date=END, _conn=conn, _adapters=[finmind], _today=TODAY
    )

    assert result["ok"] is True
    assert result["error"] is None
    assert isinstance(result["elapsed_ms"], int)
    assert len(result["data"]["bars"]) == 5
    assert all(set(b.keys()) == {"ts", "o", "h", "l", "c", "v", "amount"} for b in result["data"]["bars"])


def test_intraday_period_rejected(conn: sqlite3.Connection) -> None:
    result = get_kline("2330", period="5m", _conn=conn, _adapters=[], _today=TODAY)
    assert result["ok"] is False
    assert result["error"]["code"] == CODE_INVALID_INPUT
    assert result["data"] is None


def test_empty_symbol_rejected(conn: sqlite3.Connection) -> None:
    result = get_kline("", _conn=conn, _adapters=[], _today=TODAY)
    assert result["ok"] is False
    assert result["error"]["code"] == CODE_INVALID_INPUT


def test_malformed_end_date_rejected(conn: sqlite3.Connection) -> None:
    result = get_kline("2330", end_date="2026/04/28", _conn=conn, _adapters=[], _today=TODAY)
    assert result["ok"] is False
    assert result["error"]["code"] == CODE_INVALID_INPUT


def test_second_call_hits_cache_only(conn: sqlite3.Connection) -> None:
    finmind = _FakeAdapter("finmind", response=[_bar(d) for d in WANTED])

    r1 = get_kline("2330", bars=5, end_date=END, _conn=conn, _adapters=[finmind], _today=TODAY)
    r2 = get_kline("2330", bars=5, end_date=END, _conn=conn, _adapters=[finmind], _today=TODAY)

    assert r1["ok"] is True and r2["ok"] is True
    assert len(finmind.calls) == 1, "second call should not hit upstream"
    assert [b["ts"] for b in r1["data"]["bars"]] == [b["ts"] for b in r2["data"]["bars"]]


def test_partial_cache_triggers_gap_fetch_only(conn: sqlite3.Connection) -> None:
    insert_bars(
        conn, "2330", [_bar(d) for d in WANTED[:-1]], "finmind", "2026-04-23T20:00:00+08:00"
    )
    finmind = _FakeAdapter("finmind", response=[_bar(WANTED[-1])])

    result = get_kline(
        "2330", bars=5, end_date=END, _conn=conn, _adapters=[finmind], _today=TODAY
    )

    assert result["ok"] is True
    assert len(result["data"]["bars"]) == 5
    assert len(finmind.calls) == 1
    _, fetch_start, fetch_end = finmind.calls[0]
    assert fetch_start == WANTED[-1]
    assert fetch_end == WANTED[-1]


def test_partial_cache_with_empty_upstream_is_data_unavailable(conn: sqlite3.Connection) -> None:
    insert_bars(
        conn, "2330", [_bar(WANTED[0])], "finmind", "2026-04-23T20:00:00+08:00"
    )
    adapter = _FakeAdapter("finmind", response=[])

    result = get_kline(
        "2330", bars=5, end_date=END, _conn=conn, _adapters=[adapter], _today=TODAY
    )

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == CODE_DATA_UNAVAILABLE
    assert "2026-04-21" in result["error"]["message"]


def test_partial_cache_with_rate_limit_surfaces_rate_limit(conn: sqlite3.Connection) -> None:
    insert_bars(
        conn, "2330", [_bar(WANTED[0])], "finmind", "2026-04-23T20:00:00+08:00"
    )
    adapter = _FakeAdapter("finmind", exc=RuntimeError("HTTP 429 quota exceeded"))

    result = get_kline(
        "2330", bars=5, end_date=END, _conn=conn, _adapters=[adapter], _today=TODAY
    )

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == CODE_RATE_LIMIT
    assert result["error"]["retriable"] is True


def test_finmind_fails_twstock_succeeds(conn: sqlite3.Connection) -> None:
    finmind = _FakeAdapter("finmind", exc=RuntimeError("connection reset"))
    twstock = _FakeAdapter("twstock", response=[_bar(d) for d in WANTED])
    yfinance = _FakeAdapter("yfinance", response=[_bar(d) for d in WANTED])

    result = get_kline(
        "2330", bars=5, end_date=END, _conn=conn,
        _adapters=[finmind, twstock, yfinance], _today=TODAY,
    )

    assert result["ok"] is True
    assert len(twstock.calls) == 1
    assert len(yfinance.calls) == 0, "fallback chain stops at first success"
    cur = conn.execute("SELECT DISTINCT source FROM bars_daily WHERE symbol=?", ("2330",))
    assert {r[0] for r in cur.fetchall()} == {"twstock"}


def test_finmind_429_maps_to_rate_limit(conn: sqlite3.Connection) -> None:
    finmind = _FakeAdapter("finmind", exc=RuntimeError("HTTP 429 quota exceeded"))
    twstock = _FakeAdapter("twstock", exc=RuntimeError("connection reset"))
    yfinance = _FakeAdapter("yfinance", exc=RuntimeError("network unreachable"))

    result = get_kline(
        "2330", bars=5, end_date=END, _conn=conn,
        _adapters=[finmind, twstock, yfinance], _today=TODAY,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == CODE_RATE_LIMIT
    assert result["error"]["retriable"] is True


# --- §8.2 / §8.3 / §8.4 ------------------------------------------------------


def test_finmind_401_maps_to_auth_failed_priority(conn: sqlite3.Connection) -> None:
    finmind = _FakeAdapter("finmind", exc=RuntimeError("HTTP 401 unauthorized"))
    twstock = _FakeAdapter("twstock", exc=RuntimeError("HTTP 502 bad gateway"))
    yfinance = _FakeAdapter("yfinance", exc=RuntimeError("HTTP 504 timeout"))

    result = get_kline(
        "2330", bars=5, end_date=END, _conn=conn,
        _adapters=[finmind, twstock, yfinance], _today=TODAY,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == CODE_AUTH_FAILED
    assert result["error"]["retriable"] is False


def test_all_adapters_return_empty_maps_to_data_unavailable(conn: sqlite3.Connection) -> None:
    adapters = [_FakeAdapter(name, response=[]) for name in ("finmind", "twstock", "yfinance")]
    result = get_kline(
        "9999", bars=5, end_date=END, _conn=conn, _adapters=adapters, _today=TODAY
    )

    assert result["ok"] is False
    assert result["error"]["code"] == CODE_DATA_UNAVAILABLE
    assert result["error"]["retriable"] is False


def test_all_adapters_5xx_maps_to_upstream_error(conn: sqlite3.Connection) -> None:
    adapters = [
        _FakeAdapter("finmind", exc=RuntimeError("HTTP 503 service unavailable")),
        _FakeAdapter("twstock", exc=RuntimeError("HTTP 502 bad gateway")),
        _FakeAdapter("yfinance", exc=RuntimeError("HTTP 500 internal")),
    ]
    result = get_kline(
        "2330", bars=5, end_date=END, _conn=conn, _adapters=adapters, _today=TODAY
    )

    assert result["ok"] is False
    assert result["error"]["code"] == CODE_UPSTREAM_ERROR
    assert result["error"]["retriable"] is True


# --- helper coverage ---------------------------------------------------------


def test_business_day_range_skips_weekends() -> None:
    assert _business_day_range("2026-04-24", 5) == [
        "2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23", "2026-04-24",
    ]


def test_business_day_range_crosses_month_boundary() -> None:
    assert _business_day_range("2026-05-04", 5) == [
        "2026-04-28", "2026-04-29", "2026-04-30", "2026-05-01", "2026-05-04",
    ]
