"""Tests for ohmystock.data.sources.yfinance.YFinanceSource.

Spec: openspec/changes/market-data-fetch-cache/specs/market-data-cache/spec.md
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [900.0, 901.0],
            "High": [910.0, 911.0],
            "Low": [895.0, 896.0],
            "Close": [905.0, 906.0],
            "Volume": [12_345_000, 13_000_000],
        },
        index=pd.DatetimeIndex(["2026-04-21", "2026-04-22"]),
    )


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(
        {"Open": [], "High": [], "Low": [], "Close": [], "Volume": []}
    )


def test_fetch_daily_normalizes_dataframe() -> None:
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = _df()
    with patch(
        "ohmystock.data.sources.yfinance.Ticker", return_value=fake_ticker
    ) as mock_ticker:
        from ohmystock.data.sources.yfinance import YFinanceSource

        bars = YFinanceSource().fetch_daily("2330", "2026-04-21", "2026-04-22")

    mock_ticker.assert_called_once_with("2330.TW")
    assert len(bars) == 2
    assert bars[0] == {
        "ts": "2026-04-21",
        "o": 900.0,
        "h": 910.0,
        "l": 895.0,
        "c": 905.0,
        "v": 12345,
        "amount": int(905.0 * 12_345_000),
    }
    assert bars[1]["ts"] == "2026-04-22"


def test_fetch_daily_falls_back_from_tw_to_two_when_first_empty() -> None:
    tw_ticker = MagicMock()
    tw_ticker.history.return_value = _empty_df()
    two_ticker = MagicMock()
    two_ticker.history.return_value = _df()

    with patch(
        "ohmystock.data.sources.yfinance.Ticker",
        side_effect=[tw_ticker, two_ticker],
    ) as mock_ticker:
        from ohmystock.data.sources.yfinance import YFinanceSource

        bars = YFinanceSource().fetch_daily("6488", "2026-04-21", "2026-04-22")

    assert [c.args[0] for c in mock_ticker.call_args_list] == ["6488.TW", "6488.TWO"]
    assert len(bars) == 2
