"""Base types for market data source adapters.

Spec: openspec/changes/market-data-fetch-cache/specs/market-data-cache/spec.md
"""

from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable


class BarRow(TypedDict):
    ts: str
    o: float
    h: float
    l: float
    c: float
    v: int
    amount: int


@runtime_checkable
class DataSource(Protocol):
    name: str

    def fetch_daily(self, symbol: str, start: str, end: str) -> list[BarRow]:
        ...
