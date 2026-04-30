"""Tests for ohmystock.data.sources.twstock.TwstockSource.

Spec: openspec/changes/market-data-fetch-cache/specs/market-data-cache/spec.md
"""

from __future__ import annotations

from collections import namedtuple
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

Data = namedtuple(
    "Data",
    "date capacity turnover open high low close change transaction",
)


def _row(year: int, month: int, day: int) -> Data:
    return Data(
        date=datetime(year, month, day),
        capacity=12_345_000,
        turnover=11_165_000_000,
        open=900.0,
        high=910.0,
        low=895.0,
        close=905.0,
        change=5.0,
        transaction=8000,
    )


def test_fetch_daily_normalizes_and_filters_range() -> None:
    fake_stock = MagicMock()
    fake_stock.fetch_from.return_value = [
        _row(2026, 4, 18),  # before start
        _row(2026, 4, 21),  # in range
        _row(2026, 4, 23),  # in range
        _row(2026, 4, 30),  # after end
    ]
    with patch("ohmystock.data.sources.twstock.Stock", return_value=fake_stock):
        from ohmystock.data.sources.twstock import TwstockSource

        bars = TwstockSource().fetch_daily("2330", "2026-04-21", "2026-04-25")

    fake_stock.fetch_from.assert_called_once_with(2026, 4)
    assert [b["ts"] for b in bars] == ["2026-04-21", "2026-04-23"]
    assert bars[0] == {
        "ts": "2026-04-21",
        "o": 900.0,
        "h": 910.0,
        "l": 895.0,
        "c": 905.0,
        "v": 12345,
        "amount": 11_165_000_000,
    }


def test_fetch_daily_wraps_sdk_exception_as_runtime_error() -> None:
    with patch("ohmystock.data.sources.twstock.Stock", side_effect=ValueError("boom")):
        from ohmystock.data.sources.twstock import TwstockSource

        with pytest.raises(RuntimeError, match="twstock failed for 2330: boom"):
            TwstockSource().fetch_daily("2330", "2026-04-21", "2026-04-25")
