"""Tests for ohmystock.journal.repository (read-only query helpers).

Spec: openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from ohmystock.journal.repository import (
    closed_trades_desc,
    monthly_realized_pnl_pct,
    open_positions,
)
from ohmystock.journal.schema import init_schema


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    try:
        yield c
    finally:
        c.close()


def _insert(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    kind: str,
    symbol: str,
    created_at: str,
    payload: dict[str, Any],
) -> None:
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (decision_id, kind, symbol, created_at, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()


def _entry(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    symbol: str,
    created_at: str,
    actual_entry_price: float,
    actual_qty: int,
    sector: str = "半導體",
) -> None:
    _insert(
        conn,
        decision_id=decision_id,
        kind="entry",
        symbol=symbol,
        created_at=created_at,
        payload={
            "actual_entry_price": actual_entry_price,
            "actual_qty": actual_qty,
            "sector": sector,
        },
    )


def _exit(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    symbol: str,
    created_at: str,
    pnl_pct: float,
) -> None:
    _insert(
        conn,
        decision_id=decision_id,
        kind="exit",
        symbol=symbol,
        created_at=created_at,
        payload={"pnl_pct": pnl_pct},
    )


# ---------- open_positions ----------


def test_open_positions_empty_db_returns_empty(conn: sqlite3.Connection) -> None:
    assert open_positions(conn, "2026-04-30") == []


def test_open_positions_one_open(conn: sqlite3.Connection) -> None:
    _entry(
        conn,
        decision_id="dec_001",
        symbol="2330",
        created_at="2026-04-20T10:00:00+08:00",
        actual_entry_price=780.0,
        actual_qty=1,
    )
    positions = open_positions(conn, "2026-04-30")
    assert len(positions) == 1
    p = positions[0]
    assert p.decision_id == "dec_001"
    assert p.symbol == "2330"
    assert p.entry_price == 780.0
    assert p.qty_lots == 1
    assert p.sector == "半導體"


def test_open_positions_excludes_closed(conn: sqlite3.Connection) -> None:
    _entry(
        conn,
        decision_id="dec_002",
        symbol="2454",
        created_at="2026-04-15T10:00:00+08:00",
        actual_entry_price=1200.0,
        actual_qty=1,
    )
    _exit(
        conn,
        decision_id="dec_002",
        symbol="2454",
        created_at="2026-04-22T13:30:00+08:00",
        pnl_pct=5.5,
    )
    assert open_positions(conn, "2026-04-30") == []


def test_open_positions_asof_excludes_future_entries(conn: sqlite3.Connection) -> None:
    _entry(
        conn,
        decision_id="dec_003",
        symbol="3008",
        created_at="2026-05-01T10:00:00+08:00",
        actual_entry_price=900.0,
        actual_qty=1,
    )
    assert open_positions(conn, "2026-04-30") == []


def test_open_positions_treats_future_exit_as_open(conn: sqlite3.Connection) -> None:
    """Exit happens after asof => position is still open as of asof."""
    _entry(
        conn,
        decision_id="dec_004",
        symbol="2412",
        created_at="2026-04-10T10:00:00+08:00",
        actual_entry_price=110.0,
        actual_qty=10,
    )
    _exit(
        conn,
        decision_id="dec_004",
        symbol="2412",
        created_at="2026-05-05T13:30:00+08:00",
        pnl_pct=2.0,
    )
    positions = open_positions(conn, "2026-04-30")
    assert [p.symbol for p in positions] == ["2412"]


def test_open_positions_skips_unfilled_entry(conn: sqlite3.Connection) -> None:
    """Entry without actual_entry_price/actual_qty (pre-fill) is skipped."""
    _insert(
        conn,
        decision_id="dec_005",
        kind="entry",
        symbol="2330",
        created_at="2026-04-29T10:00:00+08:00",
        payload={"sector": "半導體"},
    )
    assert open_positions(conn, "2026-04-30") == []


def test_open_positions_default_sector_when_missing(
    conn: sqlite3.Connection,
) -> None:
    _insert(
        conn,
        decision_id="dec_006",
        kind="entry",
        symbol="9999",
        created_at="2026-04-20T10:00:00+08:00",
        payload={"actual_entry_price": 50.0, "actual_qty": 5},
    )
    positions = open_positions(conn, "2026-04-30")
    assert len(positions) == 1
    assert positions[0].sector == "未分類"


def test_open_positions_multiple_open_sorted_by_entry_ts(
    conn: sqlite3.Connection,
) -> None:
    _entry(
        conn,
        decision_id="dec_a",
        symbol="2330",
        created_at="2026-04-25T10:00:00+08:00",
        actual_entry_price=800.0,
        actual_qty=1,
    )
    _entry(
        conn,
        decision_id="dec_b",
        symbol="2454",
        created_at="2026-04-15T10:00:00+08:00",
        actual_entry_price=1200.0,
        actual_qty=1,
    )
    positions = open_positions(conn, "2026-04-30")
    assert [p.decision_id for p in positions] == ["dec_b", "dec_a"]


# ---------- closed_trades_desc ----------


def test_closed_trades_empty_db(conn: sqlite3.Connection) -> None:
    assert closed_trades_desc(conn, "2026-04-30") == []


def test_closed_trades_one_pair(conn: sqlite3.Connection) -> None:
    _entry(
        conn,
        decision_id="dec_x",
        symbol="2330",
        created_at="2026-04-15T10:00:00+08:00",
        actual_entry_price=780.0,
        actual_qty=1,
    )
    _exit(
        conn,
        decision_id="dec_x",
        symbol="2330",
        created_at="2026-04-25T13:30:00+08:00",
        pnl_pct=6.2,
    )
    trades = closed_trades_desc(conn, "2026-04-30")
    assert len(trades) == 1
    t = trades[0]
    assert t.symbol == "2330"
    assert t.pnl_pct == pytest.approx(6.2)
    assert t.entry_price == 780.0
    assert t.qty_lots == 1


def test_closed_trades_descending_by_exit_ts(conn: sqlite3.Connection) -> None:
    for idx, exit_ts in enumerate(
        ["2026-04-10T13:30:00+08:00", "2026-04-25T13:30:00+08:00", "2026-04-15T13:30:00+08:00"]
    ):
        _entry(
            conn,
            decision_id=f"dec_{idx}",
            symbol="2330",
            created_at="2026-04-01T10:00:00+08:00",
            actual_entry_price=100.0,
            actual_qty=1,
        )
        _exit(
            conn,
            decision_id=f"dec_{idx}",
            symbol="2330",
            created_at=exit_ts,
            pnl_pct=float(idx),
        )
    trades = closed_trades_desc(conn, "2026-04-30")
    assert [t.exit_ts for t in trades] == [
        "2026-04-25T13:30:00+08:00",
        "2026-04-15T13:30:00+08:00",
        "2026-04-10T13:30:00+08:00",
    ]


def test_closed_trades_limit_caps_results(conn: sqlite3.Connection) -> None:
    for idx in range(5):
        _entry(
            conn,
            decision_id=f"dec_{idx}",
            symbol="2330",
            created_at=f"2026-04-{idx + 1:02d}T10:00:00+08:00",
            actual_entry_price=100.0,
            actual_qty=1,
        )
        _exit(
            conn,
            decision_id=f"dec_{idx}",
            symbol="2330",
            created_at=f"2026-04-{idx + 10:02d}T13:30:00+08:00",
            pnl_pct=float(idx),
        )
    trades = closed_trades_desc(conn, "2026-04-30", limit=3)
    assert len(trades) == 3


def test_closed_trades_asof_excludes_future_exits(conn: sqlite3.Connection) -> None:
    _entry(
        conn,
        decision_id="dec_y",
        symbol="2330",
        created_at="2026-04-05T10:00:00+08:00",
        actual_entry_price=780.0,
        actual_qty=1,
    )
    _exit(
        conn,
        decision_id="dec_y",
        symbol="2330",
        created_at="2026-05-15T13:30:00+08:00",
        pnl_pct=4.0,
    )
    assert closed_trades_desc(conn, "2026-04-30") == []


def test_closed_trades_skips_pnl_pct_missing(conn: sqlite3.Connection) -> None:
    _entry(
        conn,
        decision_id="dec_z",
        symbol="2330",
        created_at="2026-04-05T10:00:00+08:00",
        actual_entry_price=780.0,
        actual_qty=1,
    )
    _insert(
        conn,
        decision_id="dec_z",
        kind="exit",
        symbol="2330",
        created_at="2026-04-25T13:30:00+08:00",
        payload={"exit_reason": "manual"},
    )
    assert closed_trades_desc(conn, "2026-04-30") == []


# ---------- monthly_realized_pnl_pct ----------


def test_monthly_pnl_empty_db(conn: sqlite3.Connection) -> None:
    assert monthly_realized_pnl_pct(conn, "2026-04-30", 1_000_000.0) == 0.0


def test_monthly_pnl_one_winning_trade(conn: sqlite3.Connection) -> None:
    _entry(
        conn,
        decision_id="dec_p1",
        symbol="2330",
        created_at="2026-04-10T10:00:00+08:00",
        actual_entry_price=800.0,
        actual_qty=1,
    )
    _exit(
        conn,
        decision_id="dec_p1",
        symbol="2330",
        created_at="2026-04-20T13:30:00+08:00",
        pnl_pct=10.0,
    )
    # notional = 800 * 1 * 1000 = 800_000; pnl_twd = 80_000; vs 1_000_000 = 8.0%
    pct = monthly_realized_pnl_pct(conn, "2026-04-30", 1_000_000.0)
    assert pct == pytest.approx(8.0)


def test_monthly_pnl_excludes_other_months(conn: sqlite3.Connection) -> None:
    _entry(
        conn,
        decision_id="dec_p2",
        symbol="2330",
        created_at="2026-03-10T10:00:00+08:00",
        actual_entry_price=800.0,
        actual_qty=1,
    )
    _exit(
        conn,
        decision_id="dec_p2",
        symbol="2330",
        created_at="2026-03-25T13:30:00+08:00",
        pnl_pct=10.0,
    )
    assert monthly_realized_pnl_pct(conn, "2026-04-30", 1_000_000.0) == 0.0


def test_monthly_pnl_starting_equity_zero_returns_zero(
    conn: sqlite3.Connection,
) -> None:
    _entry(
        conn,
        decision_id="dec_p3",
        symbol="2330",
        created_at="2026-04-10T10:00:00+08:00",
        actual_entry_price=800.0,
        actual_qty=1,
    )
    _exit(
        conn,
        decision_id="dec_p3",
        symbol="2330",
        created_at="2026-04-20T13:30:00+08:00",
        pnl_pct=10.0,
    )
    assert monthly_realized_pnl_pct(conn, "2026-04-30", 0.0) == 0.0


def test_monthly_pnl_excludes_future_exits(conn: sqlite3.Connection) -> None:
    _entry(
        conn,
        decision_id="dec_p4",
        symbol="2330",
        created_at="2026-04-10T10:00:00+08:00",
        actual_entry_price=800.0,
        actual_qty=1,
    )
    _exit(
        conn,
        decision_id="dec_p4",
        symbol="2330",
        created_at="2026-04-25T13:30:00+08:00",
        pnl_pct=10.0,
    )
    assert monthly_realized_pnl_pct(conn, "2026-04-20", 1_000_000.0) == 0.0
