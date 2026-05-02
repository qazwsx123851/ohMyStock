"""Exit engine v0 — daily, full-position evaluator.

Spec: openspec/changes/exit-engine-v0/specs/exit-engine/spec.md
SSOT: docs/workflow-cheatsheet.md §6.6 (normal-market exit policy)

Public API:

- ``evaluate_position(...)``         — pure function over a snapshotted
  payload, returns an ``ExitDecision`` or ``None`` (hold).
- ``evaluate_open_positions(...)``   — orchestrator: query confirmed entries,
  fetch close prices via ``MarketDataLookup``, write ``kind=exit`` rows +
  flip entry ``decision_status="closed"`` per position, atomically.
- ``ExitDecision`` / ``ExitResult``  — frozen dataclasses returned to caller.
- ``MarketDataLookup``                — Protocol the orchestrator depends on.
- ``ExitEngineError``                 — raised for non-position errors
  (currently only ``market_data_unavailable``).

v0 explicitly uses full-position close on T1 (deviates from cheatsheet's
50/25/25 split — see design.md D1). Partial fills + Chandelier are
deferred to a Phase 4 ``position-tranches`` change.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol


ExitTag = Literal["hit_stop_loss", "hit_t1", "time_stop"]


_T1_MULTIPLIER = 1.06       # cheatsheet §6.6 T1 = +6%
_TIME_STOP_FACTOR = 2       # close after expected_holding_days × 2


class ExitEngineError(Exception):
    def __init__(
        self,
        code: Literal["market_data_unavailable"],
        message: str,
        *,
        failed_symbols: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.failed_symbols = list(failed_symbols or [])


@dataclass(frozen=True)
class ExitDecision:
    exit_tag: ExitTag
    exit_reason: str
    actual_exit_price: float
    pnl_pct: float
    hold_days: int


@dataclass(frozen=True)
class ExitResult:
    decision_id: str
    action: Literal["closed", "held"]
    decision: ExitDecision | None


class MarketDataLookup(Protocol):
    def get_close(self, symbol: str, asof: date) -> float | None:
        ...


class _Clock(Protocol):
    def now_iso(self) -> str:
        ...


# ---------------------------------------------------------------------------
# pure function: evaluate_position
# ---------------------------------------------------------------------------


def _pnl(close: float, entry: float) -> float:
    return (close - entry) / entry * 100.0


def evaluate_position(
    entry_payload: dict,
    close_price: float,
    asof_date: date,
) -> ExitDecision | None:
    """Decide whether the position should close on this evaluation day.

    Returns ``None`` to mean "hold". Raises ``ValueError`` if the payload
    lacks any of the four required fields.
    """

    try:
        entry_price = float(entry_payload["actual_entry_price"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"missing or non-numeric actual_entry_price: {exc}") from exc
    try:
        stop_loss_price = float(entry_payload["stop_loss_price"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"missing or non-numeric stop_loss_price: {exc}") from exc
    try:
        expected_holding_days = int(entry_payload["expected_holding_days"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"missing or non-integer expected_holding_days: {exc}"
        ) from exc
    try:
        human_confirmed_at = str(entry_payload["human_confirmed_at"])
        entry_dt = datetime.fromisoformat(human_confirmed_at).date()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"missing or non-ISO-8601 human_confirmed_at: {exc}"
        ) from exc

    hold_days = (asof_date - entry_dt).days
    pnl_pct = _pnl(close_price, entry_price)

    # D5 decision tree — stop_loss → T1 → time_stop
    if close_price <= stop_loss_price:
        return ExitDecision(
            exit_tag="hit_stop_loss",
            exit_reason=f"close {close_price} ≤ stop_loss {stop_loss_price}",
            actual_exit_price=close_price,
            pnl_pct=pnl_pct,
            hold_days=hold_days,
        )

    t1_target = entry_price * _T1_MULTIPLIER
    if close_price >= t1_target:
        return ExitDecision(
            exit_tag="hit_t1",
            exit_reason=f"close {close_price} ≥ T1 {t1_target}",
            actual_exit_price=close_price,
            pnl_pct=pnl_pct,
            hold_days=hold_days,
        )

    time_stop_threshold = expected_holding_days * _TIME_STOP_FACTOR
    if hold_days >= time_stop_threshold:
        return ExitDecision(
            exit_tag="time_stop",
            exit_reason=f"hold_days {hold_days} ≥ {time_stop_threshold}",
            actual_exit_price=close_price,
            pnl_pct=pnl_pct,
            hold_days=hold_days,
        )

    return None


# ---------------------------------------------------------------------------
# orchestrator: evaluate_open_positions
# ---------------------------------------------------------------------------


def evaluate_open_positions(
    conn: sqlite3.Connection,
    *,
    market_data: MarketDataLookup,
    asof: date,
    clock: _Clock,
    symbol_filter: str | None = None,
) -> list[ExitResult]:
    """Evaluate every confirmed entry; close those triggered, leave others.

    Per-position transaction (BEGIN IMMEDIATE → INSERT exit + UPDATE entry
    → COMMIT). If a market_data lookup fails, the symbol is recorded and
    skipped; after processing all rows, raises ``ExitEngineError`` if any
    lookups failed (successful rows are already committed).
    """

    sql = (
        "SELECT decision_id, symbol, payload_json "
        "FROM journal_entries "
        "WHERE kind='entry' "
        "  AND json_extract(payload_json, '$.decision_status')='confirmed' "
    )
    params: tuple = ()
    if symbol_filter is not None:
        sql += "  AND symbol=? "
        params = (symbol_filter,)
    sql += "ORDER BY id ASC"

    rows = conn.execute(sql, params).fetchall()
    results: list[ExitResult] = []
    failed_symbols: list[str] = []
    ts = clock.now_iso()

    for decision_id, symbol, payload_str in rows:
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            continue

        close_price = market_data.get_close(symbol, asof)
        if close_price is None:
            failed_symbols.append(symbol)
            continue

        try:
            decision = evaluate_position(payload, close_price, asof)
        except ValueError:
            continue

        if decision is None:
            results.append(
                ExitResult(decision_id=decision_id, action="held", decision=None)
            )
            continue

        _close_position_atomic(
            conn,
            decision_id=decision_id,
            symbol=symbol,
            decision=decision,
            close_price=close_price,
            ts=ts,
        )
        results.append(
            ExitResult(decision_id=decision_id, action="closed", decision=decision)
        )

    if failed_symbols:
        raise ExitEngineError(
            "market_data_unavailable",
            f"market_data lookup failed for symbols: {failed_symbols!r}",
            failed_symbols=failed_symbols,
        )

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _close_position_atomic(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    symbol: str,
    decision: ExitDecision,
    close_price: float,
    ts: str,
) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        exit_payload = {
            "exit_tag": decision.exit_tag,
            "exit_reason": decision.exit_reason,
            "actual_exit_price": decision.actual_exit_price,
            "pnl_pct": decision.pnl_pct,
            "hold_days": decision.hold_days,
            "exited_at": ts,
            "close_price_evaluated": close_price,
        }
        conn.execute(
            "INSERT INTO journal_entries"
            "(decision_id, kind, symbol, created_at, payload_json) "
            "VALUES (?, 'exit', ?, ?, ?)",
            (
                decision_id,
                symbol,
                ts,
                json.dumps(exit_payload, ensure_ascii=False),
            ),
        )
        _flip_entry_to_closed(conn, decision_id)
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()


def _flip_entry_to_closed(conn: sqlite3.Connection, decision_id: str) -> None:
    row = conn.execute(
        "SELECT id, payload_json FROM journal_entries "
        "WHERE decision_id=? AND kind='entry' "
        "ORDER BY id DESC LIMIT 1",
        (decision_id,),
    ).fetchone()
    if row is None:
        # Should never happen because we just queried it; defensive.
        return
    row_id, payload_str = row
    payload = json.loads(payload_str)
    payload["decision_status"] = "closed"
    conn.execute(
        "UPDATE journal_entries SET payload_json=? WHERE id=?",
        (json.dumps(payload, ensure_ascii=False), row_id),
    )
