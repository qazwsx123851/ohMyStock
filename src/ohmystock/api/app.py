"""FastAPI app factory.

``create_app()`` returns a fresh FastAPI instance exposing:

* ``GET /healthz`` — liveness/version probe (no auth, no downstream calls).
* ``GET /api/admin/events`` — SSE stream that subscribes to the in-process
  ``EventBus`` and broadcasts every ``Event`` in the admin JSON shape from
  ``AdminEventSerializer``. When idle, the handler yields a comment
  ``: keepalive`` frame every 15 s so HTTP proxies (nginx default 60 s,
  Cloudflare default 100 s) do not drop the connection. On disconnect,
  ``bus.unsubscribe(q)`` runs in ``finally`` so dead queues do not leak.

This file remains *no-auth*: Bearer auth lands in a Phase 4 change.

Spec: openspec/specs/backend-api-and-eventbus/spec.md
      openspec/specs/eventbus-emitters/spec.md
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from importlib.metadata import version as _pkg_version

from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from ohmystock.api.routes.confirm_gate import router as confirm_gate_router
from ohmystock.api.routes.exit_engine import router as exit_engine_router
from ohmystock.api.routes.screener import router as screener_router
from ohmystock.eventbus import AdminEventSerializer, bus

_KEEPALIVE_TIMEOUT_SECONDS = 15.0


async def _admin_event_stream() -> AsyncGenerator[ServerSentEvent | dict[str, str], None]:
    q = bus.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=_KEEPALIVE_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                yield ServerSentEvent(comment="keepalive")
                continue

            yield {
                "event": str(event.event_type),
                "data": json.dumps(
                    AdminEventSerializer.serialize(event), ensure_ascii=False
                ),
            }
    finally:
        bus.unsubscribe(q)


def create_app() -> FastAPI:
    app = FastAPI(title="ohMyStock API", version=_pkg_version("ohmystock"))

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": _pkg_version("ohmystock")}

    @app.get("/api/admin/events")
    async def admin_events() -> EventSourceResponse:
        return EventSourceResponse(_admin_event_stream())

    app.include_router(screener_router)
    app.include_router(confirm_gate_router)
    app.include_router(exit_engine_router)

    return app
