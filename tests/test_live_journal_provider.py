"""Tests for compute_recent_winrate / compute_consecutive_loss + provider.

Spec: openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from ohmystock.journal.schema import init_schema
from ohmystock.swarm._live_journal import (
    compute_consecutive_loss,
    compute_recent_winrate,
)


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
        (
            decision_id,
            kind,
            symbol,
            created_at,
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    conn.commit()


def _seed_closed(
    conn: sqlite3.Connection,
    decision_id: str,
    *,
    pnl_pct: float,
    entry_at: str,
    exit_at: str,
) -> None:
    _insert(
        conn,
        decision_id=decision_id,
        kind="entry",
        symbol="2330",
        created_at=entry_at,
        payload={
            "actual_entry_price": 100.0,
            "actual_qty": 1,
            "sector": "半導體",
        },
    )
    _insert(
        conn,
        decision_id=decision_id,
        kind="exit",
        symbol="2330",
        created_at=exit_at,
        payload={"pnl_pct": pnl_pct},
    )


# ---------- compute_recent_winrate ----------


def test_winrate_zero_when_empty(conn: sqlite3.Connection) -> None:
    assert compute_recent_winrate(conn, "2026-04-30", 20) == 0.0


def test_winrate_12_of_20(conn: sqlite3.Connection) -> None:
    pnls = (
        [-1.0] * 5  # oldest 5: losses (will be truncated by limit=20)
        + [1.0] * 12  # next 12: wins
        + [-1.0] * 8  # most recent 8: losses
    )
    for idx, pnl in enumerate(pnls):
        day = idx + 1
        _seed_closed(
            conn,
            decision_id=f"dec_{idx}",
            pnl_pct=pnl,
            entry_at=f"2026-03-{day:02d}T10:00:00+08:00",
            exit_at=f"2026-04-{day:02d}T13:30:00+08:00",
        )
    rate = compute_recent_winrate(conn, "2026-04-30", 20)
    assert rate == pytest.approx(12 / 20)


def test_winrate_fewer_than_n_uses_actual_count(
    conn: sqlite3.Connection,
) -> None:
    pnls = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0]
    for idx, pnl in enumerate(pnls):
        day = idx + 1
        _seed_closed(
            conn,
            decision_id=f"dec_{idx}",
            pnl_pct=pnl,
            entry_at=f"2026-03-{day:02d}T10:00:00+08:00",
            exit_at=f"2026-04-{day:02d}T13:30:00+08:00",
        )
    assert compute_recent_winrate(conn, "2026-04-30", 20) == pytest.approx(
        4 / 7
    )


def test_winrate_n_zero_returns_zero(conn: sqlite3.Connection) -> None:
    _seed_closed(
        conn,
        decision_id="dec_a",
        pnl_pct=10.0,
        entry_at="2026-04-10T10:00:00+08:00",
        exit_at="2026-04-20T13:30:00+08:00",
    )
    assert compute_recent_winrate(conn, "2026-04-30", 0) == 0.0


def test_winrate_asof_excludes_future_exits(conn: sqlite3.Connection) -> None:
    _seed_closed(
        conn,
        decision_id="dec_future",
        pnl_pct=10.0,
        entry_at="2026-04-10T10:00:00+08:00",
        exit_at="2026-05-15T13:30:00+08:00",
    )
    assert compute_recent_winrate(conn, "2026-04-30", 20) == 0.0


def test_winrate_zero_pnl_counted_as_loss(conn: sqlite3.Connection) -> None:
    # pnl_pct=0 is NOT profitable (must be > 0 per spec).
    _seed_closed(
        conn,
        decision_id="dec_z",
        pnl_pct=0.0,
        entry_at="2026-04-10T10:00:00+08:00",
        exit_at="2026-04-20T13:30:00+08:00",
    )
    assert compute_recent_winrate(conn, "2026-04-30", 20) == 0.0


# ---------- compute_consecutive_loss ----------


def test_consecutive_loss_zero_when_empty(conn: sqlite3.Connection) -> None:
    assert compute_consecutive_loss(conn, "2026-04-30") == 0


def test_consecutive_loss_three_then_a_win_returns_three(
    conn: sqlite3.Connection,
) -> None:
    pnls_oldest_to_newest = [+300.0, -100.0, -200.0, -50.0]
    for idx, pnl in enumerate(pnls_oldest_to_newest):
        day = idx + 1
        _seed_closed(
            conn,
            decision_id=f"dec_{idx}",
            pnl_pct=pnl,
            entry_at=f"2026-03-{day:02d}T10:00:00+08:00",
            exit_at=f"2026-04-{day:02d}T13:30:00+08:00",
        )
    # Most recent → oldest desc: -50, -200, -100, +300 → streak = 3
    assert compute_consecutive_loss(conn, "2026-04-30") == 3


def test_consecutive_loss_all_losing_returns_at_least_five(
    conn: sqlite3.Connection,
) -> None:
    for idx in range(5):
        day = idx + 1
        _seed_closed(
            conn,
            decision_id=f"dec_{idx}",
            pnl_pct=-1.0,
            entry_at=f"2026-03-{day:02d}T10:00:00+08:00",
            exit_at=f"2026-04-{day:02d}T13:30:00+08:00",
        )
    assert compute_consecutive_loss(conn, "2026-04-30") >= 5


def test_consecutive_loss_zero_pnl_counts_as_loss(
    conn: sqlite3.Connection,
) -> None:
    _seed_closed(
        conn,
        decision_id="dec_old",
        pnl_pct=5.0,
        entry_at="2026-04-01T10:00:00+08:00",
        exit_at="2026-04-15T13:30:00+08:00",
    )
    _seed_closed(
        conn,
        decision_id="dec_new",
        pnl_pct=0.0,
        entry_at="2026-04-20T10:00:00+08:00",
        exit_at="2026-04-25T13:30:00+08:00",
    )
    assert compute_consecutive_loss(conn, "2026-04-30") == 1


# ---------- LiveJournalStatsProvider integration ----------


def test_provider_delegates_against_seeded_db(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from ohmystock.swarm import LiveJournalStatsProvider

    db_path = tmp_path / "journal.db"
    monkeypatch.setenv("OHMYSTOCK_DB_PATH", str(db_path))
    c = sqlite3.connect(str(db_path))
    init_schema(c)
    c.close()

    provider = LiveJournalStatsProvider(asof="2026-04-30")
    assert provider.recent_winrate(20) == 0.0
    assert provider.consecutive_loss() == 0
