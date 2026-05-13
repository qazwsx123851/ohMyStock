"""Admin HTTP surface for swarm-style pipeline runs.

Endpoints (all require Bearer auth via ``require_admin`` and use the
``{ok, data, error}`` envelope):

* ``GET  /api/admin/swarm/presets``      — registry-driven preset list.
* ``POST /api/admin/swarm/runs``         — synchronous run, persists row.
* ``GET  /api/admin/swarm/runs``         — paginated history (no result_json).
* ``GET  /api/admin/swarm/runs/{id}``    — full detail incl. parsed result.

``_MARKET_DATA_LOADER_FACTORY`` is the test seam — production builds the
loader from ``get_db()`` + ``CachedMarketData`` matching the CLI behaviour.

Spec: openspec/changes/admin-swarm-endpoints-and-pages/specs/swarm-runs/spec.md
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from ohmystock.api.auth import require_admin
from ohmystock.api.routes._deps import get_db
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_error,
    to_success,
)
from ohmystock.config import Settings
from ohmystock.data import cache as data_cache
from ohmystock.review import MarketDataLoader
from ohmystock.swarm_runs import storage as swarm_storage
from ohmystock.swarm_runs.presets import PRESETS
from ohmystock.swarm_runs.runner import SwarmRunnerError, run_swarm


router = APIRouter(prefix="/api/admin/swarm", dependencies=[Depends(require_admin)])

_INVALID_NAME_TOKENS: tuple[str, ...] = ("/", "\\", "..", os.sep)
_DEFAULT_LIMIT = 50
_MAX_LIMIT = 100
_CHEATSHEET_PATH = Path("docs/workflow-cheatsheet.md")


class _CachedMarketData:
    """Default ``MarketDataLoader`` reading cached daily bars only.

    Mirrors ``ohmystock.cli._review._CachedMarketData`` so admin runs and
    CLI runs see the same market data for the same period.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def select_bars(
        self, symbol: str, exit_date: date, days: int
    ) -> list[float]:
        start = (exit_date + timedelta(days=1)).isoformat()
        end = (exit_date + timedelta(days=days * 2 + 7)).isoformat()
        bars = data_cache.select_bars(self.conn, symbol, start, end)
        closes = [float(b["c"]) for b in bars]
        return closes[:days]


# Test override seam: ``monkeypatch.setattr(routes.swarm,
# "_MARKET_DATA_LOADER_FACTORY", lambda conn: synthetic_loader)`` lets
# tests bypass the SQLite cache entirely.
_MARKET_DATA_LOADER_FACTORY: Callable[[sqlite3.Connection], MarketDataLoader] = (
    lambda conn: _CachedMarketData(conn)
)


class SwarmRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    preset: str
    params: dict[str, Any]


def _is_safe_id(run_id: str) -> bool:
    return not any(bad in run_id for bad in _INVALID_NAME_TOKENS)


def _summary_row(row: swarm_storage.SwarmRunRowDict) -> dict[str, Any]:
    return {
        "id": row["id"],
        "preset": row["preset"],
        "status": row["status"],
        "elapsed_ms": row["elapsed_ms"],
        "created_at": row["created_at"],
    }


def _full_row(row: swarm_storage.SwarmRunRowDict) -> dict[str, Any]:
    return {
        "id": row["id"],
        "preset": row["preset"],
        "status": row["status"],
        "params": json.loads(row["params_json"]),
        "result": json.loads(row["result_json"]),
        "elapsed_ms": row["elapsed_ms"],
        "created_at": row["created_at"],
    }


def _runner_error_to_envelope(exc: SwarmRunnerError) -> tuple[int, dict[str, Any]]:
    msg = str(exc)
    if msg.startswith("missing_api_key:"):
        return 422, to_error("missing_api_key", msg)
    if msg.startswith("invalid_params:"):
        return 400, to_error("invalid_input", msg)
    if msg.startswith("unknown_preset:"):
        return 400, to_error("invalid_input", msg)
    return 422, to_error("swarm_runner_failed", msg)


@router.get("/presets")
async def list_presets() -> JSONResponse:
    items = [
        {
            "name": p.name,
            "title": p.title,
            "description": p.description,
            "nodes": list(p.nodes),
            "params_schema": dict(p.params_schema),
        }
        for p in PRESETS.values()
    ]
    return JSONResponse(status_code=200, content=to_success({"items": items}))


@router.post("/runs")
async def post_run(
    body: SwarmRunRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    settings = Settings()
    out_dir = Path(settings.reviews_dir)
    proposals_dir = Path(settings.proposals_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    proposals_dir.mkdir(parents=True, exist_ok=True)
    market_data_loader = _MARKET_DATA_LOADER_FACTORY(conn)

    try:
        result = await run_swarm(
            body.preset,
            dict(body.params),
            db_conn=conn,
            out_dir=out_dir,
            proposals_dir=proposals_dir,
            market_data_loader=market_data_loader,
            cheatsheet_path=_CHEATSHEET_PATH,
        )
    except SwarmRunnerError as exc:
        status, envelope = _runner_error_to_envelope(exc)
        return JSONResponse(status_code=status, content=envelope)
    except Exception as exc:  # noqa: BLE001 — never leak details
        status, envelope = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=envelope)

    payload = {
        "id": result.run_id,
        "preset": result.preset,
        "status": result.status,
        "params": result.params,
        "result": result.result,
        "elapsed_ms": result.elapsed_ms,
        "created_at": result.created_at,
    }
    return JSONResponse(status_code=200, content=to_success(payload))


@router.get("/runs")
async def list_runs(
    limit: int = Query(default=_DEFAULT_LIMIT),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    if limit < 1:
        return JSONResponse(
            status_code=400,
            content=to_error("invalid_input", "limit must be >= 1"),
        )
    effective_limit = min(limit, _MAX_LIMIT)
    rows = swarm_storage.select_recent(conn, effective_limit)
    return JSONResponse(
        status_code=200,
        content=to_success(
            {
                "items": [_summary_row(r) for r in rows],
                "limit": effective_limit,
            }
        ),
    )


@router.get("/runs/{run_id:path}")
async def get_run(
    run_id: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    if not _is_safe_id(run_id):
        return JSONResponse(
            status_code=400,
            content=to_error("invalid_input", f"invalid run_id: {run_id!r}"),
        )
    row = swarm_storage.select_by_id(conn, run_id)
    if row is None:
        return JSONResponse(
            status_code=404,
            content=to_error("not_found", f"swarm run not found: {run_id}"),
        )
    return JSONResponse(status_code=200, content=to_success(_full_row(row)))
