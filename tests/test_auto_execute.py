"""End-to-end tests for the Phase 3.5 auto-execute breakers.

Spec: openspec/changes/auto-execute-toggle-and-breakers/specs/auto-execute/spec.md

Covers all 8 outcomes (pass / sizing_clamped_then_pass / flag_off /
low_confidence / daily_limit / notional_limit / loss_lockout / live_broker)
plus the 4 contract-violation error paths (not_found / not_pending /
payload_invalid / confirm_failed).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

import pytest

from ohmystock.config import Settings
from ohmystock.journal.schema import init_schema
from ohmystock.paper import FakePaperBroker
from ohmystock.safety import (
    AutoExecuteError,
    AutoExecuteResult,
    try_auto_execute,
)


@dataclass(frozen=True)
class _FakeClock:
    ts: str

    def now_iso(self) -> str:
        return self.ts


_DEFAULT_DECISION_ID = "dec_2026-05-02T10-00-00_2330"
_DEFAULT_SYMBOL = "2330"
_DEFAULT_CREATED_AT = "2026-05-02T10:00:00+08:00"
_DEFAULT_NOW = "2026-05-02T10:15:00+08:00"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    return c


def _settings(**overrides: Any) -> Settings:
    """Build an isolated Settings with auto-execute defaults overridable."""
    base: dict[str, Any] = {
        "ohmystock_broker": "shioaji-sim",
        "ohmystock_auto_execute": True,  # tests default to flag-on
        "ohmystock_auto_execute_account_equity_twd": 1_000_000,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _seed_pending(
    conn: sqlite3.Connection,
    *,
    decision_id: str = _DEFAULT_DECISION_ID,
    symbol: str = _DEFAULT_SYMBOL,
    created_at: str = _DEFAULT_CREATED_AT,
    llm_confidence: float = 0.85,
    final_sizing_pct: float = 20.0,
    current_price: float = 100.0,
    atr_14_pct: float = 2.85,
    stage: int = 2,
    extra: dict | None = None,
    omit: tuple[str, ...] = (),
) -> str:
    """Default `current_price=100.0` keeps notional (200k) under the 25% cap
    (250k) so pass-path tests reach confirm(). Tests that need to trip
    `notional_limit` set `current_price` explicitly.
    """
    payload: dict[str, Any] = {
        "decision_status": "pending_confirm",
        "llm_confidence": llm_confidence,
        "final_sizing_pct": final_sizing_pct,
        "current_price": current_price,
        "atr_14_pct": atr_14_pct,
        "stage": stage,
        "auto_executed": False,
    }
    if extra:
        payload.update(extra)
    for key in omit:
        payload.pop(key, None)
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        (decision_id, symbol, created_at, json.dumps(payload)),
    )
    conn.commit()
    return decision_id


def _seed_auto_executed_entry(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    symbol: str = "2330",
    confirmed_at: str,
) -> None:
    """Seed an already-confirmed entry that came from the auto path."""
    payload = {
        "decision_status": "confirmed",
        "auto_executed": True,
        "human_confirmed_by": "auto",
        "human_confirmed_at": confirmed_at,
    }
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        (decision_id, symbol, confirmed_at, json.dumps(payload)),
    )
    conn.commit()


def _seed_auto_exit(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    symbol: str,
    closed_at: str,
    realized_pnl_pct: float,
) -> None:
    payload = {
        "decision_status": "closed",
        "source": "auto",
        "realized_pnl_pct": realized_pnl_pct,
        "closed_at": closed_at,
    }
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'exit', ?, ?, ?)",
        (decision_id, symbol, closed_at, json.dumps(payload)),
    )
    conn.commit()


def _audit_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE kind='auto_execute_audit'"
    ).fetchone()[0]


def _audit_rows(
    conn: sqlite3.Connection, decision_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT payload_json FROM journal_entries "
        "WHERE kind='auto_execute_audit' AND decision_id=? ORDER BY id",
        (decision_id,),
    ).fetchall()
    return [json.loads(r[0]) for r in rows]


def _entry_status(conn: sqlite3.Connection, decision_id: str) -> str:
    return conn.execute(
        "SELECT json_extract(payload_json, '$.decision_status') "
        "FROM journal_entries WHERE kind='entry' AND decision_id=?",
        (decision_id,),
    ).fetchone()[0]


# ---------------------------------------------------------------------------
# Contract-violation error paths (no audit row written)
# ---------------------------------------------------------------------------


def test_not_found_raises_and_writes_no_audit() -> None:
    conn = _conn()
    clock = _FakeClock(_DEFAULT_NOW)
    with pytest.raises(AutoExecuteError) as exc_info:
        try_auto_execute(
            conn,
            decision_id="dec_does_not_exist",
            broker=FakePaperBroker(clock=clock),
            settings=_settings(),
            clock=clock,
        )
    assert exc_info.value.code == "not_found"
    assert _audit_count(conn) == 0


def test_not_pending_raises_and_writes_no_audit() -> None:
    conn = _conn()
    decision_id = _seed_pending(conn, extra={"decision_status": "confirmed"})
    clock = _FakeClock(_DEFAULT_NOW)
    with pytest.raises(AutoExecuteError) as exc_info:
        try_auto_execute(
            conn,
            decision_id=decision_id,
            broker=FakePaperBroker(clock=clock),
            settings=_settings(),
            clock=clock,
        )
    assert exc_info.value.code == "not_pending"
    assert _audit_count(conn) == 0


def test_payload_invalid_missing_stage_raises_and_writes_no_audit() -> None:
    conn = _conn()
    decision_id = _seed_pending(conn, omit=("stage",))
    clock = _FakeClock(_DEFAULT_NOW)
    with pytest.raises(AutoExecuteError) as exc_info:
        try_auto_execute(
            conn,
            decision_id=decision_id,
            broker=FakePaperBroker(clock=clock),
            settings=_settings(),
            clock=clock,
        )
    assert exc_info.value.code == "payload_invalid"
    assert "stage" in str(exc_info.value)
    assert _audit_count(conn) == 0


def test_confirm_failed_raises_and_writes_no_audit() -> None:
    """Use price=100 to keep notional within the 25% cap so we reach confirm()."""
    conn = _conn()
    decision_id = _seed_pending(conn, current_price=100.0, final_sizing_pct=20.0)
    clock = _FakeClock(_DEFAULT_NOW)
    with pytest.raises(AutoExecuteError) as exc_info:
        try_auto_execute(
            conn,
            decision_id=decision_id,
            broker=FakePaperBroker(clock=clock, raise_on_submit=True),
            settings=_settings(),
            clock=clock,
        )
    assert exc_info.value.code == "confirm_failed"
    assert _audit_count(conn) == 0
    assert _entry_status(conn, decision_id) == "pending_confirm"


# ---------------------------------------------------------------------------
# Breaker fallbacks (one audit row per call, entry stays pending)
# ---------------------------------------------------------------------------


def test_flag_off_writes_audit_and_keeps_pending() -> None:
    conn = _conn()
    decision_id = _seed_pending(conn)
    clock = _FakeClock(_DEFAULT_NOW)

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=FakePaperBroker(clock=clock),
        settings=_settings(ohmystock_auto_execute=False),
        clock=clock,
    )

    assert isinstance(result, AutoExecuteResult)
    assert result.outcome == "flag_off"
    assert result.confirm_result is None
    rows = _audit_rows(conn, decision_id)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "flag_off"
    assert _entry_status(conn, decision_id) == "pending_confirm"


def test_live_broker_writes_audit_when_runtime_set_to_live() -> None:
    """settings validator forbids live+auto in construction; we mutate the
    field at runtime to prove the redundant call-time breaker still fires.
    """
    conn = _conn()
    decision_id = _seed_pending(conn)
    clock = _FakeClock(_DEFAULT_NOW)

    s = _settings()
    object.__setattr__(s, "ohmystock_broker", "shioaji-live")

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=FakePaperBroker(clock=clock),
        settings=s,
        clock=clock,
    )
    assert result.outcome == "live_broker"
    rows = _audit_rows(conn, decision_id)
    assert len(rows) == 1
    assert rows[0]["evidence"] == {"broker_mode": "shioaji-live"}
    assert _entry_status(conn, decision_id) == "pending_confirm"


def test_low_confidence_writes_audit() -> None:
    conn = _conn()
    decision_id = _seed_pending(conn, llm_confidence=0.62)
    clock = _FakeClock(_DEFAULT_NOW)

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=FakePaperBroker(clock=clock),
        settings=_settings(),
        clock=clock,
    )
    assert result.outcome == "low_confidence"
    rows = _audit_rows(conn, decision_id)
    assert rows[0]["evidence"] == {
        "llm_confidence": 0.62,
        "min_confidence": 0.7,
    }
    assert _entry_status(conn, decision_id) == "pending_confirm"


def test_notional_limit_writes_audit() -> None:
    conn = _conn()
    # final_sizing_pct=25, price=832 → qty = floor(250000/832/1000)*1000 = 0,
    # max(1000, 0) = 1000 lots → notional = 1000 * 832 = 832,000.
    # max_notional = 1_000_000 * 0.20 = 200,000 → 832k > 200k → trips.
    decision_id = _seed_pending(
        conn, final_sizing_pct=25.0, current_price=832.0
    )
    clock = _FakeClock(_DEFAULT_NOW)

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=FakePaperBroker(clock=clock),
        settings=_settings(ohmystock_auto_execute_max_notional_pct=0.20),
        clock=clock,
    )
    assert result.outcome == "notional_limit"
    rows = _audit_rows(conn, decision_id)
    assert rows[0]["evidence"]["notional_twd"] == 832_000.0
    assert rows[0]["evidence"]["max_notional_twd"] == 200_000.0
    assert _entry_status(conn, decision_id) == "pending_confirm"


def test_daily_limit_writes_audit_when_quota_reached() -> None:
    conn = _conn()
    # Seed 5 prior auto-executed entries today TPE.
    for i in range(5):
        _seed_auto_executed_entry(
            conn,
            decision_id=f"dec_prior_{i}",
            symbol=f"233{i}",
            confirmed_at=f"2026-05-02T09:0{i}:00+08:00",
        )
    decision_id = _seed_pending(conn, decision_id="dec_new")
    clock = _FakeClock(_DEFAULT_NOW)

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=FakePaperBroker(clock=clock),
        settings=_settings(),
        clock=clock,
    )
    assert result.outcome == "daily_limit"
    rows = _audit_rows(conn, decision_id)
    assert rows[0]["evidence"] == {
        "auto_today_count": 5,
        "daily_limit": 5,
    }
    assert _entry_status(conn, decision_id) == "pending_confirm"


def test_loss_lockout_writes_audit_when_streak_active() -> None:
    conn = _conn()
    for i, pnl in enumerate([-0.06, -0.07, -0.08]):
        _seed_auto_exit(
            conn,
            decision_id=f"dec_loss_{i}",
            symbol=f"100{i}",
            closed_at=(
                "2026-05-02T08:00:00+08:00"
                if i < 2
                else "2026-05-02T09:00:00+08:00"
            ),
            realized_pnl_pct=pnl,
        )
    decision_id = _seed_pending(conn)
    clock = _FakeClock(_DEFAULT_NOW)

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=FakePaperBroker(clock=clock),
        settings=_settings(),
        clock=clock,
    )
    assert result.outcome == "loss_lockout"
    rows = _audit_rows(conn, decision_id)
    assert rows[0]["evidence"]["loss_streak_count"] == 3
    assert rows[0]["evidence"]["lockout_until"] == (
        "2026-05-03T09:00:00+08:00"
    )
    assert _entry_status(conn, decision_id) == "pending_confirm"


def test_loss_lockout_does_not_trigger_when_fewer_than_three_exits() -> None:
    """Only 2 prior auto exits → streak query returns <3 → no lockout."""
    conn = _conn()
    for i, pnl in enumerate([-0.06, -0.07]):
        _seed_auto_exit(
            conn,
            decision_id=f"dec_loss_{i}",
            symbol=f"100{i}",
            closed_at=f"2026-05-02T0{8 + i}:00:00+08:00",
            realized_pnl_pct=pnl,
        )
    decision_id = _seed_pending(conn)
    clock = _FakeClock(_DEFAULT_NOW)

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=FakePaperBroker(clock=clock),
        settings=_settings(),
        clock=clock,
    )
    assert result.outcome == "pass"
    assert _entry_status(conn, decision_id) == "confirmed"


# ---------------------------------------------------------------------------
# Pass paths
# ---------------------------------------------------------------------------


def test_pass_runs_confirm_and_writes_audit() -> None:
    conn = _conn()
    decision_id = _seed_pending(conn)
    clock = _FakeClock(_DEFAULT_NOW)

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=FakePaperBroker(clock=clock),
        settings=_settings(),
        clock=clock,
    )
    assert result.outcome == "pass"
    assert result.confirm_result is not None
    assert result.confirm_result.fill.fill_price == 100.0

    row = conn.execute(
        "SELECT json_extract(payload_json, '$.decision_status'),"
        " json_extract(payload_json, '$.auto_executed'),"
        " json_extract(payload_json, '$.human_confirmed_by'),"
        " json_extract(payload_json, '$.actual_entry_price')"
        " FROM journal_entries WHERE kind='entry' AND decision_id=?",
        (decision_id,),
    ).fetchone()
    assert row == ("confirmed", 1, "auto", 100.0)

    rows = _audit_rows(conn, decision_id)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "pass"
    assert rows[0]["evidence"]["broker_mode"] == "shioaji-sim"
    assert rows[0]["evidence"]["clamped_sizing_pct"] is None


def test_sizing_clamped_then_pass_clamps_and_runs_confirm() -> None:
    """stage=3, sizing=20 (deviation = (20-10)/10 = 1.0 > 0.30) → clamp to 10."""
    conn = _conn()
    decision_id = _seed_pending(
        conn,
        stage=3,
        final_sizing_pct=20.0,
        current_price=100.0,  # keeps notional under 25% cap
    )
    clock = _FakeClock(_DEFAULT_NOW)

    result = try_auto_execute(
        conn,
        decision_id=decision_id,
        broker=FakePaperBroker(clock=clock),
        settings=_settings(),
        clock=clock,
    )
    assert result.outcome == "sizing_clamped_then_pass"
    assert _entry_status(conn, decision_id) == "confirmed"

    row = conn.execute(
        "SELECT json_extract(payload_json, '$.final_sizing_pct')"
        " FROM journal_entries WHERE kind='entry' AND decision_id=?",
        (decision_id,),
    ).fetchone()
    assert row[0] == 10.0  # clamped

    rows = _audit_rows(conn, decision_id)
    ev = rows[0]["evidence"]
    assert ev["raw_sizing_pct"] == 20.0
    assert ev["clamped_sizing_pct"] == 10.0
    assert ev["system_sizing_pct"] == 10.0
