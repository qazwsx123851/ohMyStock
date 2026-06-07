"""Auto-execute Phase 3.5 — five hard breakers + sizing clamp + confirm reuse.

Spec: openspec/changes/auto-execute-toggle-and-breakers/specs/auto-execute/spec.md
SSOT: docs/workflow-cheatsheet.md §6.7 + docs/safety-and-simulation.md §2.9

Public API:

- ``try_auto_execute(...)`` — entry point. Reads a pending_confirm entry,
  runs five hard breakers in fixed order, optionally clamps sizing, then
  delegates to ``confirm-gate``'s ``confirm(...)`` for the broker call.
- ``AutoExecuteResult`` / ``AutoExecuteError`` / ``AutoExecuteOutcome``.

Defense-in-depth design choices:

- The settings validator already forbids ``OHMYSTOCK_AUTO_EXECUTE=true`` in
  live mode at process boundary. The ``live_broker`` breaker is a redundant
  call-time check so a runtime mutation of ``ohmystock_broker`` cannot bypass
  the guarantee.
- Every call writes exactly one ``kind=auto_execute_audit`` row, *except*
  the three contract-violation errors (``not_found`` / ``not_pending`` /
  ``payload_invalid``) and ``confirm_failed`` (which rolls back inside
  ``confirm`` itself).
- The audit row is emitted **after** ``confirm()`` returns successfully on
  the pass path. If audit insert fails, the entry is correctly confirmed
  but missing audit — that is the safer asymmetry (cf. design.md R5).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol

from ohmystock.eventbus import Agent, Event, EventType, safe_emit_sync
from ohmystock.journal import emit_journal_written
from ohmystock.safety.confirm_gate import (
    ConfirmGateError,
    ConfirmResult,
    _compute_qty,
    confirm,
)
from ohmystock.safety.sizing_clamp import (
    clamp_to_conservative,
    exceeds_deviation,
    exceeds_notional_limit,
)


_TPE_TZ = timezone(timedelta(hours=8))


class _SettingsLike(Protocol):
    """Subset of ``ohmystock.config.Settings`` consumed by this module.

    Tests pass either a real ``Settings`` instance or a stand-in with the
    same fields; both work.
    """

    ohmystock_broker: str
    ohmystock_auto_execute: bool
    ohmystock_auto_execute_daily_limit: int
    ohmystock_auto_execute_min_confidence: float
    ohmystock_auto_execute_max_notional_pct: float
    ohmystock_auto_execute_max_sizing_deviation: float
    ohmystock_auto_execute_loss_lockout_hours: int
    ohmystock_auto_execute_loss_pct_threshold: float
    ohmystock_auto_execute_account_equity_twd: int


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
    "confirm_failed",
]


AutoExecuteOutcome = Literal[
    "pass",
    "sizing_clamped_then_pass",
    "flag_off",
    "low_confidence",
    "daily_limit",
    "notional_limit",
    "loss_lockout",
    "live_broker",
]


class AutoExecuteError(Exception):
    """Raised on contract violations or downstream confirm failures."""

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
class AutoExecuteResult:
    decision_id: str
    outcome: AutoExecuteOutcome
    confirm_result: ConfirmResult | None
    evidence: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def try_auto_execute(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    broker: Any,
    settings: _SettingsLike,
    clock: Clock = system_clock,
) -> AutoExecuteResult:
    """Run breakers; on pass, call confirm() and write a pass audit row."""

    symbol, payload = _parse_pending_entry(conn, decision_id)

    # Breaker 2 — flag_off
    if not settings.ohmystock_auto_execute:
        evidence = {"flag": False}
        _write_audit(
            conn,
            decision_id=decision_id,
            symbol=symbol,
            outcome="flag_off",
            evidence=evidence,
            clock=clock,
        )
        _emit_risk_off("flag_off")
        return AutoExecuteResult(
            decision_id=decision_id,
            outcome="flag_off",
            confirm_result=None,
            evidence=evidence,
        )

    # Breaker 3 — live_broker (redundant w/ Settings validator; defense-in-depth)
    if settings.ohmystock_broker == "shioaji-live":
        evidence = {"broker_mode": "shioaji-live"}
        _write_audit(
            conn,
            decision_id=decision_id,
            symbol=symbol,
            outcome="live_broker",
            evidence=evidence,
            clock=clock,
        )
        _emit_risk_off("live_broker")
        return AutoExecuteResult(
            decision_id=decision_id,
            outcome="live_broker",
            confirm_result=None,
            evidence=evidence,
        )

    # Breaker 4 — low_confidence
    llm_confidence = float(payload["llm_confidence"])
    min_confidence = settings.ohmystock_auto_execute_min_confidence
    if llm_confidence < min_confidence:
        evidence = {
            "llm_confidence": llm_confidence,
            "min_confidence": min_confidence,
        }
        _write_audit(
            conn,
            decision_id=decision_id,
            symbol=symbol,
            outcome="low_confidence",
            evidence=evidence,
            clock=clock,
        )
        _emit_risk_off("low_confidence")
        return AutoExecuteResult(
            decision_id=decision_id,
            outcome="low_confidence",
            confirm_result=None,
            evidence=evidence,
        )

    # Breaker 5 — notional_limit
    final_sizing_pct = float(payload["final_sizing_pct"])
    current_price = float(payload["current_price"])
    equity = settings.ohmystock_auto_execute_account_equity_twd
    qty = _compute_qty(equity, final_sizing_pct, current_price)
    notional = qty * current_price
    max_notional = equity * settings.ohmystock_auto_execute_max_notional_pct
    if exceeds_notional_limit(
        qty,
        current_price,
        equity,
        settings.ohmystock_auto_execute_max_notional_pct,
    ):
        evidence = {
            "notional_twd": notional,
            "max_notional_twd": max_notional,
        }
        _write_audit(
            conn,
            decision_id=decision_id,
            symbol=symbol,
            outcome="notional_limit",
            evidence=evidence,
            clock=clock,
        )
        _emit_risk_off("notional_limit")
        return AutoExecuteResult(
            decision_id=decision_id,
            outcome="notional_limit",
            confirm_result=None,
            evidence=evidence,
        )

    # Breaker 6 — daily_limit
    auto_today = _count_auto_executed_today(conn, clock=clock)
    daily_limit = settings.ohmystock_auto_execute_daily_limit
    if auto_today >= daily_limit:
        evidence = {
            "auto_today_count": auto_today,
            "daily_limit": daily_limit,
        }
        _write_audit(
            conn,
            decision_id=decision_id,
            symbol=symbol,
            outcome="daily_limit",
            evidence=evidence,
            clock=clock,
        )
        _emit_risk_off("daily_limit")
        return AutoExecuteResult(
            decision_id=decision_id,
            outcome="daily_limit",
            confirm_result=None,
            evidence=evidence,
        )

    # Breaker 7 — loss_lockout (graceful no-op until exit-engine writes rows)
    lockout_until = _check_loss_lockout(conn, settings=settings, clock=clock)
    if lockout_until is not None:
        evidence = {
            "loss_streak_count": 3,
            "lockout_until": lockout_until,
        }
        _write_audit(
            conn,
            decision_id=decision_id,
            symbol=symbol,
            outcome="loss_lockout",
            evidence=evidence,
            clock=clock,
        )
        _emit_risk_off("loss_lockout")
        return AutoExecuteResult(
            decision_id=decision_id,
            outcome="loss_lockout",
            confirm_result=None,
            evidence=evidence,
        )

    # Step 8 — sizing clamp (NOT a fallback)
    stage = int(payload["stage"])
    sys_pct = _system_sizing_pct(stage)
    raw_sizing = final_sizing_pct
    clamped_sizing: float | None = None
    outcome_label: AutoExecuteOutcome = "pass"
    if exceeds_deviation(
        final_sizing_pct,
        sys_pct,
        settings.ohmystock_auto_execute_max_sizing_deviation,
    ):
        clamped_sizing = clamp_to_conservative(final_sizing_pct, sys_pct)
        # UPDATE the entry payload in-place so confirm() sees the clamped value.
        _patch_entry_payload(
            conn,
            decision_id=decision_id,
            updates={"final_sizing_pct": clamped_sizing},
        )
        outcome_label = "sizing_clamped_then_pass"

    # Step 9 — call confirm() (re-uses qty/ATR/stop-loss math)
    try:
        result = confirm(
            conn,
            decision_id=decision_id,
            broker=broker,
            default_capital_twd=equity,
            user="auto",
            auto_executed=True,
            clock=clock,
        )
    except ConfirmGateError as exc:
        # confirm() already rolled back its own transaction; we deliberately
        # do NOT write an audit row here (asymmetric — better to lack audit
        # than to record a confirmation that didn't happen).
        raise AutoExecuteError(
            "confirm_failed",
            f"confirm() failed under auto-execute: {exc}",
            cause=exc,
        ) from exc

    # Step 10 — write pass audit row
    pass_evidence: dict[str, Any] = {
        "llm_confidence": llm_confidence,
        "auto_today_count": auto_today + 1,
        "notional_twd": result.qty * float(payload["current_price"]),
        "system_sizing_pct": sys_pct,
        "raw_sizing_pct": raw_sizing,
        "clamped_sizing_pct": clamped_sizing,
        "broker_mode": settings.ohmystock_broker,
    }
    _write_audit(
        conn,
        decision_id=decision_id,
        symbol=symbol,
        outcome=outcome_label,
        evidence=pass_evidence,
        clock=clock,
    )
    return AutoExecuteResult(
        decision_id=decision_id,
        outcome=outcome_label,
        confirm_result=result,
        evidence=pass_evidence,
    )


# ---------------------------------------------------------------------------
# Helpers — entry parsing
# ---------------------------------------------------------------------------


_REQUIRED_PAYLOAD_KEYS = (
    "llm_confidence",
    "current_price",
    "final_sizing_pct",
    "stage",
)


def _parse_pending_entry(
    conn: sqlite3.Connection, decision_id: str
) -> tuple[str, dict[str, Any]]:
    row = conn.execute(
        "SELECT symbol, payload_json FROM journal_entries "
        "WHERE decision_id=? AND kind='entry' "
        "ORDER BY id DESC LIMIT 1",
        (decision_id,),
    ).fetchone()
    if row is None:
        raise AutoExecuteError(
            "not_found",
            f"no entry row for decision_id={decision_id!r}",
        )
    symbol, payload_str = row
    try:
        payload: dict[str, Any] = json.loads(payload_str)
    except json.JSONDecodeError as exc:
        raise AutoExecuteError(
            "payload_invalid",
            f"entry payload is not valid JSON: {exc}",
        ) from exc

    status = payload.get("decision_status")
    if status != "pending_confirm":
        raise AutoExecuteError(
            "not_pending",
            f"entry status is {status!r}, expected 'pending_confirm'",
        )

    for key in _REQUIRED_PAYLOAD_KEYS:
        if key not in payload:
            raise AutoExecuteError(
                "payload_invalid",
                f"entry payload missing required key {key!r}",
            )
        if payload[key] is None:
            raise AutoExecuteError(
                "payload_invalid",
                f"entry payload key {key!r} is null",
            )
    return symbol, payload


def _patch_entry_payload(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    updates: dict[str, Any],
) -> None:
    """Read the latest entry payload, merge updates, commit.

    The explicit ``commit()`` closes the auto-opened transaction Python's
    sqlite3 driver starts on the UPDATE; without it the subsequent
    ``confirm()`` call would fail to open its own ``BEGIN IMMEDIATE``.
    Persisting the clamp before confirm runs is also semantically right —
    it reflects auto-execute's policy decision regardless of whether the
    broker call succeeds.
    """
    row = conn.execute(
        "SELECT id, payload_json FROM journal_entries "
        "WHERE decision_id=? AND kind='entry' "
        "ORDER BY id DESC LIMIT 1",
        (decision_id,),
    ).fetchone()
    if row is None:
        raise AutoExecuteError(
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
    conn.commit()


# ---------------------------------------------------------------------------
# Helpers — system_sizing_pct + breaker queries
# ---------------------------------------------------------------------------


def _system_sizing_pct(stage: int) -> float:
    """v0 stub matching docs/workflow-cheatsheet.md §6.6 stage caps.

    Will be replaced with the real Volatility Targeting formula in a future
    change. The ``entry-decider`` already writes this same value into
    ``payload.system_sizing_pct``; we recompute here so a payload missing the
    field still gets a sensible breaker value.
    """
    return 10.0 if stage == 3 else 25.0


def _today_tpe_midnight_iso(now_iso: str) -> str:
    """Return the ISO-8601 timestamp for today's TPE 00:00:00."""
    now = datetime.fromisoformat(now_iso)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_TPE_TZ)
    tpe_now = now.astimezone(_TPE_TZ)
    midnight = tpe_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.isoformat(timespec="seconds")


