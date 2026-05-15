"""ohmystock.eventbus — in-process pub/sub for backend events.

Public surface:
    * ``bus`` — module-level ``EventBus`` singleton.
    * ``EventBus`` — pub/sub primitive.
    * ``Event`` — immutable event payload.
    * ``EventType``, ``Agent`` — canonical string constants.
    * ``AdminEventSerializer`` — admin-channel JSON shape.
    * ``safe_emit`` — best-effort fire-and-forget emit.

Producers MUST call ``await safe_emit(event)`` instead of ``await
bus.emit(event)`` so that bus-side failures cannot break the producer's
primary write/return path.

Spec: openspec/specs/eventbus-emitters/spec.md
"""

from __future__ import annotations

from asyncio import QueueFull

from ohmystock.eventbus.bus import EventBus, bus
from ohmystock.eventbus.events import TPE, Event
from ohmystock.eventbus.mask_table import SymbolMaskTable
from ohmystock.eventbus.serializers import (
    DENYLIST_FIELDS,
    PUBLIC_WHITELIST,
    TWSE_CODE_RE,
    AdminEventSerializer,
    MaskedEventSerializer,
)
from ohmystock.eventbus.types import Agent, EventType


async def safe_emit(event: Event) -> None:
    """Best-effort emit: swallow ``Exception`` from the bus, never block producers.

    ``BaseException`` subclasses (``asyncio.CancelledError``, ``KeyboardInterrupt``,
    ``SystemExit``) are intentionally NOT caught so cooperative cancellation and
    interpreter shutdown still propagate.
    """
    try:
        await bus.emit(event)
    except Exception:  # noqa: BLE001 — bus failures must not break producers
        pass


def safe_emit_sync(event: Event) -> None:
    """Sync producer entry point. Iterate the bus's current subscribers and
    enqueue via ``put_nowait``; this is safe to call from any context (sync
    CLI, sync code inside an async route handler, etc.). On any exception
    (e.g. queue full, unexpected bus state), drop silently — never block or
    re-raise to the producer's caller.

    Unlike ``safe_emit``, this does NOT swallow ``BaseException``; cancellation
    and interpreter shutdown still propagate naturally because we never enter
    an ``await`` here.
    """
    try:
        for q in list(bus._subscribers):  # copy to tolerate concurrent unsub
            try:
                q.put_nowait(event)
            except QueueFull:
                pass
    except Exception:  # noqa: BLE001 — bus failures must not break producers
        pass


__all__ = [
    "DENYLIST_FIELDS",
    "PUBLIC_WHITELIST",
    "TPE",
    "TWSE_CODE_RE",
    "AdminEventSerializer",
    "Agent",
    "Event",
    "EventBus",
    "EventType",
    "MaskedEventSerializer",
    "SymbolMaskTable",
    "bus",
    "safe_emit",
    "safe_emit_sync",
]
