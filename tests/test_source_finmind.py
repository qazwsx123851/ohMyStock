"""Tests for ohmystock.data.sources.finmind.FinMindSource.

Spec: openspec/changes/market-data-fetch-cache/specs/market-data-cache/spec.md
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ohmystock.data.finmind_client import FinMindConnectionError


def _raw_row(date: str = "2026-04-21") -> dict:
    return {
        "date": date,
        "stock_id": "2330",
        "open": 900.0,
        "max": 910.0,
        "min": 895.0,
        "close": 905.0,
        "Trading_Volume": 12_345_000,
        "Trading_money": 11_165_000_000,
        "spread": 5.0,
        "Trading_turnover": 8000,
    }


def test_fetch_daily_normalizes_raw_rows() -> None:
    with patch(
        "ohmystock.data.sources.finmind.FinMindClient.get_taiwan_stock_price",
        return_value=[_raw_row("2026-04-21"), _raw_row("2026-04-22")],
    ):
        from ohmystock.data.sources.finmind import FinMindSource

        bars = FinMindSource().fetch_daily("2330", "2026-04-21", "2026-04-22")

    assert len(bars) == 2
    assert bars[0] == {
        "ts": "2026-04-21",
        "o": 900.0,
        "h": 910.0,
        "l": 895.0,
        "c": 905.0,
        "v": 12345,
        "amount": 11_165_000_000,
    }
    assert bars[1]["ts"] == "2026-04-22"


def test_fetch_daily_propagates_finmind_connection_error() -> None:
    with patch(
        "ohmystock.data.sources.finmind.FinMindClient.get_taiwan_stock_price",
        side_effect=FinMindConnectionError("HTTP 429"),
    ):
        from ohmystock.data.sources.finmind import FinMindSource

        with pytest.raises(FinMindConnectionError, match="429"):
            FinMindSource().fetch_daily("2330", "2026-04-21", "2026-04-22")