def _count_auto_executed_today(
    conn: sqlite3.Connection, *, clock: Clock
) -> int:
    """Count kind=entry rows confirmed by the auto path within today TPE."""
    now_iso = clock.now_iso()
    midnight_iso = _today_tpe_midnight_iso(now_iso)
    row = conn.execute(
        "SELECT COUNT(*) FROM journal_entries "
        "WHERE kind='entry' "
        "  AND json_extract(payload_json, '$.auto_executed') = 1 "
        "  AND json_extract(payload_json, '$.human_confirmed_at') >= ? "
        "  AND json_extract(payload_json, '$.human_confirmed_at') < ?",
        (midnight_iso, now_iso),
    ).fetchone()
    return int(row[0]) if row else 0


def _check_loss_lockout(
    conn: sqlite3.Connection,
    *,
    settings: _SettingsLike,
    clock: Clock,
) -> str | None:
    """Return the lockout_until ISO timestamp if the streak is active, else None.

    Reads the last 3 ``kind=exit`` rows where ``payload.source='auto'`` (most
    recent first). If fewer than 3 exist → no lockout. If all three pnl values
    are below the loss threshold AND the latest ``closed_at + lockout_hours``
    is still in the future, lockout is active.
    """
    rows = conn.execute(
        "SELECT json_extract(payload_json, '$.realized_pnl_pct') AS pnl,"
        " json_extract(payload_json, '$.closed_at') AS closed_at"
        " FROM journal_entries"
        " WHERE kind='exit'"
        "   AND json_extract(payload_json, '$.source') = 'auto'"
        " ORDER BY id DESC LIMIT 3"
    ).fetchall()
    if len(rows) < 3:
        return None

    threshold = settings.ohmystock_auto_execute_loss_pct_threshold
    pnls = []
    closed_ats = []
    for pnl, closed_at in rows:
        if pnl is None or closed_at is None:
            return None
        pnls.append(float(pnl))
        closed_ats.append(str(closed_at))
    if any(p >= threshold for p in pnls):
        return None

    latest_closed = max(_parse_iso(c) for c in closed_ats)
    lockout_until_dt = latest_closed + timedelta(
        hours=settings.ohmystock_auto_execute_loss_lockout_hours
    )
    now_dt = _parse_iso(clock.now_iso())
    if lockout_until_dt <= now_dt:
        return None
    return lockout_until_dt.astimezone(_TPE_TZ).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Helpers — audit writer
