"""Unit tests for the Confirm Gate v0.

Spec: openspec/changes/confirm-gate-v0/specs/confirm-gate/spec.md

Covers all four public functions: confirm / reject / sweep_expired / list_pending.
Plus the internal qty calculator (parametrized).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

import pytest

from ohmystock.journal.schema import init_schema
from ohmystock.paper import BrokerError, FakePaperBroker, Fill
from ohmystock.safety import (
    ConfirmGateError,
    PendingEntry,
    confirm,
    list_pending,
    reject,
    sweep_expired,
)
from ohmystock.safety.confirm_gate import _compute_qty


@dataclass(frozen=True)
class _FakeClock:
    ts: str

    def now_iso(self) -> str:
        return self.ts


_DEFAULT_CAPITAL = 1_000_000


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    return c


def _seed_pending(
    conn: sqlite3.Connection,
    *,
    decision_id: str = "dec_2026-05-02T10-00-00_2330",
    symbol: str = "2330",
    created_at: str = "2026-05-02T10:00:00+08:00",
    final_sizing_pct: float = 16.5,
    current_price: float = 832.0,
    atr_14_pct: float | None = 2.85,
    extra: dict | None = None,
) -> str:
    payload = {
        "decision_status": "pending_confirm",
        "final_sizing_pct": final_sizing_pct,
        "current_price": current_price,
        "actual_entry_price": None,
        "actual_qty": None,
        "human_confirmed_by": None,
        "human_confirmed_at": None,
    }
    if atr_14_pct is not None:
        payload["atr_14_pct"] = atr_14_pct
    if extra:
        payload.update(extra)
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        (decision_id, symbol, created_at, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
    return decision_id


# ---------------------------------------------------------------------------
# _compute_qty
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sizing_pct,price,expected",
    [
        (16.5, 832.0, 1000),  # floor((1M*0.165)/832/1000)*1000 = 0 → max 1000
        (16.5, 100.0, 1000),  # floor(165000/100/1000)*1000 = 1*1000
        (25.0, 50.0, 5000),   # floor(250000/50/1000)*1000 = 5*1000
    ],
)
def test_compute_qty_matches_spec_examples(
    sizing_pct: float, price: float, expected: int
) -> None:
    assert _compute_qty(_DEFAULT_CAPITAL, sizing_pct, price) == expected


# ---------------------------------------------------------------------------
# confirm()
# ---------------------------------------------------------------------------


def test_confirm_success_updates_entry_and_returns_result() -> None:
    conn = _conn()
    decision_id = _seed_pending(conn)
    clock = _FakeClock("2026-05-02T10:15:00+08:00")
    broker = FakePaperBroker(clock=clock)

    result = confirm(
        conn,
        decision_id=decision_id,
        broker=broker,
        default_capital_twd=_DEFAULT_CAPITAL,
        user="mark@local",
        clock=clock,
    )

    assert result.decision_id == decision_id
    assert result.qty == 1000
    assert isinstance(result.fill, Fill)
    assert result.fill.fill_price == 832.0
    assert result.fill.filled_qty == 1000
    assert result.fill.fill_ts == "2026-05-02T10:15:00+08:00"

    row = conn.execute(
        "SELECT json_extract(payload_json, '$.decision_status'),"
        " json_extract(payload_json, '$.actual_entry_price'),"
        " json_extract(payload_json, '$.actual_qty'),"
        " json_extract(payload_json, '$.human_confirmed_by'),"
        " json_extract(payload_json, '$.human_confirmed_at')"
        " FROM journal_entries WHERE kind='entry'"
    ).fetchone()
    assert row == (
        "confirmed",
        832.0,
        1000,
        "mark@local",
        "2026-05-02T10:15:00+08:00",
    )


def test_confirm_success_backfills_atr_at_entry_and_stop_loss() -> None:
    """Per cheatsheet §6.6 normal-market: stop = max(entry*0.94, entry-2*ATR)."""
    conn = _conn()
    decision_id = _seed_pending(conn, atr_14_pct=2.85)
    clock = _FakeClock("2026-05-02T10:15:00+08:00")
    broker = FakePaperBroker(clock=clock)

    confirm(
        conn,
        decision_id=decision_id,
        broker=broker,
        default_capital_twd=_DEFAULT_CAPITAL,
        user="mark@local",
        clock=clock,
    )

    atr, stop = conn.execute(
        "SELECT json_extract(payload_json, '$.atr_at_entry'),"
        " json_extract(payload_json, '$.stop_loss_price')"
        " FROM journal_entries WHERE kind='entry'"
    ).fetchone()
    # atr = 832 * 2.85 / 100 = 23.712
    # stop = max(832 * 0.94, 832 - 2 * 23.712) = max(782.08, 784.576) = 784.576
    assert atr == pytest.approx(23.712, rel=1e-4)
    assert stop == pytest.approx(784.576, rel=1e-4)


def test_confirm_payload_invalid_when_missing_atr_14_pct() -> None:
    conn = _conn()
    # Seed without atr_14_pct (atr_14_pct=None tells _seed_pending to omit it).
    decision_id = _seed_pending(conn, atr_14_pct=None)
    clock = _FakeClock("2026-05-02T10:15:00+08:00")

    with pytest.raises(ConfirmGateError) as exc_info:
        confirm(
            conn,
            decision_id=decision_id,
            broker=FakePaperBroker(clock=clock),
            default_capital_twd=_DEFAULT_CAPITAL,
            user="mark",
            clock=clock,
        )
    assert exc_info.value.code == "payload_invalid"
    assert "atr_14_pct" in str(exc_info.value)

    status = conn.execute(
        "SELECT json_extract(payload_json, '$.decision_status') FROM journal_entries"
    ).fetchone()[0]
    assert status == "pending_confirm"  # rollback succeeded


def test_confirm_not_found_raises() -> None:
    conn = _conn()
    clock = _FakeClock("2026-05-02T10:15:00+08:00")
    broker = FakePaperBroker(clock=clock)

    with pytest.raises(ConfirmGateError) as exc_info:
        confirm(
            conn,
            decision_id="dec_does_not_exist",
            broker=broker,
            default_capital_twd=_DEFAULT_CAPITAL,
            user="mark",
            clock=clock,
        )
    assert exc_info.value.code == "not_found"

    count = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
    assert count == 0


def test_confirm_not_pending_raises_when_already_confirmed() -> None:
    conn = _conn()
    decision_id = _seed_pending(conn)
    clock = _FakeClock("2026-05-02T10:15:00+08:00")
    broker = FakePaperBroker(clock=clock)

    confirm(
        conn,
        decision_id=decision_id,
        broker=broker,
        default_capital_twd=_DEFAULT_CAPITAL,
        user="mark",
        clock=clock,
    )

    with pytest.raises(ConfirmGateError) as exc_info:
        confirm(
            conn,
            decision_id=decision_id,
            broker=broker,
            default_capital_twd=_DEFAULT_CAPITAL,
            user="mark",
            clock=clock,
        )
    assert exc_info.value.code == "not_pending"
    assert "confirmed" in str(exc_info.value)


def test_confirm_broker_failure_rolls_back_payload() -> None:
    conn = _conn()
    decision_id = _seed_pending(conn)
    clock = _FakeClock("2026-05-02T10:15:00+08:00")
    broker = FakePaperBroker(clock=clock, raise_on_submit=True)

    with pytest.raises(ConfirmGateError) as exc_info:
        confirm(
            conn,
            decision_id=decision_id,
            broker=broker,
            default_capital_twd=_DEFAULT_CAPITAL,
            user="mark",
            clock=clock,
        )
    assert exc_info.value.code == "broker_failed"
    assert isinstance(exc_info.value.cause, BrokerError)

    status = conn.execute(
        "SELECT json_extract(payload_json, '$.decision_status') FROM journal_entries"
    ).fetchone()[0]
    assert status == "pending_confirm"  # rollback succeeded


def test_confirm_payload_missing_current_price_raises_payload_invalid() -> None:
    conn = _conn()
    payload = {"decision_status": "pending_confirm", "final_sizing_pct": 16.5}
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        ("dec_X", "2330", "2026-05-02T10:00:00+08:00", json.dumps(payload)),
    )
    conn.commit()
    clock = _FakeClock("2026-05-02T10:15:00+08:00")

    with pytest.raises(ConfirmGateError) as exc_info:
        confirm(
            conn,
            decision_id="dec_X",
            broker=FakePaperBroker(clock=clock),
            default_capital_twd=_DEFAULT_CAPITAL,
            user="mark",
            clock=clock,
        )
    assert exc_info.value.code == "payload_invalid"


# ---------------------------------------------------------------------------
# reject()
# ---------------------------------------------------------------------------


def test_reject_success_inserts_kind_reject_and_flips_status() -> None:
    conn = _conn()
    decision_id = _seed_pending(conn)
    clock = _FakeClock("2026-05-02T10:20:00+08:00")

    result = reject(
        conn,
        decision_id=decision_id,
        reason="盤勢不對",
        user="mark@local",
        clock=clock,
    )
    assert result.decision_id == decision_id
    assert result.reject_row_id > 0

    reject_count = conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE decision_id=? AND kind='reject'",
        (decision_id,),
    ).fetchone()[0]
    assert reject_count == 1

    reject_payload = conn.execute(
        "SELECT json_extract(payload_json, '$.reject_layer'),"
        " json_extract(payload_json, '$.reject_reason'),"
        " json_extract(payload_json, '$.rejected_by'),"
        " json_extract(payload_json, '$.rejected_at'),"
        " json_extract(payload_json, '$.decision_status')"
        " FROM journal_entries WHERE kind='reject'"
    ).fetchone()
    assert reject_payload == (
        "human",
        "盤勢不對",
        "mark@local",
        "2026-05-02T10:20:00+08:00",
        "rejected",
    )

    entry_status = conn.execute(
        "SELECT json_extract(payload_json, '$.decision_status') FROM journal_entries "
        "WHERE kind='entry'"
    ).fetchone()[0]
    assert entry_status == "rejected"


def test_reject_not_pending_raises_when_already_confirmed() -> None:
    conn = _conn()
    decision_id = _seed_pending(conn)
    clock = _FakeClock("2026-05-02T10:15:00+08:00")
    broker = FakePaperBroker(clock=clock)
    confirm(
        conn,
        decision_id=decision_id,
        broker=broker,
        default_capital_twd=_DEFAULT_CAPITAL,
        user="mark",
        clock=clock,
    )

    before = conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE kind='reject'"
    ).fetchone()[0]

    with pytest.raises(ConfirmGateError) as exc_info:
        reject(
            conn,
            decision_id=decision_id,
            reason="too late",
            user="mark",
            clock=clock,
        )
    assert exc_info.value.code == "not_pending"

    after = conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE kind='reject'"
    ).fetchone()[0]
    assert after == before  # rollback succeeded, no reject row added


def test_reject_empty_reason_raises_value_error() -> None:
    conn = _conn()
    decision_id = _seed_pending(conn)
    with pytest.raises(ValueError, match="reason"):
        reject(
            conn,
            decision_id=decision_id,
            reason="",
            user="mark",
            clock=_FakeClock("2026-05-02T10:20:00+08:00"),
        )


# ---------------------------------------------------------------------------
# sweep_expired()
# ---------------------------------------------------------------------------


def test_sweep_expired_marks_old_entry() -> None:
    conn = _conn()
    decision_id = _seed_pending(
        conn, created_at="2026-05-02T10:00:00+08:00"
    )
    clock = _FakeClock("2026-05-02T10:35:00+08:00")

    swept = sweep_expired(conn, timeout_minutes=30, clock=clock)
    assert swept == [decision_id]

    entry_status = conn.execute(
        "SELECT json_extract(payload_json, '$.decision_status') FROM journal_entries "
        "WHERE kind='entry'"
    ).fetchone()[0]
    assert entry_status == "expired"

    expire_payload = conn.execute(
        "SELECT json_extract(payload_json, '$.decision_status'),"
        " json_extract(payload_json, '$.expire_reason'),"
        " json_extract(payload_json, '$.expired_at')"
        " FROM journal_entries WHERE kind='expire'"
    ).fetchone()
    assert expire_payload == (
        "expired",
        "confirm timeout after 30 minutes",
        "2026-05-02T10:35:00+08:00",
    )


def test_sweep_expired_skips_recent_entry() -> None:
    conn = _conn()
    _seed_pending(conn, created_at="2026-05-02T10:00:00+08:00")
    clock = _FakeClock("2026-05-02T10:25:00+08:00")  # only 25 min old

    swept = sweep_expired(conn, timeout_minutes=30, clock=clock)
    assert swept == []

    status = conn.execute(
        "SELECT json_extract(payload_json, '$.decision_status') FROM journal_entries "
        "WHERE kind='entry'"
    ).fetchone()[0]
    assert status == "pending_confirm"

    expire_count = conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE kind='expire'"
    ).fetchone()[0]
    assert expire_count == 0


def test_sweep_expired_handles_batch_atomically() -> None:
    conn = _conn()
    for i in range(3):
        _seed_pending(
            conn,
            decision_id=f"dec_batch_{i}",
            symbol=f"233{i}",
            created_at="2026-05-02T10:00:00+08:00",
        )
    clock = _FakeClock("2026-05-02T10:35:00+08:00")

    swept = sweep_expired(conn, timeout_minutes=30, clock=clock)
    assert len(swept) == 3
    assert set(swept) == {f"dec_batch_{i}" for i in range(3)}

    expired_entries = conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE kind='entry' "
        "AND json_extract(payload_json, '$.decision_status')='expired'"
    ).fetchone()[0]
    assert expired_entries == 3

    expire_rows = conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE kind='expire'"
    ).fetchone()[0]
    assert expire_rows == 3


def test_sweep_expired_idempotent_second_call_is_noop() -> None:
    conn = _conn()
    _seed_pending(conn, created_at="2026-05-02T10:00:00+08:00")
    clock = _FakeClock("2026-05-02T10:35:00+08:00")

    first = sweep_expired(conn, timeout_minutes=30, clock=clock)
    second = sweep_expired(conn, timeout_minutes=30, clock=clock)

    assert len(first) == 1
    assert second == []
    expire_count = conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE kind='expire'"
    ).fetchone()[0]
    assert expire_count == 1


@pytest.mark.parametrize("bad_value", [0, -5])
def test_sweep_expired_rejects_non_positive_timeout(bad_value: int) -> None:
    conn = _conn()
    with pytest.raises(ValueError, match="timeout_minutes"):
        sweep_expired(
            conn,
            timeout_minutes=bad_value,
            clock=_FakeClock("2026-05-02T10:35:00+08:00"),
        )


# ---------------------------------------------------------------------------
# list_pending()
# ---------------------------------------------------------------------------


def test_list_pending_returns_oldest_first_with_ttl() -> None:
    conn = _conn()
    _seed_pending(
        conn,
        decision_id="dec_old",
        symbol="2330",
        created_at="2026-05-02T10:00:00+08:00",
    )
    _seed_pending(
        conn,
        decision_id="dec_new",
        symbol="2317",
        created_at="2026-05-02T10:10:00+08:00",
    )

    clock = _FakeClock("2026-05-02T10:15:00+08:00")
    rows = list_pending(conn, clock=clock, timeout_minutes=30)

    assert [r.decision_id for r in rows] == ["dec_old", "dec_new"]
    old, new = rows
    assert isinstance(old, PendingEntry)
    assert old.symbol == "2330"
    assert old.age_seconds == 900  # 15 min
    assert old.ttl_seconds == 30 * 60 - 900  # 900
    assert old.current_price == 832.0
    assert old.final_sizing_pct == 16.5
    assert new.age_seconds == 300  # 5 min


def test_list_pending_empty_when_no_pending_rows() -> None:
    conn = _conn()
    decision_id = _seed_pending(conn)
    clock = _FakeClock("2026-05-02T10:15:00+08:00")
    broker = FakePaperBroker(clock=clock)
    confirm(
        conn,
        decision_id=decision_id,
        broker=broker,
        default_capital_twd=_DEFAULT_CAPITAL,
        user="mark",
        clock=clock,
    )

    rows = list_pending(conn, clock=clock, timeout_minutes=30)
    assert rows == []


def test_list_pending_excludes_rejected_and_expired() -> None:
    conn = _conn()
    rejected_id = _seed_pending(conn, decision_id="dec_r")
    reject(
        conn,
        decision_id=rejected_id,
        reason="bad",
        user="mark",
        clock=_FakeClock("2026-05-02T10:01:00+08:00"),
    )

    _seed_pending(
        conn,
        decision_id="dec_e",
        symbol="1101",
        created_at="2026-05-02T09:00:00+08:00",
    )
    sweep_expired(
        conn,
        timeout_minutes=30,
        clock=_FakeClock("2026-05-02T10:00:00+08:00"),
    )

    rows = list_pending(
        conn,
        clock=_FakeClock("2026-05-02T10:30:00+08:00"),
        timeout_minutes=30,
    )
    assert rows == []
