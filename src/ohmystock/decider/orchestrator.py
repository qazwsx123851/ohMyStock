"""Decider orchestration — LLM call → validation → journal + llm_costs.

``decide_entry`` is the single public entry point. It owns the SQLite
transaction boundary so a write failure rolls back both the journal row
and the cost row together.

Three terminal paths:
- LLM enters and §2.1 passes → ``kind=entry`` (pending_confirm) + cost row.
- LLM rejects, or §2.1 force-rejects → ``kind=reject`` (reject_layer=llm)
  + cost row.
- LLM raises ``DeciderOutputParseError`` → ``kind=reject`` (reject_layer=llm,
  reject_reason starts with ``"json_parse_error:"``) + cost row with zero
  tokens; the exception is then re-raised.

Spec: openspec/changes/entry-decider-pm-node/specs/entry-decider/spec.md
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal, Protocol

from ohmystock.config import Settings
from ohmystock.decider._journal_writer import (
    write_entry_pending_confirm,
    write_llm_cost,
    write_reject_llm,
)
from ohmystock.decider.models import DeciderOutput
from ohmystock.decider.node import (
    DeciderOutputParseError,
    LLMUsage,
    PMConclusionNode,
)
from ohmystock.decider.validator import validate_decider_output
from ohmystock.eventbus import Agent, Event, EventType, safe_emit_sync
from ohmystock.journal import emit_journal_written
from ohmystock.swarm.models import EntryDecisionInput


_TPE_TZ = timezone(timedelta(hours=8))
_PARSE_ERROR_REASON_MAX_CHARS = 500


class Clock(Protocol):
    """Protocol for an injectable clock; returns ISO-8601 +08:00 timestamps."""

    def now_iso(self) -> str:
        ...


class _SystemClock:
    def now_iso(self) -> str:
        return datetime.now(_TPE_TZ).isoformat(timespec="seconds")


system_clock: Clock = _SystemClock()


def default_decision_id(entry_input: EntryDecisionInput) -> str:
    """Default factory: reuse the input's decision_id (already filesystem-safe).

    The ``EntryDecisionInput`` produced by Phase 2B's
    ``build_entry_decision_input`` already normalises ``trigger_at`` into
    ``"dec_<YYYY-MM-DDTHH-MM-SS>_<symbol>"`` form, so we just forward it.
    """
    return entry_input.decision_id


@dataclass(frozen=True)
class OrchestrationResult:
    """Outcome of :func:`decide_entry`."""

    decision_id: str
    final: DeciderOutput
    written_kind: Literal["entry", "reject"]
    llm_cost: LLMUsage | None
    force_reject_reason: str | None


def decide_entry(
    entry_input: EntryDecisionInput,
    *,
    conn: sqlite3.Connection,
    decider: PMConclusionNode,
    clock: Clock = system_clock,
    decision_id_factory: Callable[
        [EntryDecisionInput], str
    ] = default_decision_id,
) -> OrchestrationResult:
    """Run the LLM decider, validate, write journal + cost rows atomically."""

    decision_id = decision_id_factory(entry_input)
    created_at = clock.now_iso()

    safe_emit_sync(
        Event(
            event_type=EventType.DECIDER_THINKING,
            agent=Agent.DECIDER,
            payload={
                "symbol": entry_input.candidate.symbol,
                "confidence_so_far": 0.0,
            },
        )
    )

    try:
        raw, usage = decider.decide(entry_input)
    except DeciderOutputParseError as exc:
        reason = _parse_error_reason(exc)
        with _atomic(conn):
            write_reject_llm(
                conn,
                decision_id=decision_id,
                entry_input=entry_input,
                raw=None,
                usage=None,
                reject_reason=reason,
                created_at=created_at,
            )
            write_llm_cost(
                conn,
                decision_id=decision_id,
                usage=None,
                created_at=created_at,
            )
        emit_journal_written("reject", entry_input.candidate.symbol)
        raise

    vr = validate_decider_output(raw, entry_input.candidate)

    with _atomic(conn):
        if vr.force_reject_reason is None and raw.decision == "enter":
            write_entry_pending_confirm(
                conn,
                decision_id=decision_id,
                entry_input=entry_input,
                raw=raw,
                final=vr.final_decision,
                usage=usage,
                created_at=created_at,
            )
            written_kind: Literal["entry", "reject"] = "entry"
        else:
            reject_reason = vr.force_reject_reason or _llm_reject_reason(raw)
            write_reject_llm(
                conn,
                decision_id=decision_id,
                entry_input=entry_input,
                raw=raw,
                usage=usage,
                reject_reason=reject_reason,
                applied_overrides=list(vr.applied_overrides),
                created_at=created_at,
            )
            written_kind = "reject"

        write_llm_cost(
            conn,
            decision_id=decision_id,
            usage=usage,
            created_at=created_at,
        )

    emit_journal_written(written_kind, entry_input.candidate.symbol)

    safe_emit_sync(
        Event(
            event_type=EventType.DECISION_MADE,
            agent=Agent.DECIDER,
            payload={
                "symbol": entry_input.candidate.symbol,
                "confidence": float(raw.confidence),
                "reasoning": raw.reasoning,
                "action": "entry" if written_kind == "entry" else "skip",
            },
        )
    )

    if written_kind == "entry":
        timeout_at = _compute_timeout_at(created_at)
        safe_emit_sync(
            Event(
                event_type=EventType.AWAITING_CONFIRM,
                agent=Agent.TRADER,
                payload={
                    "symbol": entry_input.candidate.symbol,
                    "timeout_at": timeout_at,
                    "expected_price": entry_input.candidate.current_price,
                },
            )
        )

    return OrchestrationResult(
        decision_id=decision_id,
        final=vr.final_decision,
        written_kind=written_kind,
        llm_cost=usage,
        force_reject_reason=vr.force_reject_reason,
    )


class _atomic:
    """Context manager that BEGIN/COMMITs and rolls back on any exception."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        self._conn.execute("BEGIN")
        return self._conn

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()


def _parse_error_reason(exc: DeciderOutputParseError) -> str:
    raw = (exc.raw_text or "")[:_PARSE_ERROR_REASON_MAX_CHARS]
    return f"json_parse_error: {raw}"


def _compute_timeout_at(created_at: str) -> str:
    """``created_at`` (ISO-8601 +08:00) + Settings confirm timeout, ISO-8601."""
    settings = Settings()
    delta = timedelta(minutes=settings.ohmystock_confirm_timeout_minutes)
    return (datetime.fromisoformat(created_at) + delta).isoformat(timespec="seconds")


def _llm_reject_reason(raw: DeciderOutput) -> str:
    """Reason string for a non-force LLM-volunteered reject."""
    return f"llm_voluntary_reject:{raw.decision}"
