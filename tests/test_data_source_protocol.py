"""Tests for ohmystock.data.sources.base.DataSource Protocol.

Spec: openspec/changes/market-data-fetch-cache/specs/market-data-cache/spec.md
"""

from __future__ import annotations

from ohmystock.data.sources.base import BarRow, DataSource


class _DummySource:
    name = "dummy"

    def fetch_daily(self, symbol: str, start: str, end: str) -> list[BarRow]:
        return []


def test_dummy_class_satisfies_data_source_protocol() -> None:
    obj = _DummySource()
    assert isinstance(obj, DataSource)
    assert obj.name == "dummy"
    assert obj.fetch_daily("2330", "2026-04-21", "2026-04-25") == []
