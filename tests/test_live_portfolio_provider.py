"""Tests for reconstruct_portfolio + LivePortfolioSnapshotProvider.

Spec: openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from ohmystock.data.cache import init_market_data_schema, insert_bars
from ohmystock.data.sources.base import BarRow
from ohmystock.journal.schema import init_schema
from ohmystock.screener.cache import init_universe_schema, insert_universe_rows
from ohmystock.swarm import LiveProviderError, PortfolioSnapshot
from ohmystock.swarm._live_portfolio import reconstruct_portfolio


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    init_market_data_schema(c)
    init_universe_schema(c)
    try:
        yield c
    finally:
        c.close()


def _journal_insert(
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
        (
            decision_id,
            kind,
            symbol,
            created_at,
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    conn.commit()


def _seed_bar(
    conn: sqlite3.Connection, symbol: str, ts: str, close: float
) -> None:
    insert_bars(
        conn,
        symbol,
        [
            BarRow(
                ts=ts,
                o=close,
                h=close,
                l=close,
                c=close,
                v=1_000,
                amount=int(close * 1_000),
            )
        ],
        source="test",
        fetched_at="2026-04-30T00:00:00+08:00",
    )


def _seed_universe(
    conn: sqlite3.Connection,
    *,
    asof: str,
    symbol: str,
    industry: str,
) -> None:
    insert_universe_rows(
        conn,
        [
            {
                "asof_date": asof,
                "symbol": symbol,
                "market": "TWSE",
                "name": symbol,
                "industry": industry,
                "is_warning": 0,
                "is_disposal": 0,
                "is_fully_paid": 0,
                "is_ky": 0,
            }
        ],
        source="test",
        fetched_at="2026-04-30T00:00:00+08:00",
    )


# ---------- reconstruct_portfolio ----------


def test_empty_journal_returns_empty_snapshot(conn: sqlite3.Connection) -> None:
    snap = reconstruct_portfolio(
        "2026-04-30", conn=conn, starting_equity=1_000_000.0
    )
    assert snap == PortfolioSnapshot()


def test_one_open_position_full_lifecycle(conn: sqlite3.Connection) -> None:
    _journal_insert(
        conn,
        decision_id="dec_1",
        kind="entry",
        symbol="2330",
        created_at="2026-04-20T10:00:00+08:00",
        payload={
            "actual_entry_price": 780.0,
            "actual_qty": 1,
            "sector": "半導體",
        },
    )
    _seed_bar(conn, "2330", "2026-04-30", 820.0)
    _seed_universe(conn, asof="2026-04-30", symbol="2330", industry="半導體")

    snap = reconstruct_portfolio(
        "2026-04-30", conn=conn, starting_equity=1_000_000.0
    )

    assert len(snap.positions) == 1
    p = snap.positions[0]
    assert p.symbol == "2330"
    assert p.sector == "半導體"
    # 1 lot * 1000 shares * 820 / 1_000_000 * 100 = 82.0
    assert p.exposure_pct == pytest.approx(82.0)
    assert snap.total_exposure_pct == pytest.approx(82.0)


def test_closed_position_excluded_by_decision_id_match(
    conn: sqlite3.Connection,
) -> None:
    _journal_insert(
        conn,
        decision_id="dec_2",
        kind="entry",
        symbol="2454",
        created_at="2026-04-15T10:00:00+08:00",
        payload={
            "actual_entry_price": 1200.0,
            "actual_qty": 1,
            "sector": "半導體",
        },
    )
    _journal_insert(
        conn,
        decision_id="dec_2",
        kind="exit",
        symbol="2454",
        created_at="2026-04-22T13:30:00+08:00",
        payload={"pnl_pct": 5.5},
    )

    snap = reconstruct_portfolio(
        "2026-04-30", conn=conn, starting_equity=1_000_000.0
    )

    assert snap == PortfolioSnapshot()


def test_missing_sector_falls_back_to_unknown(
    conn: sqlite3.Connection,
) -> None:
    _journal_insert(
        conn,
        decision_id="dec_3",
        kind="entry",
        symbol="9999",
        created_at="2026-04-20T10:00:00+08:00",
        payload={"actual_entry_price": 50.0, "actual_qty": 5},
    )
    _seed_bar(conn, "9999", "2026-04-30", 55.0)

    snap = reconstruct_portfolio(
        "2026-04-30", conn=conn, starting_equity=1_000_000.0
    )

    assert len(snap.positions) == 1
    assert snap.positions[0].sector == "未分類"


def test_missing_journal_db_raises_data_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    file_blocker = tmp_path / "blocker"
    file_blocker.write_text("")
    # Settings reads OHMYSTOCK_DB_PATH from env (case-insensitive,
    # extra=ignore). Forcing the path under a regular file makes mkdir fail.
    monkeypatch.setenv(
        "OHMYSTOCK_DB_PATH", str(file_blocker / "journal.db")
    )
    with pytest.raises(LiveProviderError) as exc:
        reconstruct_portfolio("2026-04-30")
    assert exc.value.code == "DATA_UNAVAILABLE"


def test_no_cached_close_falls_back_to_entry_price(
    conn: sqlite3.Connection,
) -> None:
    _journal_insert(
        conn,
        decision_id="dec_4",
        kind="entry",
        symbol="2330",
        created_at="2026-04-20T10:00:00+08:00",
        payload={
            "actual_entry_price": 800.0,
            "actual_qty": 1,
            "sector": "半導體",
        },
    )
    snap = reconstruct_portfolio(
        "2026-04-30", conn=conn, starting_equity=1_000_000.0
    )
    assert len(snap.positions) == 1
    # 1 * 1000 * 800 / 1_000_000 * 100 = 80.0
    assert snap.positions[0].exposure_pct == pytest.approx(80.0)


def test_universe_sector_overrides_payload_sector(
    conn: sqlite3.Connection,
) -> None:
    _journal_insert(
        conn,
        decision_id="dec_5",
        kind="entry",
        symbol="2330",
        created_at="2026-04-20T10:00:00+08:00",
        payload={
            "actual_entry_price": 800.0,
            "actual_qty": 1,
            "sector": "半導體",
        },
    )
    _seed_bar(conn, "2330", "2026-04-30", 820.0)
    _seed_universe(
        conn, asof="2026-04-30", symbol="2330", industry="半導體製造"
    )

    snap = reconstruct_portfolio(
        "2026-04-30", conn=conn, starting_equity=1_000_000.0
    )

    assert snap.positions[0].sector == "半導體製造"


def test_total_exposure_sums_across_positions(
    conn: sqlite3.Connection,
) -> None:
    _journal_insert(
        conn,
        decision_id="dec_a",
        kind="entry",
        symbol="2330",
        created_at="2026-04-20T10:00:00+08:00",
        payload={
            "actual_entry_price": 800.0,
            "actual_qty": 1,
            "sector": "半導體",
        },
    )
    _journal_insert(
        conn,
        decision_id="dec_b",
        kind="entry",
        symbol="2454",
        created_at="2026-04-15T10:00:00+08:00",
        payload={
            "actual_entry_price": 1200.0,
            "actual_qty": 1,
            "sector": "半導體",
        },
    )
    _seed_bar(conn, "2330", "2026-04-30", 800.0)
    _seed_bar(conn, "2454", "2026-04-30", 1200.0)

    snap = reconstruct_portfolio(
        "2026-04-30", conn=conn, starting_equity=1_000_000.0
    )

    # 80.0 + 120.0 = 200.0
    assert snap.total_exposure_pct == pytest.approx(200.0)
    assert {p.symbol for p in snap.positions} == {"2330", "2454"}
