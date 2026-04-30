"""Tests for ohmystock.chip.margin_short.get_margin_short.

Spec: openspec/changes/chip-data-skill/specs/chip-data-skill/spec.md
"""

from __future__ import annotations

import sqlite3

import pytest

from ohmystock.chip.cache import init_chip_schema, insert_margin_short_rows
from ohmystock.chip.margin_short import get_margin_short


class FakeClient:
    def __init__(self, rows=None, raises=None):
        self.rows = rows if rows is not None else []
        self.raises = raises
        self.calls: list[tuple[str, str, str]] = []

    def get_margin_purchase_short_sale(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        if self.raises is not None:
            raise self.raises
        return list(self.rows)


class ExplodingClient:
    def get_margin_purchase_short_sale(self, *a, **k):  # pragma: no cover
        raise AssertionError("client must not be called when cache is fully populated")


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    init_chip_schema(c)
    try:
        yield c
    finally:
        c.close()


def _raw(date_str: str, margin_today: int, margin_yest: int,
         short_today: int, short_yest: int) -> dict:
    return {
        "date": date_str, "stock_id": "2330",
        "MarginPurchaseTodayBalance": margin_today,
        "MarginPurchaseYesterdayBalance": margin_yest,
        "ShortSaleTodayBalance": short_today,
        "ShortSaleYesterdayBalance": short_yest,
    }


# ---------- success ----------


def test_full_cache_hit_does_not_call_client(conn) -> None:
    insert_margin_short_rows(
        conn, [_raw("2026-04-29", 100_000, 98_500, 4_200, 4_300)], "finmind", "t"
    )
    result = get_margin_short(
        "2330", days=1, end_date="2026-04-29",
        _conn=conn, _client=ExplodingClient(),
    )
    assert result["ok"] is True
    assert result["error"] is None
    row = result["data"]["rows"][0]
    assert row["margin_balance"] == 100_000
    assert row["short_balance"] == 4_200
    assert row["short_to_margin_ratio"] == 4.2  # surfaced unchanged from cache


def test_partial_cache_miss_triggers_narrow_fetch(conn) -> None:
    # 2026-04-23 Thu, 04-24 Fri, 04-27 Mon, 04-28 Tue, 04-29 Wed
    insert_margin_short_rows(
        conn,
        [
            _raw("2026-04-23", 90_000, 89_000, 3_000, 3_100),
            _raw("2026-04-24", 91_000, 90_000, 3_050, 3_000),
            _raw("2026-04-27", 92_000, 91_000, 3_100, 3_050),
        ],
        "finmind",
        "t",
    )
    fake_rows = [
        _raw("2026-04-28", 95_000, 92_000, 3_500, 3_100),
        _raw("2026-04-29", 100_000, 95_000, 4_200, 3_500),
    ]
    client = FakeClient(rows=fake_rows)

    result = get_margin_short(
        "2330", days=5, end_date="2026-04-29",
        _conn=conn, _client=client,
    )
    assert result["ok"] is True
    assert client.calls == [("2330", "2026-04-28", "2026-04-29")]
    dates = [r["date"] for r in result["data"]["rows"]]
    assert dates == ["2026-04-23", "2026-04-24", "2026-04-27", "2026-04-28", "2026-04-29"]


def test_full_miss_empty_upstream_returns_data_unavailable(conn) -> None:
    client = FakeClient(rows=[])
    result = get_margin_short(
        "2330", days=5, end_date="2026-04-29",
        _conn=conn, _client=client,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "DATA_UNAVAILABLE"
    assert result["error"]["retriable"] is False


def test_ratio_computed_from_fetched_rows(conn) -> None:
    fake_rows = [_raw("2026-04-29", 100_000, 100_000, 4_200, 4_200)]
    client = FakeClient(rows=fake_rows)
    result = get_margin_short(
        "2330", days=1, end_date="2026-04-29",
        _conn=conn, _client=client,
    )
    assert result["ok"] is True
    assert result["data"]["rows"][0]["short_to_margin_ratio"] == 4.2


# ---------- validation ----------


def test_invalid_symbol_returns_invalid_input() -> None:
    result = get_margin_short("AAPL", days=30)
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_zero_days_returns_invalid_input() -> None:
    result = get_margin_short("2330", days=0)
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_malformed_end_date_returns_invalid_input() -> None:
    result = get_margin_short("2330", days=30, end_date="2026/04/29")
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


# ---------- error classification ----------


def test_rate_limit_classified(conn) -> None:
    client = FakeClient(raises=RuntimeError("FinMind returned HTTP 429 Too Many Requests"))
    result = get_margin_short(
        "2330", days=1, end_date="2026-04-29",
        _conn=conn, _client=client,
    )
    assert result["error"]["code"] == "RATE_LIMIT"
    assert result["error"]["retriable"] is True


def test_auth_failed_classified(conn) -> None:
    client = FakeClient(raises=RuntimeError("FinMind returned HTTP 403 forbidden"))
    result = get_margin_short(
        "2330", days=1, end_date="2026-04-29",
        _conn=conn, _client=client,
    )
    assert result["error"]["code"] == "AUTH_FAILED"
    assert result["error"]["retriable"] is False


def test_upstream_error_classified(conn) -> None:
    client = FakeClient(raises=RuntimeError("connection reset by peer"))
    result = get_margin_short(
        "2330", days=1, end_date="2026-04-29",
        _conn=conn, _client=client,
    )
    assert result["error"]["code"] == "UPSTREAM_ERROR"
    assert result["error"]["retriable"] is True
