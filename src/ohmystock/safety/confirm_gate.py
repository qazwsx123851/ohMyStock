"""Confirm Gate v0 — human-mode lifecycle for pending_confirm entries.

Spec: openspec/changes/confirm-gate-v0/specs/confirm-gate/spec.md
SSOT: docs/llm-decision-schema.md §4.1 / §4.3 / §4.4

Public API:

- ``confirm(...)``    — pending_confirm → confirmed (paper broker fills, UPDATE entry payload).
- ``reject(...)``     — pending_confirm → rejected (INSERT kind=reject row + UPDATE entry).
- ``sweep_expired(...)`` — bulk pending_confirm → expired for rows past timeout.
- ``list_pending(...)``  — read-only listing for the CLI ``--list`` flag.

Each mutation function owns its own ``BEGIN IMMEDIATE`` transaction so a
broker failure or status race rolls back the SQLite work atomically. The
caller passes its own ``sqlite3.Connection`` (gate never opens or closes one).
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Protocol

from ohmystock.paper.broker import BrokerError, Fill, PaperBroker


_TPE_TZ = timezone(timedelta(hours=8))
_LOT_SIZE = 1000


class Clock(Protocol):
    """Returns ISO-8601 timestamps with ``+08:00`` offset."""

    def now_iso(self) -> str:
        ...


class _SystemClock:
    def now_iso(self) -> str:
        return datetime.now(_TPE_TZ).isoformat(timespec="seconds")


system_clock: Clock = _SystemClock()


# ---------------------------------------------------------------------------
# Errors / result dataclasses
# ---------------------------------------------------------------------------


_ErrorCode = Literal[
    "not_found",
    "not_pending",
    "payload_invalid",
    "broker_failed",
]


class ConfirmGateError(Exception):
    """Raised by gate functions on contract violations or broker failures."""

    def __init__(
        self,
        code: _ErrorCode,
        message: str,
        *,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.code: _ErrorCode = code
        self.cause: Exception | None = cause


@dataclass(frozen=True)
class ConfirmResult:
    decision_id: str
    fill: Fill
    qty: int


@dataclass(frozen=True)
class RejectResult:
    decision_id: str
    reject_row_id: int


@dataclass(frozen=True)
class PendingEntry:
    decision_id: str
    symbol: str
    created_at: str
    age_seconds: int
    ttl_seconds: int
    current_price: float
    final_sizing_pct: float


# ---------------------------------------------------------------------------
# confirm() — pending_confirm → confirmed
# ---------------------------------------------------------------------------


def confirm(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    broker: PaperBroker,
    default_capital_twd: int,
    user: str,
    auto_executed: bool = False,
    clock: Clock = system_clock,
) -> ConfirmResult:
    """Promote a pending_confirm entry to confirmed via the paper broker.

    ``auto_executed=False`` (default) marks the row as a human confirm.
    ``auto_executed=True`` marks the row as the auto-execute path
    (``ohmystock.safety.auto_execute.try_auto_execute``); breakers must have
    been checked by that caller before invoking this with ``True``.
    """

    _begin_immediate(conn)
    try:
        row = _select_entry(conn, decision_id)
        if row is None:
            raise ConfirmGateError(
                "not_found",
                f"no entry row for decision_id={decision_id!r}",
            )

        symbol, payload = row
        status = payload.get("decision_status")
        if status != "pending_confirm":
            raise ConfirmGateError(
                "not_pending",
                f"entry status is {status!r}, expected 'pending_confirm'",
            )

        try:
            sizing_pct = float(payload["final_sizing_pct"])
            current_price = float(payload["current_price"])
            atr_14_pct = float(payload["atr_14_pct"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfirmGateError(
                "payload_invalid",
                "missing or non-numeric final_sizing_pct / current_price / "
                f"atr_14_pct: {exc}",
            ) from exc

        qty = _compute_qty(default_capital_twd, sizing_pct, current_price)

        try:
            fill = broker.submit_market_order(
                symbol=symbol,
                qty=qty,
                side="buy",
                reference_price=current_price,
            )
        except BrokerError as exc:
            raise ConfirmGateError(
                "broker_failed",
                f"paper broker rejected the order: {exc}",
                cause=exc,
            ) from exc

        # cheatsheet §6.6 normal-market case
        atr_at_entry = fill.fill_price * atr_14_pct / 100.0
        stop_loss_price = max(
            fill.fill_price * 0.94,
            fill.fill_price - 2.0 * atr_at_entry,
        )

        confirmed_at = clock.now_iso()
        _update_entry_payload(
            conn,
            decision_id=decision_id,
            updates={
                "decision_status": "confirmed",
                "actual_entry_price": fill.fill_price,
                "actual_qty": fill.filled_qty,
                "atr_at_entry": atr_at_entry,
                "stop_loss_price": stop_loss_price,
                "human_confirmed_by": user,
                "human_confirmed_at": confirmed_at,
                "auto_executed": auto_executed,
            },
        )
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()

    return ConfirmResult(decision_id=decision_id, fill=fill, qty=qty)


def _compute_qty(
    default_capital_twd: int,
    final_sizing_pct: float,
    current_price: float,
) -> int:
    """``max(1000, floor(capital * pct/100 / price / 1000) * 1000)``."""

    notional = default_capital_twd * (final_sizing_pct / 100.0)
    raw_shares = notional / current_price
    lots = math.floor(raw_shares / _LOT_SIZE)
    return max(_LOT_SIZE, lots * _LOT_SIZE)


# ---------------------------------------------------------------------------
# reject() — pending_confirm → rejected (human)
# ---------------------------------------------------------------------------


def reject(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    reason: str,
    user: str,
    clock: Clock = system_clock,
) -> RejectResult:
    """Insert a kind=reject (reject_layer=human) row + flip entry status."""

    if not reason or not reason.strip():
        raise ValueError("reason must be a non-empty string")

    _begin_immediate(conn)
    try:
        row = _select_entry(conn, decision_id)
        if row is None:
            raise ConfirmGateError(
                "not_found",
                f"no entry row for decision_id={decision_id!r}",
            )

        symbol, payload = row
        status = payload.get("decision_status")
        if status != "pending_confirm":
            raise ConfirmGateError(
                "not_pending",
                f"entry status is {status!r}, expected 'pending_confirm'",
            )

        ts = clock.now_iso()
        reject_payload = {
            "decision_status": "rejected",
            "reject_layer": "human",
            "reject_reason": reason,
            "rejected_by": user,
            "rejected_at": ts,
        }
        cursor = conn.execute(
            "INSERT INTO journal_entries"
            "(decision_id, kind, symbol, created_at, payload_json) "
            "VALUES (?, 'reject', ?, ?, ?)",
            (
                decision_id,
                symbol,
                ts,
                json.dumps(reject_payload, ensure_ascii=False),
            ),
        )
        reject_row_id = int(cursor.lastrowid or 0)

        _update_entry_payload(
            conn,
            decision_id=decision_id,
            updates={"decision_status": "rejected"},
        )
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()

    return RejectResult(decision_id=decision_id, reject_row_id=reject_row_id)


# ---------------------------------------------------------------------------
# sweep_expired() — bulk pending_confirm → expired (timeout)
# ---------------------------------------------------------------------------


def sweep_expired(
    conn: sqlite3.Connection,
    *,
    timeout_minutes: int,
    clock: Clock = system_clock,
) -> list[str]:
    """Write kind=expire rows for any pending_confirm entry past timeout."""

    if timeout_minutes <= 0:
        raise ValueError(
            f"timeout_minutes must be positive, got {timeout_minutes}"
        )

    now = _parse_iso(clock.now_iso())
    cutoff_delta = timedelta(minutes=timeout_minutes)

    _begin_immediate(conn)
    try:
        rows = conn.execute(
            "SELECT decision_id, symbol, created_at "
            "FROM journal_entries "
            "WHERE kind='entry' "
            "  AND json_extract(payload_json, '$.decision_status')='pending_confirm' "
            "ORDER BY created_at ASC"
        ).fetchall()

        swept: list[str] = []
        ts = clock.now_iso()
        expire_reason = f"confirm timeout after {timeout_minutes} minutes"

        for decision_id, symbol, created_at in rows:
            created_dt = _parse_iso(created_at)
            if created_dt + cutoff_delta >= now:
                continue

            expire_payload = {
                "decision_status": "expired",
                "expire_reason": expire_reason,
                "expired_at": ts,
            }
            conn.execute(
                "INSERT INTO journal_entries"
                "(decision_id, kind, symbol, created_at, payload_json) "
                "VALUES (?, 'expire', ?, ?, ?)",
                (
                    decision_id,
                    symbol,
                    ts,
                    json.dumps(expire_payload, ensure_ascii=False),
                ),
            )
            _update_entry_payload(
                conn,
                decision_id=decision_id,
                updates={"decision_status": "expired"},
            )
            swept.append(decision_id)
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()

    return swept


# ---------------------------------------------------------------------------
# list_pending() — read-only listing for CLI --list
# ---------------------------------------------------------------------------


def list_pending(
    conn: sqlite3.Connection,
    *,
    clock: Clock = system_clock,
    timeout_minutes: int,
) -> list[PendingEntry]:
    """Return all pending_confirm entries with TTL info (oldest first)."""

    if timeout_minutes <= 0:
        raise ValueError(
            f"timeout_minutes must be positive, got {timeout_minutes}"
        )

    now = _parse_iso(clock.now_iso())
    rows = conn.execute(
        "SELECT decision_id, symbol, created_at, payload_json "
        "FROM journal_entries "
        "WHERE kind='entry' "
        "  AND json_extract(payload_json, '$.decision_status')='pending_confirm' "
        "ORDER BY created_at ASC"
    ).fetchall()

    timeout_seconds = timeout_minutes * 60
    out: list[PendingEntry] = []
    for decision_id, symbol, created_at, payload_str in rows:
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            continue

        created_dt = _parse_iso(created_at)
        age_seconds = int((now - created_dt).total_seconds())
        ttl_seconds = timeout_seconds - age_seconds

        try:
            current_price = float(payload["current_price"])
            final_sizing_pct = float(payload["final_sizing_pct"])
        except (KeyError, TypeError, ValueError):
            current_price = 0.0
            final_sizing_pct = 0.0

        out.append(
            PendingEntry(
                decision_id=decision_id,
                symbol=symbol,
                created_at=created_at,
                age_seconds=age_seconds,
                ttl_seconds=ttl_seconds,
                current_price=current_price,
                final_sizing_pct=final_sizing_pct,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _begin_immediate(conn: sqlite3.Connection) -> None:
    """Open a write-locked transaction; safe even when isolation_level is set."""
    conn.execute("BEGIN IMMEDIATE")


def _select_entry(
    conn: sqlite3.Connection, decision_id: str
) -> tuple[str, dict] | None:
    row = conn.execute(
        "SELECT symbol, payload_json FROM journal_entries "
        "WHERE decision_id=? AND kind='entry' "
        "ORDER BY id DESC LIMIT 1",
        (decision_id,),
    ).fetchone()
    if row is None:
        return None
    symbol, payload_str = row
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError as exc:
        raise ConfirmGateError(
            "payload_invalid",
            f"entry payload is not valid JSON: {exc}",
        ) from exc
    return symbol, payload


def _update_entry_payload(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    updates: dict,
) -> None:
    """Read entry payload, merge updates, write back. Latest entry row wins."""

    row = conn.execute(
        "SELECT id, payload_json FROM journal_entries "
        "WHERE decision_id=? AND kind='entry' "
        "ORDER BY id DESC LIMIT 1",
        (decision_id,),
    ).fetchone()
    if row is None:
        raise ConfirmGateError(
            "not_found",
            f"entry row vanished for decision_id={decision_id!r}",
        )
    row_id, payload_str = row
    payload = json.loads(payload_str)
    payload.update(updates)
    conn.execute(
        "UPDATE journal_entries SET payload_json=? WHERE id=?",
        (json.dumps(payload, ensure_ascii=False), row_id),
    )


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_TPE_TZ)
    return dt.astimezone(timezone.utc)
