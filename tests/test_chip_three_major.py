"""Tests for ohmystock.chip.three_major.get_three_major_investors.

Spec: openspec/changes/chip-data-skill/specs/chip-data-skill/spec.md
"""

from __future__ import annotations

import sqlite3

import pytest

from ohmystock.chip.cache import init_chip_schema, insert_three_major_rows
from ohmystock.chip.three_major import get_three_major_investors


class FakeClient:
    """Records calls and returns canned FinMind rows."""

    def __init__(self, rows=None, raises=None):
        self.rows = rows if rows is not None else []
        self.raises = raises
        self.calls: list[tuple[str, str, str]] = []

    def get_institutional_investors_buy_sell(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        if self.raises is not None:
            raise self.raises
        return list(self.rows)


class ExplodingClient:
    def get_institutional_investors_buy_sell(self, *a, **k):  # pragma: no cover
        raise AssertionError("client must not be called when cache is fully populated")


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    init_chip_schema(c)
    try:
        yield c
    finally:
        c.close()


# ---------- success path ----------


def test_full_cache_hit_does_not_call_client(conn) -> None:
    insert_three_major_rows(
        conn,
        [
            {"symbol": "2330", "date": "2026-04-29",
             "foreign_net": 8_000_000, "invest_trust_net": 1_200_000,
             "prop_dealer_net": 250_000},
        ],
        "finmind",
        "t",
    )
    result = get_three_major_investors(
        "2330", days=1, end_date="2026-04-29",
        _conn=conn, _client=ExplodingClient(),
    )
    assert result["ok"] is True
    assert result["error"] is None
    assert result["data"]["rows"] == [
        {"date": "2026-04-29",
         "foreign_net": 8_000,
         "invest_trust_net": 1_200,
         "prop_dealer_net": 250},
    ]


def test_partial_cache_miss_triggers_narrow_fetch(conn) -> None:
    # Business days walking back from 2026-04-29 (Wed):
    # 2026-04-23 Thu, 04-24 Fri, 04-27 Mon, 04-28 Tue, 04-29 Wed.
    insert_three_major_rows(
        conn,
        [
            {"symbol": "2330", "date": "2026-04-23",
             "foreign_net": 1_000_000, "invest_trust_net": 0, "prop_dealer_net": 0},
            {"symbol": "2330", "date": "2026-04-24",
             "foreign_net": 2_000_000, "invest_trust_net": 0, "prop_dealer_net": 0},
            {"symbol": "2330", "date": "2026-04-27",
             "foreign_net": 3_000_000, "invest_trust_net": 0, "prop_dealer_net": 0},
        ],
        "finmind",
        "t",
    )
    fake_rows = [
        {"date": "2026-04-28", "stock_id": "2330", "name": "Foreign_Investor",
         "buy": 4_000_000, "sell": 0},
        {"date": "2026-04-29", "stock_id": "2330", "name": "Foreign_Investor",
         "buy": 5_000_000, "sell": 0},
    ]
    client = FakeClient(rows=fake_rows)

    result = get_three_major_investors(
        "2330", days=5, end_date="2026-04-29",
        _conn=conn, _client=client,
    )
    assert result["ok"] is True
    assert client.calls == [("2330", "2026-04-28", "2026-04-29")]
    dates = [r["date"] for r in result["data"]["rows"]]
    assert dates == ["2026-04-23", "2026-04-24", "2026-04-27", "2026-04-28", "2026-04-29"]


def test_full_miss_empty_upstream_returns_data_unavailable(conn) -> None:
    client = FakeClient(rows=[])
    result = get_three_major_investors(
        "2330", days=5, end_date="2026-04-29",
        _conn=conn, _client=client,
    )
    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == "DATA_UNAVAILABLE"
    assert result["error"]["retriable"] is False


def test_partial_cache_with_empty_upstream_returns_data_unavailable(conn) -> None:
    insert_three_major_rows(
        conn,
        [
            {"symbol": "2330", "date": "2026-04-23",
             "foreign_net": 1_000_000, "invest_trust_net": 0, "prop_dealer_net": 0},
        ],
        "finmind",
        "t",
    )
    client = FakeClient(rows=[])

    result = get_three_major_investors(
        "2330", days=5, end_date="2026-04-29",
        _conn=conn, _client=client,
    )

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == "DATA_UNAVAILABLE"
    assert "2026-04-24" in result["error"]["message"]


def test_partial_cache_with_rate_limit_surfaces_rate_limit(conn) -> None:
    insert_three_major_rows(
        conn,
        [
            {"symbol": "2330", "date": "2026-04-23",
             "foreign_net": 1_000_000, "invest_trust_net": 0, "prop_dealer_net": 0},
        ],
        "finmind",
        "t",
    )
    client = FakeClient(raises=RuntimeError("FinMind returned HTTP 429 Too Many Requests"))

    result = get_three_major_investors(
        "2330", days=5, end_date="2026-04-29",
        _conn=conn, _client=client,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "RATE_LIMIT"
    assert result["error"]["retriable"] is True


def test_shares_to_lots_conversion_at_boundary(conn) -> None:
    insert_three_major_rows(
        conn,
        [
            {"symbol": "2330", "date": "2026-04-29",
             "foreign_net": 12_400_500,   # 12_400 lots + 500 shares (truncates toward 0)
             "invest_trust_net": -3_500,  # -3 lots + 500 shares (truncates toward 0)
             "prop_dealer_net": 999},     # < 1 lot
        ],
        "finmind",
        "t",
    )
    result = get_three_major_investors(
        "2330", days=1, end_date="2026-04-29",
        _conn=conn, _client=ExplodingClient(),
    )
    row = result["data"]["rows"][0]
    assert row["foreign_net"] == 12_400
    assert row["invest_trust_net"] == -3   # truncate-toward-zero of -3.5 → -3
    assert row["prop_dealer_net"] == 0


# ---------- validation ----------


def test_invalid_symbol_returns_invalid_input() -> None:
    result = get_three_major_investors("AAPL", days=30)
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_zero_days_returns_invalid_input() -> None:
    result = get_three_major_investors("2330", days=0)
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_malformed_end_date_returns_invalid_input() -> None:
    result = get_three_major_investors("2330", days=30, end_date="2026/04/29")
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_impossible_end_date_returns_invalid_input() -> None:
    result = get_three_major_investors("2330", days=30, end_date="2026-02-31")
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


# ---------- error classification ----------


def test_rate_limit_classified(conn) -> None:
    client = FakeClient(raises=RuntimeError("FinMind returned HTTP 429 Too Many Requests"))
    result = get_three_major_investors(
        "2330", days=1, end_date="2026-04-29",
        _conn=conn, _client=client,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "RATE_LIMIT"
    assert result["error"]["retriable"] is True


def test_auth_failed_classified(conn) -> None:
    client = FakeClient(raises=RuntimeError("FinMind returned HTTP 401 unauthorized"))
    result = get_three_major_investors(
        "2330", days=1, end_date="2026-04-29",
        _conn=conn, _client=client,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "AUTH_FAILED"
    assert result["error"]["retriable"] is False


def test_upstream_error_classified(conn) -> None:
    client = FakeClient(raises=RuntimeError("connection reset by peer"))
    result = get_three_major_investors(
        "2330", days=1, end_date="2026-04-29",
        _conn=conn, _client=client,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "UPSTREAM_ERROR"
    assert result["error"]["retriable"] is True
