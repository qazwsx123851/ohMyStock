"""Tests for ohmystock.screener.filters.

Spec: openspec/changes/screener-tw-universe/specs/screener-tw-universe/spec.md
"""

from __future__ import annotations

import sqlite3
from typing import Any
from unittest.mock import MagicMock

import pytest

from ohmystock.data.cache import init_market_data_schema, insert_bars
from ohmystock.data.sources.base import BarRow
from ohmystock.screener.filters import apply_negative_filter, apply_volume_filter


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    init_market_data_schema(c)
    try:
        yield c
    finally:
        c.close()


def _u(symbol: str, **flags: int) -> dict[str, Any]:
    base = {
        "symbol": symbol,
        "market": "TWSE",
        "name": "X",
        "industry": "",
        "is_warning": 0,
        "is_disposal": 0,
        "is_fully_paid": 0,
        "is_ky": 0,
    }
    base.update({k: int(v) for k, v in flags.items()})
    return base


def _bar(date: str, amount: int) -> BarRow:
    return BarRow(ts=date, o=1.0, h=1.0, l=1.0, c=1.0, v=1, amount=amount)


def _seed_bars(conn: sqlite3.Connection, symbol: str, amounts_by_date: list[tuple[str, int]]) -> None:
    bars = [_bar(d, amt) for d, amt in amounts_by_date]
    insert_bars(conn, symbol, bars, "finmind", "t")


# ---------- negative filter ----------


def test_negative_filter_drops_ky() -> None:
    rows = [_u("2330", is_ky=0), _u("9105KY", is_ky=1)]
    out = apply_negative_filter(rows, ["KY"])
    assert [r["symbol"] for r in out] == ["2330"]


def test_negative_filter_unknown_flag_raises() -> None:
    with pytest.raises(ValueError, match="unknown exclude flag"):
        apply_negative_filter([_u("2330")], ["foo"])


def test_negative_filter_empty_exclude_keeps_all() -> None:
    rows = [_u("2330"), _u("9105KY", is_ky=1)]
    out = apply_negative_filter(rows, [])
    assert [r["symbol"] for r in out] == ["2330", "9105KY"]


def test_negative_filter_warning_flag_no_op_when_zero() -> None:
    rows = [_u("2330", is_warning=0)]
    out = apply_negative_filter(rows, ["warning"])
    assert [r["symbol"] for r in out] == ["2330"]


# ---------- volume filter ----------


def test_volume_filter_above_threshold_kept(conn) -> None:
    # 5 bars, avg = 1.2e8 >= 1e8
    _seed_bars(
        conn,
        "2330",
        [
            ("2026-04-24", 100_000_000),
            ("2026-04-25", 100_000_000),
            ("2026-04-28", 100_000_000),
            ("2026-04-29", 100_000_000),
            ("2026-04-30", 200_000_000),
        ],
    )
    out = apply_volume_filter([_u("2330")], conn, 100_000_000, "2026-04-30")
    assert [r["symbol"] for r in out] == ["2330"]


def test_volume_filter_below_threshold_dropped(conn) -> None:
    # 5 bars, avg = 8e7 < 1e8
    _seed_bars(
        conn,
        "2330",
        [
            ("2026-04-24", 80_000_000),
            ("2026-04-25", 80_000_000),
            ("2026-04-28", 80_000_000),
            ("2026-04-29", 80_000_000),
            ("2026-04-30", 80_000_000),
        ],
    )
    out = apply_volume_filter([_u("2330")], conn, 100_000_000, "2026-04-30")
    assert out == []


def test_volume_filter_skip_missing_default(conn) -> None:
    _seed_bars(
        conn,
        "2330",
        [("2026-04-29", 200_000_000), ("2026-04-30", 200_000_000)],
    )
    out = apply_volume_filter([_u("2330")], conn, 100_000_000, "2026-04-30")
    assert out == []


def test_volume_filter_fail_fast_raises(conn) -> None:
    _seed_bars(
        conn,
        "2330",
        [("2026-04-29", 200_000_000), ("2026-04-30", 200_000_000)],
    )
    with pytest.raises(ValueError, match="data unavailable"):
        apply_volume_filter(
            [_u("2330")], conn, 100_000_000, "2026-04-30", error_policy="fail_fast"
        )


def test_volume_filter_does_not_call_get_kline(conn, monkeypatch) -> None:
    """apply_volume_filter MUST NOT trigger any kline fetch path."""
    spy = MagicMock()
    import ohmystock.data.market_data as md

    monkeypatch.setattr(md, "get_kline", spy)

    _seed_bars(
        conn,
        "2330",
        [
            ("2026-04-24", 100_000_000),
            ("2026-04-25", 100_000_000),
            ("2026-04-28", 100_000_000),
            ("2026-04-29", 100_000_000),
            ("2026-04-30", 100_000_000),
        ],
    )
    apply_volume_filter([_u("2330")], conn, 50_000_000, "2026-04-30")
    apply_volume_filter([_u("9999")], conn, 50_000_000, "2026-04-30")

    spy.assert_not_called()


def test_volume_filter_unknown_error_policy_raises(conn) -> None:
    with pytest.raises(ValueError, match="unknown error_policy"):
        apply_volume_filter([_u("2330")], conn, 100, "2026-04-30", error_policy="weird")
