"""Public SSE channel — masked event stream for ``web-public/``.

No bearer token, no admin token, no protection. The only safety guarantee is
the ``MaskedEventSerializer`` applied to every frame: payloads are passed
through ``PUBLIC_WHITELIST`` and ``DENYLIST_FIELDS`` before they leave the
process.

A single ``SymbolMaskTable`` + ``MaskedEventSerializer`` pair is installed
once at app startup via :func:`set_mask_table` and torn down via
:func:`clear_mask_table` so that any reference after shutdown raises a clear
runtime error instead of silently serving stale state.

Spec: openspec/changes/web-public-shell-and-mask/specs/admin-public-events-endpoint/spec.md
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from ohmystock.eventbus import MaskedEventSerializer, SymbolMaskTable, bus

_KEEPALIVE_TIMEOUT_SECONDS = 15.0

_mask_table: SymbolMaskTable | None = None
_serializer: MaskedEventSerializer | None = None


def set_mask_table(mask_table: SymbolMaskTable) -> None:
    """Install the process-scoped mask table + serializer.

    Called once from ``api/app.py:_lifespan`` after the industry lookup is
    loaded from ``universe_daily``. Calling twice replaces the previous
    instance — useful for tests.
    """
    global _mask_table, _serializer
    _mask_table = mask_table
    _serializer = MaskedEventSerializer(mask_table)


def clear_mask_table() -> None:
    """Null the module globals so any post-shutdown reference raises."""
    global _mask_table, _serializer
    _mask_table = None
    _serializer = None


def get_mask_table() -> SymbolMaskTable | None:
    """Test helper — returns the currently-installed mask table or ``None``."""
    return _mask_table


async def _public_event_stream() -> AsyncGenerator[ServerSentEvent | dict[str, str], None]:
    serializer = _serializer
    if serializer is None:
        raise RuntimeError(
            "public-events route invoked before set_mask_table() was called"
        )
    q = bus.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(
                    q.get(), timeout=_KEEPALIVE_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                yield ServerSentEvent(comment="keepalive")
                continue

            yield {
                "event": str(event.event_type),
                "data": json.dumps(
                    serializer.serialize(event), ensure_ascii=False
                ),
            }
    finally:
        bus.unsubscribe(q)


router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/events")
async def public_events() -> EventSourceResponse:
    return EventSourceResponse(_public_event_stream())
