"""Trade journal package — schema + post-commit event helper.

``emit_journal_written(kind, symbol)`` is the single chokepoint for the
``journal_written`` bus event. Every site that inserts a row into
``journal_entries`` calls this helper *after* its ``conn.commit()`` so a
subscriber can rely on the row being persisted by the time the event
arrives. Emit is best-effort (drops silently on bus failure).

Spec: openspec/specs/eventbus-emitters/spec.md §"Journal emitter"
"""

from __future__ import annotations

from ohmystock.eventbus import Agent, Event, EventType, safe_emit_sync


def emit_journal_written(kind: str, symbol: str) -> None:
    """Best-effort emit of ``journal_written`` for one committed row."""
    safe_emit_sync(
        Event(
            event_type=EventType.JOURNAL_WRITTEN,
            agent=Agent.LIBRARIAN,
            payload={"journal_kind": kind, "symbol": symbol},
        )
    )


__all__ = ["emit_journal_written"]
