"""Shared fixtures for tests/review/.

Provides an in-memory sqlite DB pre-loaded with ``journal_entries`` schema
plus helpers that insert synthetic ``entry`` / ``exit`` / ``reject`` /
``expire`` rows so individual node tests stay short.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest

from ohmystock.journal.schema import init_schema


@pytest.fixture()
def journal_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")
    try:
        init_schema(conn)
        yield conn
    finally:
        conn.close()


def insert_entry(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    symbol: str,
    created_at: str,
    actual_entry_price: float = 100.0,
    cited_skills: list[str] | None = None,
    entry_thesis: str = "synthetic thesis",
    llm_confidence: float = 0.75,
    risk_flags: list[str] | None = None,
    sector: str | None = "半導體",
    extra: dict | None = None,
) -> None:
    payload = {
        "actual_entry_price": actual_entry_price,
        "actual_qty": 1,
        "cited_skills": cited_skills or ["technical/breakout"],
        "entry_thesis": entry_thesis,
        "llm_reasoning": entry_thesis,
        "llm_confidence": llm_confidence,
        "risk_flags": risk_flags or [],
        "sector": sector,
        "decision_status": "closed",
    }
    if extra:
        payload.update(extra)
    conn.execute(
        "INSERT INTO journal_entries (decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        (decision_id, symbol, created_at, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()


def insert_exit(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    symbol: str,
    created_at: str,
    actual_exit_price: float = 106.0,
    exit_tag: str = "hit_t1",
    pnl_pct: float = 6.0,
    hold_days: int = 5,
) -> None:
    payload = {
        "exit_tag": exit_tag,
        "exit_reason": f"synthetic {exit_tag}",
        "actual_exit_price": actual_exit_price,
        "pnl_pct": pnl_pct,
        "hold_days": hold_days,
        "exited_at": created_at,
        "close_price_evaluated": actual_exit_price,
    }
    conn.execute(
        "INSERT INTO journal_entries (decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'exit', ?, ?, ?)",
        (decision_id, symbol, created_at, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()


def insert_reject(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    symbol: str,
    created_at: str,
    reject_layer: str = "llm",
    reject_reason: str = "confidence < 0.6",
) -> None:
    payload = {
        "decision_status": "rejected",
        "reject_layer": reject_layer,
        "reject_reason": reject_reason,
    }
    conn.execute(
        "INSERT INTO journal_entries (decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'reject', ?, ?, ?)",
        (decision_id, symbol, created_at, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()


def insert_expire(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    symbol: str,
    created_at: str,
    expire_reason: str = "confirm timeout after 30 minutes",
) -> None:
    payload = {
        "decision_status": "expired",
        "expire_reason": expire_reason,
        "expired_at": created_at,
    }
    conn.execute(
        "INSERT INTO journal_entries (decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'expire', ?, ?, ?)",
        (decision_id, symbol, created_at, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()


class StaticMarketData:
    """Test double for ``MarketDataLoader``.

    ``responses`` maps ``(symbol, exit_date_iso)`` to a list of close
    prices. Missing keys return ``[]`` so callers can simulate
    ``data_missing=true``.
    """

    def __init__(self, responses: dict[tuple[str, str], list[float]] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, str, int]] = []

    def select_bars(
        self, symbol: str, exit_date: date, days: int
    ) -> list[float]:
        self.calls.append((symbol, exit_date.isoformat(), days))
        return list(self.responses.get((symbol, exit_date.isoformat()), [])[:days])
