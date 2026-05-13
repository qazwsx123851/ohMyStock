"""Swarm runner — thin async wrapper over ``review.pipeline.run_review``.

For v0 the only preset (``phase5-review``) wraps a single synchronous
``run_review`` call and emits per-node SSE events around it. The first
node's ``swarm_node_started`` is fired BEFORE ``run_review`` is invoked;
the remaining started/completed events fire after the call returns.

On failure, the failed node is inferred from which expected output files
exist on disk under ``out_dir/<review_id>/`` (per
``post-trade-review-pipeline`` spec § "Pipeline 以固定順序 sequential 執行
5 節點"). In dry-run mode, no files are written, so the failed node
defaults to the first preset node.

Spec: openspec/changes/admin-swarm-endpoints-and-pages/specs/swarm-runs/spec.md
      openspec/changes/admin-swarm-endpoints-and-pages/specs/eventbus-emitters/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ohmystock.config import Settings
from ohmystock.eventbus import Agent, Event, EventType, safe_emit
from ohmystock.review.llm_client import ReviewLLM
from ohmystock.review.nodes.data_loader import MarketDataLoader
from ohmystock.review.pipeline import ReviewResult, run_review
from ohmystock.swarm_runs.presets import get_preset
from ohmystock.swarm_runs.storage import SwarmRunRowDict, insert_run

_TPE = timezone(timedelta(hours=8))


class SwarmRunnerError(Exception):
    """Raised when input validation fails BEFORE any state is mutated.

    Token prefixes (matched by endpoint envelope mapping):
      - ``unknown_preset:`` → 400 invalid_input
      - ``invalid_params:`` → 400 invalid_input
      - ``missing_api_key:`` → 422 missing_api_key
    """


@dataclass(frozen=True)
class SwarmRunResult:
    """Return value of :func:`run_swarm`.

    ``status`` is always ``completed`` or ``failed``. ``result`` is the
    parsed dict that was JSON-serialised into ``swarm_runs.result_json``.
    """

    run_id: str
    status: str
    preset: str
    params: dict[str, Any]
    result: dict[str, Any]
    elapsed_ms: int
    created_at: str


async def run_swarm(
    preset_name: str,
    params: dict[str, Any],
    *,
    db_conn: sqlite3.Connection,
    out_dir: Path,
    proposals_dir: Path,
    market_data_loader: MarketDataLoader,
    cheatsheet_path: Path,
    llm_factory: Callable[[str], ReviewLLM] | None = None,
    now: datetime | None = None,
) -> SwarmRunResult:
    """Run one preset pipeline. See spec for invariants."""

    # 1. Preset lookup (validation; no row, no event)
    try:
        preset = get_preset(preset_name)
    except KeyError:
        raise SwarmRunnerError(f"unknown_preset: {preset_name!r}") from None

    # 2. Params validation for phase5-review (only preset in v0)
    try:
        period_from_str = params["period_from"]
        period_to_str = params["period_to"]
    except KeyError as exc:
        raise SwarmRunnerError(
            f"invalid_params: missing field {exc.args[0]!r}"
        ) from None
    try:
        period_from = date.fromisoformat(str(period_from_str))
        period_to = date.fromisoformat(str(period_to_str))
    except ValueError as exc:
        raise SwarmRunnerError(f"invalid_params: {exc}") from None
    if period_from > period_to:
        raise SwarmRunnerError(
            f"invalid_params: period_from {period_from} > period_to {period_to}"
        )
    limit_trades = params.get("limit_trades")
    dry_run = bool(params.get("dry_run", False))
    force = bool(params.get("force", False))

    # 3. API key fail-fast
    settings = Settings()
    if not settings.anthropic_api_key:
        raise SwarmRunnerError("missing_api_key: ANTHROPIC_API_KEY not set")

    # 4. Run id and timing
    run_id = f"swr_{uuid4().hex[:12]}"
    started_at = now or datetime.now(_TPE)
    nodes = preset.nodes
    first_node = nodes[0]

    # 5. Emit run started + first node started
    await safe_emit(
        Event(
            event_type=EventType.SWARM_RUN_STARTED,
            agent=Agent.REVIEWER,
            payload={
                "run_id": run_id,
                "preset": preset_name,
                "nodes": list(nodes),
                "params": dict(params),
            },
        )
    )
    await safe_emit(
        Event(
            event_type=EventType.SWARM_NODE_STARTED,
            agent=Agent.REVIEWER,
            payload={"run_id": run_id, "preset": preset_name, "node": first_node},
        )
    )

    # 6. Run the wrapped pipeline
    try:
        review_result = run_review(
            period_from=period_from,
            period_to=period_to,
            db_conn=db_conn,
            out_dir=out_dir,
            proposals_dir=proposals_dir,
            market_data_loader=market_data_loader,
            cheatsheet_path=cheatsheet_path,
            llm_factory=llm_factory,
            force=force,
            limit_trades=limit_trades,
            dry_run=dry_run,
            now=now,
        )
    except Exception as exc:  # noqa: BLE001 — captured into failed row
        return await _handle_failure(
            exc=exc,
            run_id=run_id,
            preset_name=preset_name,
            preset_nodes=nodes,
            first_node=first_node,
            params=params,
            started_at=started_at,
            out_dir=out_dir,
            period_from=period_from,
            period_to=period_to,
            dry_run=dry_run,
            db_conn=db_conn,
        )

    # 7. Happy path: emit remaining node events
    return await _handle_success(
        review_result=review_result,
        run_id=run_id,
        preset_name=preset_name,
        preset_nodes=nodes,
        first_node=first_node,
        params=params,
        started_at=started_at,
        db_conn=db_conn,
    )


async def _handle_success(
    *,
    review_result: ReviewResult,
    run_id: str,
    preset_name: str,
    preset_nodes: list[str],
    first_node: str,
    params: dict[str, Any],
    started_at: datetime,
    db_conn: sqlite3.Connection,
) -> SwarmRunResult:
    # First node's completed (started was emitted before run_review)
    await safe_emit(
        Event(
            event_type=EventType.SWARM_NODE_COMPLETED,
            agent=Agent.REVIEWER,
            payload={
                "run_id": run_id,
                "preset": preset_name,
                "node": first_node,
                "elapsed_ms": 0,
            },
        )
    )
    # Remaining nodes: emit synthetic started + completed pairs
    for node in preset_nodes[1:]:
        await safe_emit(
            Event(
                event_type=EventType.SWARM_NODE_STARTED,
                agent=Agent.REVIEWER,
                payload={"run_id": run_id, "preset": preset_name, "node": node},
            )
        )
        await safe_emit(
            Event(
                event_type=EventType.SWARM_NODE_COMPLETED,
                agent=Agent.REVIEWER,
                payload={
                    "run_id": run_id,
                    "preset": preset_name,
                    "node": node,
                    "elapsed_ms": 0,
                },
            )
        )

    elapsed_ms = int((datetime.now(_TPE) - started_at).total_seconds() * 1000)
    node_outputs: dict[str, dict[str, Any]] = {
        "data_loader": {
            "trade_count": review_result.trade_count,
            "dry_run": review_result.dry_run,
        },
        "attributor": {"completed": True},
        "aggregator": {"completed": True},
        "critic": {"completed": True},
        "proposer": {
            "proposals_created": review_result.proposals_created,
            "files": list(review_result.proposals_files),
        },
    }
    result_payload: dict[str, Any] = {
        "review_id": review_result.review_id,
        "node_outputs": node_outputs,
        "trade_count": review_result.trade_count,
        "proposals_created": review_result.proposals_created,
        "total_cost_usd": review_result.total_cost_usd,
        "total_input_tokens": review_result.total_input_tokens,
        "total_output_tokens": review_result.total_output_tokens,
        "dry_run": review_result.dry_run,
    }
    insert_run(
        db_conn,
        SwarmRunRowDict(
            id=run_id,
            preset=preset_name,
            status="completed",
            params_json=json.dumps(params, ensure_ascii=False),
            result_json=json.dumps(result_payload, ensure_ascii=False),
            elapsed_ms=elapsed_ms,
            created_at=started_at.isoformat(timespec="seconds"),
        ),
    )
    await safe_emit(
        Event(
            event_type=EventType.SWARM_RUN_COMPLETED,
            agent=Agent.REVIEWER,
            payload={
                "run_id": run_id,
                "preset": preset_name,
                "elapsed_ms": elapsed_ms,
            },
        )
    )
    return SwarmRunResult(
        run_id=run_id,
        status="completed",
        preset=preset_name,
        params=dict(params),
        result=result_payload,
        elapsed_ms=elapsed_ms,
        created_at=started_at.isoformat(timespec="seconds"),
    )


async def _handle_failure(
    *,
    exc: BaseException,
    run_id: str,
    preset_name: str,
    preset_nodes: list[str],
    first_node: str,
    params: dict[str, Any],
    started_at: datetime,
    out_dir: Path,
    period_from: date,
    period_to: date,
    dry_run: bool,
    db_conn: sqlite3.Connection,
) -> SwarmRunResult:
    review_id = f"manual-{period_from.isoformat()}-to-{period_to.isoformat()}"
    review_dir = out_dir / review_id
    failed_node = _infer_failed_node(review_dir, preset_nodes, dry_run=dry_run)
    if failed_node in preset_nodes:
        completed_nodes = preset_nodes[: preset_nodes.index(failed_node)]
    else:
        completed_nodes = []

    # First node's completed (if first_node is among completed)
    if first_node in completed_nodes:
        await safe_emit(
            Event(
                event_type=EventType.SWARM_NODE_COMPLETED,
                agent=Agent.REVIEWER,
                payload={
                    "run_id": run_id,
                    "preset": preset_name,
                    "node": first_node,
                    "elapsed_ms": 0,
                },
            )
        )
    # Remaining completed nodes (if any beyond first)
    for node in completed_nodes:
        if node == first_node:
            continue
        await safe_emit(
            Event(
                event_type=EventType.SWARM_NODE_STARTED,
                agent=Agent.REVIEWER,
                payload={"run_id": run_id, "preset": preset_name, "node": node},
            )
        )
        await safe_emit(
            Event(
                event_type=EventType.SWARM_NODE_COMPLETED,
                agent=Agent.REVIEWER,
                payload={
                    "run_id": run_id,
                    "preset": preset_name,
                    "node": node,
                    "elapsed_ms": 0,
                },
            )
        )
    # Failed node started (only if not the first, since first was already emitted)
    if failed_node != first_node:
        await safe_emit(
            Event(
                event_type=EventType.SWARM_NODE_STARTED,
                agent=Agent.REVIEWER,
                payload={
                    "run_id": run_id,
                    "preset": preset_name,
                    "node": failed_node,
                },
            )
        )

    elapsed_ms = int((datetime.now(_TPE) - started_at).total_seconds() * 1000)
    error_payload = {"code": type(exc).__name__, "message": str(exc)}
    result_payload: dict[str, Any] = {
        "failed_node": failed_node,
        "completed_nodes": completed_nodes,
        "error": error_payload,
    }
    insert_run(
        db_conn,
        SwarmRunRowDict(
            id=run_id,
            preset=preset_name,
            status="failed",
            params_json=json.dumps(params, ensure_ascii=False),
            result_json=json.dumps(result_payload, ensure_ascii=False),
            elapsed_ms=elapsed_ms,
            created_at=started_at.isoformat(timespec="seconds"),
        ),
    )
    await safe_emit(
        Event(
            event_type=EventType.SWARM_RUN_FAILED,
            agent=Agent.REVIEWER,
            payload={
                "run_id": run_id,
                "preset": preset_name,
                "failed_node": failed_node,
                "error": error_payload,
            },
        )
    )
    return SwarmRunResult(
        run_id=run_id,
        status="failed",
        preset=preset_name,
        params=dict(params),
        result=result_payload,
        elapsed_ms=elapsed_ms,
        created_at=started_at.isoformat(timespec="seconds"),
    )


def _infer_failed_node(
    review_dir: Path, preset_nodes: list[str], *, dry_run: bool
) -> str:
    """Infer which node failed based on which expected files exist on disk.

    File ordering per ``post-trade-review-pipeline`` spec:
      data_loader → data.json
      attributor → attribution.json
      aggregator → metrics.json
      critic     → critique.md
      proposer   → report.md / proposals_created.md

    In dry-run mode no files are written, so default to the first node.
    """
    if dry_run or not review_dir.exists():
        return preset_nodes[0]
    file_for_node = {
        "data_loader": "data.json",
        "attributor": "attribution.json",
        "aggregator": "metrics.json",
        "critic": "critique.md",
        "proposer": "proposals_created.md",
    }
    for node in preset_nodes:
        fname = file_for_node.get(node)
        if fname is None:
            continue
        if not (review_dir / fname).exists():
            return node
    return preset_nodes[-1]


__all__ = ["SwarmRunResult", "SwarmRunnerError", "run_swarm"]
