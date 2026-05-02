"""Unit tests for the Exit Engine v0.

Spec: openspec/changes/exit-engine-v0/specs/exit-engine/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date

import pytest

from ohmystock.exit_engine import (
    ExitDecision,
    ExitEngineError,
    ExitResult,
    evaluate_open_positions,
    evaluate_position,
)
from ohmystock.exit_engine.evaluator import _pnl
from ohmystock.journal.schema import init_schema


@dataclass(frozen=True)
class _FakeClock:
    ts: str

    def now_iso(self) -> str:
        return self.ts


class _DictMarketData:
    def __init__(self, data: dict[tuple[str, date], float]) -> None:
        self._data = data

    def get_close(self, symbol: str, asof: date) -> float | None:
        return self._data.get((symbol, asof))


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    return c


def _make_payload(
    *,
    decision_status: str = "confirmed",
    actual_entry_price: float = 832.0,
    stop_loss_price: float = 784.58,
    expected_holding_days: int = 8,
    human_confirmed_at: str = "2026-05-02T10:15:00+08:00",
    drop: list[str] | None = None,
) -> dict:
    payload = {
        "decision_status": decision_status,
        "actual_entry_price": actual_entry_price,
        "actual_qty": 1000,
        "stop_loss_price": stop_loss_price,
        "expected_holding_days": expected_holding_days,
        "human_confirmed_at": human_confirmed_at,
    }
    if drop:
        for k in drop:
            payload.pop(k, None)
    return payload


def _seed_entry(
    conn: sqlite3.Connection,
    *,
    decision_id: str = "dec_X",
    symbol: str = "2330",
    created_at: str = "2026-05-02T10:00:00+08:00",
    payload: dict | None = None,
) -> str:
    payload = payload if payload is not None else _make_payload()
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        (decision_id, symbol, created_at, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
    return decision_id


# ---------------------------------------------------------------------------
# _pnl
# ---------------------------------------------------------------------------


def test_pnl_positive_for_higher_close() -> None:
    assert _pnl(900.0, 832.0) == pytest.approx(8.173, rel=1e-3)


def test_pnl_negative_for_lower_close() -> None:
    assert _pnl(780.0, 832.0) == pytest.approx(-6.250, rel=1e-3)


# ---------------------------------------------------------------------------
# evaluate_position — pure function
# ---------------------------------------------------------------------------


def test_evaluate_position_hit_stop_loss() -> None:
    payload = _make_payload()
    decision = evaluate_position(payload, close_price=780.0, asof_date=date(2026, 5, 5))

    assert decision is not None
    assert decision.exit_tag == "hit_stop_loss"
    assert "stop_loss" in decision.exit_reason
    assert decision.actual_exit_price == 780.0
    assert decision.pnl_pct == pytest.approx(-6.250, rel=1e-3)
    assert decision.hold_days == 3


def test_evaluate_position_hit_t1() -> None:
    payload = _make_payload()
    decision = evaluate_position(payload, close_price=900.0, asof_date=date(2026, 5, 7))

    assert decision is not None
    assert decision.exit_tag == "hit_t1"
    assert "T1" in decision.exit_reason
    assert decision.actual_exit_price == 900.0
    assert decision.pnl_pct == pytest.approx(8.173, rel=1e-3)
    assert decision.hold_days == 5


def test_evaluate_position_time_stop() -> None:
    payload = _make_payload(expected_holding_days=8)  # threshold = 16
    decision = evaluate_position(
        payload, close_price=850.0, asof_date=date(2026, 5, 22)
    )

    assert decision is not None
    assert decision.exit_tag == "time_stop"
    assert "hold_days" in decision.exit_reason
    assert decision.actual_exit_price == 850.0
    assert decision.hold_days == 20


def test_evaluate_position_hold_when_no_trigger() -> None:
    payload = _make_payload(expected_holding_days=8)
    # close in middle of band (not stop, not T1), hold_days=5 (< 16)
    decision = evaluate_position(
        payload, close_price=850.0, asof_date=date(2026, 5, 7)
    )
    assert decision is None


def test_evaluate_position_stop_takes_priority_over_t1() -> None:
    """D5: downside protection wins on hypothetical simultaneous trigger.

    Construct stop_loss=300, entry=100 → t1=106. close=300 ≤ 300 (stop) AND ≥ 106 (t1).
    """
    payload = _make_payload(actual_entry_price=100.0, stop_loss_price=300.0)
    decision = evaluate_position(
        payload, close_price=300.0, asof_date=date(2026, 5, 5)
    )
    assert decision is not None
    assert decision.exit_tag == "hit_stop_loss"


def test_evaluate_position_missing_stop_loss_price_raises() -> None:
    payload = _make_payload(drop=["stop_loss_price"])
    with pytest.raises(ValueError, match="stop_loss_price"):
        evaluate_position(payload, close_price=850.0, asof_date=date(2026, 5, 7))


def test_evaluate_position_missing_actual_entry_price_raises() -> None:
    payload = _make_payload(drop=["actual_entry_price"])
    with pytest.raises(ValueError, match="actual_entry_price"):
        evaluate_position(payload, close_price=850.0, asof_date=date(2026, 5, 7))


def test_evaluate_position_missing_expected_holding_days_raises() -> None:
    payload = _make_payload(drop=["expected_holding_days"])
    with pytest.raises(ValueError, match="expected_holding_days"):
        evaluate_position(payload, close_price=850.0, asof_date=date(2026, 5, 7))


def test_evaluate_position_missing_human_confirmed_at_raises() -> None:
    payload = _make_payload(drop=["human_confirmed_at"])
    with pytest.raises(ValueError, match="human_confirmed_at"):
        evaluate_position(payload, close_price=850.0, asof_date=date(2026, 5, 7))


# ---------------------------------------------------------------------------
# evaluate_open_positions — orchestrator
# ---------------------------------------------------------------------------


def test_evaluate_open_positions_hit_t1_writes_exit_and_flips_entry() -> None:
    conn = _conn()
    decision_id = _seed_entry(conn)
    market = _DictMarketData({("2330", date(2026, 5, 7)): 900.0})
    clock = _FakeClock("2026-05-07T13:30:00+08:00")

    results = evaluate_open_positions(
        conn, market_data=market, asof=date(2026, 5, 7), clock=clock
    )

    assert len(results) == 1
    r = results[0]
    assert isinstance(r, ExitResult)
    assert r.action == "closed"
    assert isinstance(r.decision, ExitDecision)
    assert r.decision.exit_tag == "hit_t1"

    entry_status = conn.execute(
        "SELECT json_extract(payload_json, '$.decision_status') "
        "FROM journal_entries WHERE kind='entry'"
    ).fetchone()[0]
    assert entry_status == "closed"

    exit_row = conn.execute(
        "SELECT decision_id, symbol,"
        " json_extract(payload_json, '$.exit_tag'),"
        " json_extract(payload_json, '$.actual_exit_price'),"
        " json_extract(payload_json, '$.hold_days'),"
        " json_extract(payload_json, '$.exited_at'),"
        " json_extract(payload_json, '$.close_price_evaluated')"
        " FROM journal_entries WHERE kind='exit'"
    ).fetchone()
    assert exit_row == (
        decision_id,
        "2330",
        "hit_t1",
        900.0,
        5,
        "2026-05-07T13:30:00+08:00",
        900.0,
    )


def test_evaluate_open_positions_hold_writes_no_row() -> None:
    conn = _conn()
    _seed_entry(conn)
    market = _DictMarketData({("2330", date(2026, 5, 5)): 850.0})
    clock = _FakeClock("2026-05-05T13:30:00+08:00")

    results = evaluate_open_positions(
        conn, market_data=market, asof=date(2026, 5, 5), clock=clock
    )

    assert len(results) == 1
    assert results[0].action == "held"
    assert results[0].decision is None

    exit_count = conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE kind='exit'"
    ).fetchone()[0]
    assert exit_count == 0

    entry_status = conn.execute(
        "SELECT json_extract(payload_json, '$.decision_status') "
        "FROM journal_entries WHERE kind='entry'"
    ).fetchone()[0]
    assert entry_status == "confirmed"


def test_evaluate_open_positions_batch_one_closed_one_held() -> None:
    conn = _conn()
    _seed_entry(conn, decision_id="dec_A", symbol="2330")
    _seed_entry(conn, decision_id="dec_B", symbol="2317")
    market = _DictMarketData(
        {
            ("2330", date(2026, 5, 7)): 900.0,  # hit_t1
            ("2317", date(2026, 5, 7)): 850.0,  # hold
        }
    )
    clock = _FakeClock("2026-05-07T13:30:00+08:00")

    results = evaluate_open_positions(
        conn, market_data=market, asof=date(2026, 5, 7), clock=clock
    )

    actions = {r.decision_id: r.action for r in results}
    assert actions == {"dec_A": "closed", "dec_B": "held"}

    closed_count = conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE kind='entry' "
        "AND json_extract(payload_json, '$.decision_status')='closed'"
    ).fetchone()[0]
    assert closed_count == 1


def test_evaluate_open_positions_market_data_unavailable_raises_after_processing() -> None:
    conn = _conn()
    _seed_entry(conn, decision_id="dec_A", symbol="2330")
    _seed_entry(conn, decision_id="dec_B", symbol="2317")
    # Only 2330 has data; 2317 returns None
    market = _DictMarketData({("2330", date(2026, 5, 7)): 900.0})
    clock = _FakeClock("2026-05-07T13:30:00+08:00")

    with pytest.raises(ExitEngineError) as exc_info:
        evaluate_open_positions(
            conn, market_data=market, asof=date(2026, 5, 7), clock=clock
        )
    assert exc_info.value.code == "market_data_unavailable"
    assert exc_info.value.failed_symbols == ["2317"]

    # 2330 was processed and committed BEFORE the error was raised.
    closed_count = conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE kind='entry' "
        "AND decision_id='dec_A' "
        "AND json_extract(payload_json, '$.decision_status')='closed'"
    ).fetchone()[0]
    assert closed_count == 1


def test_evaluate_open_positions_skips_already_closed() -> None:
    conn = _conn()
    _seed_entry(conn, payload=_make_payload(decision_status="closed"))
    market = _DictMarketData({("2330", date(2026, 5, 7)): 900.0})
    clock = _FakeClock("2026-05-07T13:30:00+08:00")

    results = evaluate_open_positions(
        conn, market_data=market, asof=date(2026, 5, 7), clock=clock
    )
    assert results == []

    exit_count = conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE kind='exit'"
    ).fetchone()[0]
    assert exit_count == 0


def test_evaluate_open_positions_symbol_filter_narrows_query() -> None:
    conn = _conn()
    _seed_entry(conn, decision_id="dec_A", symbol="2330")
    _seed_entry(conn, decision_id="dec_B", symbol="2317")
    market = _DictMarketData({("2330", date(2026, 5, 7)): 900.0})
    clock = _FakeClock("2026-05-07T13:30:00+08:00")

    results = evaluate_open_positions(
        conn,
        market_data=market,
        asof=date(2026, 5, 7),
        clock=clock,
        symbol_filter="2330",
    )
    assert len(results) == 1
    assert results[0].decision_id == "dec_A"


def test_evaluate_open_positions_idempotent_second_call_is_noop() -> None:
    conn = _conn()
    _seed_entry(conn)
    market = _DictMarketData({("2330", date(2026, 5, 7)): 900.0})
    clock = _FakeClock("2026-05-07T13:30:00+08:00")

    first = evaluate_open_positions(
        conn, market_data=market, asof=date(2026, 5, 7), clock=clock
    )
    second = evaluate_open_positions(
        conn, market_data=market, asof=date(2026, 5, 7), clock=clock
    )

    assert len(first) == 1 and first[0].action == "closed"
    assert second == []  # nothing to do, entry now closed

    exit_count = conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE kind='exit'"
    ).fetchone()[0]
    assert exit_count == 1
