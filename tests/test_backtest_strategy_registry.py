"""Unit tests for ``ohmystock.backtest.strategy.registry``.

Spec: openspec/changes/web-admin-backtest-pages/specs/admin-backtest-endpoints/spec.md
"""

from __future__ import annotations

import pytest

from ohmystock.backtest import strategy as strategy_pkg
from ohmystock.backtest.strategy.registry import available_strategies


class _Broken:
    """A class that raises during construction."""

    name = "broken_strategy"

    def __init__(self) -> None:
        raise RuntimeError("boom")

    def warmup_bars(self) -> int:
        return 0

    def on_bar(self, ctx: object) -> list:  # type: ignore[override]
        return []


def test_includes_sma_cross() -> None:
    entries = available_strategies()
    names = [e["name"] for e in entries]
    assert "sma_cross" in names


def test_entries_have_name_and_description_keys() -> None:
    entries = available_strategies()
    assert len(entries) >= 1
    for entry in entries:
        assert set(entry.keys()) == {"name", "description"}
        assert isinstance(entry["name"], str) and entry["name"]
        assert isinstance(entry["description"], str)


def test_broken_strategy_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(strategy_pkg, "_BrokenForTest", _Broken, raising=False)
    entries = available_strategies()
    names = [e["name"] for e in entries]
    assert "broken_strategy" not in names
    assert "sma_cross" in names
