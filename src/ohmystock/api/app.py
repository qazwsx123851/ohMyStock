"""FastAPI app factory.

create_app() returns a fresh FastAPI instance with /healthz and
/api/admin/events. The bootstrap change emits a 15-second heartbeat on
the SSE stream and does NOT wire EventBus into it — that lands in a
later change. Factory mode (no module-level `app`) is enforced so
uvicorn --reload and tests both build clean instances.

Spec: openspec/changes/fastapi-bootstrap/specs/backend-api-and-eventbus/spec.md
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime
from importlib.metadata import version as _pkg_version

from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse

from ohmystock.eventbus.events import TPE


async def _admin_event_stream() -> AsyncGenerator[dict[str, str], None]:
    try:
        while True:
            yield {
                "event": "heartbeat",
                "data": json.dumps({"ts": datetime.now(TPE).isoformat()}),
            }
            await asyncio.sleep(15)
    finally:
        # Phase 1 will replace this with bus.unsubscribe(q) once EventBus is wired in.
        pass


def create_app() -> FastAPI:
    app = FastAPI(title="ohMyStock API", version=_pkg_version("ohmystock"))

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": _pkg_version("ohmystock")}

    @app.get("/api/admin/events")
    async def admin_events() -> EventSourceResponse:
        return EventSourceResponse(_admin_event_stream())

    return app
