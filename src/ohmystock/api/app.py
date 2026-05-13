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
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version as _pkg_version

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from ohmystock.api.auth import AuthError, _validate_admin_token, require_admin
from ohmystock.api.db import get_connection
from ohmystock.api.routes._envelope import to_error
from ohmystock.api.routes.backtest import router as backtest_router
from ohmystock.api.routes.confirm_gate import router as confirm_gate_router
from ohmystock.api.routes.exit_engine import router as exit_engine_router
from ohmystock.api.routes.journal import router as journal_router
from ohmystock.api.routes.market import router as market_router
from ohmystock.api.routes.memory import router as memory_router
from ohmystock.api.routes.positions import router as positions_router
from ohmystock.api.routes.proposals import router as proposals_router
from ohmystock.api.routes.reviews import router as reviews_router
from ohmystock.api.routes.screener import router as screener_router
from ohmystock.api.routes.settings import router as settings_router
from ohmystock.api.routes.skills import router as skills_router
from ohmystock.api.routes.stats import router as stats_router
from ohmystock.backtest import storage as backtest_storage
from ohmystock.config import Settings
from ohmystock.data.disposition import fetch_disposition_set
from ohmystock.eventbus import AdminEventSerializer, bus
from ohmystock.memory import init_schema as memory_init_schema
from ohmystock.sepa.rs import reset_providers, set_universe_closes_loader
from ohmystock.sepa.rs_loader import build_universe_closes_loader

_KEEPALIVE_TIMEOUT_SECONDS = 15.0


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Wire the rs-percentile universe-closes loader for the app's lifetime.

    Also bootstraps the ``backtest_jobs`` schema and the ``memory_rows`` +
    FTS5 schema once at startup so the first request against a fresh DB
    succeeds without relying on per-handler init calls. Both
    ``init_schema`` calls are idempotent.

    Spec: openspec/changes/rs-percentile-finmind-wiring/specs/rs-percentile/spec.md
    ("Production universe-closes loader …")
          openspec/changes/web-admin-memory-page-and-store/specs/admin-memory-endpoints/spec.md
    ("Requirement: ``init_schema`` wired from app lifespan")
    """
    set_universe_closes_loader(
        build_universe_closes_loader(disposition_fetcher=fetch_disposition_set)
    )

    init_conn = get_connection()
    try:
        backtest_storage.init_schema(init_conn)
        memory_init_schema(init_conn)
    finally:
        init_conn.close()

    try:
        yield
    finally:
        reset_providers()


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
    # Fail-fast: refuse to construct the app if OHMYSTOCK_ADMIN_TOKEN is
    # missing or shorter than 32 chars. Performed BEFORE any router is
    # registered so a misconfigured deploy can never serve admin routes
    # (web-admin-bearer-auth spec §「啟動時驗證 OHMYSTOCK_ADMIN_TOKEN」).
    _validate_admin_token(Settings())

    app = FastAPI(
        title="ohMyStock API",
        version=_pkg_version("ohmystock"),
        lifespan=_lifespan,
    )

    # Map AuthError raised by `require_admin` into the unified envelope.
    # `Depends` runs before route handlers, so the inline try/except inside
    # individual handlers cannot catch it — we need an app-level handler.
    @app.exception_handler(AuthError)
    async def _auth_error_handler(
        request: Request, exc: AuthError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=401, content=to_error(exc.code, exc.message)
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": _pkg_version("ohmystock")}

    @app.get("/api/admin/events", dependencies=[Depends(require_admin)])
    async def admin_events() -> EventSourceResponse:
        return EventSourceResponse(_admin_event_stream())

    app.include_router(screener_router)
    app.include_router(confirm_gate_router)
    app.include_router(exit_engine_router)
    app.include_router(journal_router)
    app.include_router(market_router)
    app.include_router(memory_router)
    app.include_router(positions_router)
    app.include_router(stats_router)
    app.include_router(backtest_router)
    app.include_router(settings_router)
    app.include_router(skills_router)
    app.include_router(proposals_router)
    app.include_router(reviews_router)

    return app
