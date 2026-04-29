"""LLM cost tracking decorator + monthly aggregation helper.

Spec: openspec/changes/external-connectors-and-cost/specs/cost-tracking/spec.md

- ``track_llm_cost(decision_id=None)`` — async decorator that records token
  usage from an Anthropic ``Message`` return value into ``llm_costs``.
- ``get_monthly_cost_usd(year_month)`` — sum cost_usd for a YYYY-MM prefix.
- ``MODEL_PRICING_USD_PER_MTOK`` — hardcoded pricing table (USD per million
  tokens) for the three production models.

Avoids importing from ``ohmystock.api`` (per Phase 0d constraint); opens its
own SQLite connection via ``Settings.ohmystock_db_path``.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Awaitable, Callable

from ohmystock.config import Settings
from ohmystock.journal.schema import init_schema

MODEL_PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
}

_TPE_TZ = timezone(timedelta(hours=8))


def _open_db() -> sqlite3.Connection:
    path = Path(Settings().ohmystock_db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    return conn


def _calculate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING_USD_PER_MTOK.get(model)
    if pricing is None:
        raise ValueError(
            f"unknown model {model!r} not in MODEL_PRICING_USD_PER_MTOK"
        )
    return (
        input_tokens * pricing["input"] / 1_000_000.0
        + output_tokens * pricing["output"] / 1_000_000.0
    )


def track_llm_cost(
    decision_id: str | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    def decorator(
        func: Callable[..., Awaitable[Any]],
    ) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await func(*args, **kwargs)
            model = result.model
            input_tokens = result.usage.input_tokens
            output_tokens = result.usage.output_tokens
            cost = _calculate_cost_usd(model, input_tokens, output_tokens)
            created_at = datetime.now(_TPE_TZ).isoformat(timespec="seconds")
            conn = _open_db()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO llm_costs"
                        "(decision_id, model, input_tokens, output_tokens, cost_usd, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            decision_id,
                            model,
                            input_tokens,
                            output_tokens,
                            cost,
                            created_at,
                        ),
                    )
            finally:
                conn.close()
            return result

        return wrapper

    return decorator


def get_monthly_cost_usd(year_month: str) -> float:
    conn = _open_db()
    try:
        cur = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM llm_costs WHERE created_at LIKE ?",
            (f"{year_month}%",),
        )
        row = cur.fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0
    finally:
        conn.close()