# ---------------------------------------------------------------------------


def _write_audit(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    symbol: str,
    outcome: AutoExecuteOutcome,
    evidence: dict[str, Any],
    clock: Clock,
) -> None:
    ts = clock.now_iso()
    payload = {
        "decision_status": "auto_execute_audit",
        "outcome": outcome,
        "decision_id_ref": decision_id,
        "audit_at": ts,
        "evidence": evidence,
    }
    conn.execute(
        "INSERT INTO journal_entries"
        "(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'auto_execute_audit', ?, ?, ?)",
        (
            decision_id,
            symbol,
            ts,
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    conn.commit()
    emit_journal_written("auto_execute_audit", symbol)


_RISK_OFF_SEVERITY: dict[str, str] = {
    "flag_off": "warn",
    "low_confidence": "warn",
    "live_broker": "halt",
    "notional_limit": "halt",
    "daily_limit": "halt",
    "loss_lockout": "halt",
}


def _emit_risk_off(reason_category: str) -> None:
    """Emit risk_off_triggered for breaker outcomes only (not pass / clamp)."""
    severity = _RISK_OFF_SEVERITY.get(reason_category)
    if severity is None:
        return
    safe_emit_sync(
        Event(
            event_type=EventType.RISK_OFF_TRIGGERED,
            agent=Agent.GUARD,
            payload={"reason_category": reason_category, "severity": severity},
        )
    )


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_TPE_TZ)
    return dt.astimezone(timezone.utc)
