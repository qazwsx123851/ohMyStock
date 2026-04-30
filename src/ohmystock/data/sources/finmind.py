"""FinMind adapter for the DataSource protocol.

Spec: openspec/changes/market-data-fetch-cache/specs/market-data-cache/spec.md
"""

from __future__ import annotations

from ohmystock.data.finmind_client import FinMindClient
from ohmystock.data.sources.base import BarRow


class FinMindSource:
    name = "finmind"

    def __init__(self) -> None:
        self._client = FinMindClient()

    def fetch_daily(self, symbol: str, start: str, end: str) -> list[BarRow]:
        rows = self._client.get_taiwan_stock_price(symbol, start, end)
        return [_normalize(r) for r in rows]


def _normalize(row: dict) -> BarRow:
    # Trading_Volume is in shares; //1000 to 張 keeps units consistent with
    # twstock/yfinance adapters and the bars_daily cache.
    return BarRow(
        ts=row["date"],
        o=float(row["open"]),
        h=float(row["max"]),
        l=float(row["min"]),
        c=float(row["close"]),
        v=int(row["Trading_Volume"]) // 1000,
        amount=int(row["Trading_money"]),
    )
