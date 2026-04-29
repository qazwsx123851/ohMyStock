"""Tests for ohmystock.observability.cost_tracker.

Spec: openspec/changes/external-connectors-and-cost/specs/cost-tracking/spec.md
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from ohmystock.observability.cost_tracker import (
    MODEL_PRICING_USD_PER_MTOK,
    get_monthly_cost_usd,
    track_llm_cost,
)


@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "journal.db"
    monkeypatch.setenv("OHMYSTOCK_DB_PATH", str(db_path))
    return db_path


def _fake_message(model: str, input_tokens: int, output_tokens: int):
    return SimpleNamespace(
        model=model,
        usage=SimpleNamespace(
            input_tokens=input_tokens, output_tokens=output_tokens
        ),
    )


def test_pricing_table_has_three_models() -> None:
    for key in (
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ):
        assert key in MODEL_PRICING_USD_PER_MTOK
        assert "input" in MODEL_PRICING_USD_PER_MTOK[key]
        assert "output" in MODEL_PRICING_USD_PER_MTOK[key]


@pytest.mark.asyncio
async def test_haiku_cost_recorded(temp_db) -> None:
    @track_llm_cost(decision_id="dec_haiku_001")
    async def call():
        return _fake_message("claude-haiku-4-5-20251001", 100, 50)

    result = await call()
    assert result.model == "claude-haiku-4-5-20251001"

    conn = sqlite3.connect(str(temp_db))
    try:
        cur = conn.execute(
            "SELECT decision_id, model, input_tokens, output_tokens, cost_usd, created_at "
            "FROM llm_costs"
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    decision_id, model, input_tokens, output_tokens, cost_usd, created_at = rows[0]
    assert decision_id == "dec_haiku_001"
    assert model == "claude-haiku-4-5-20251001"
    assert input_tokens == 100
    assert output_tokens == 50
    expected = 100 * 1.0 / 1_000_000 + 50 * 5.0 / 1_000_000
    assert abs(cost_usd - expected) < 1e-12
    assert created_at.endswith("+08:00")


@pytest.mark.asyncio
async def test_opus_cost_recorded(temp_db) -> None:
    @track_llm_cost()
    async def call():
        return _fake_message("claude-opus-4-7", 1000, 500)

    await call()

    conn = sqlite3.connect(str(temp_db))
    try:
        cur = conn.execute("SELECT decision_id, cost_usd FROM llm_costs")
        rows = cur.fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    decision_id, cost_usd = rows[0]
    assert decision_id is None
    expected = 1000 * 15.0 / 1_000_000 + 500 * 75.0 / 1_000_000
    assert abs(cost_usd - expected) < 1e-12


@pytest.mark.asyncio
async def test_exception_does_not_record_but_propagates(temp_db) -> None:
    from ohmystock.journal.schema import init_schema

    conn = sqlite3.connect(str(temp_db))
    try:
        init_schema(conn)
    finally:
        conn.close()

    @track_llm_cost()
    async def call():
        raise RuntimeError("api error")

    with pytest.raises(RuntimeError, match="api error"):
        await call()

    conn = sqlite3.connect(str(temp_db))
    try:
        cur = conn.execute("SELECT COUNT(*) FROM llm_costs")
        (count,) = cur.fetchone()
    finally:
        conn.close()
    assert count == 0


@pytest.mark.asyncio
async def test_unknown_model_raises_value_error(temp_db) -> None:
    @track_llm_cost()
    async def call():
        return _fake_message("claude-future-99", 10, 10)

    with pytest.raises(ValueError, match="claude-future-99"):
        await call()


@pytest.mark.asyncio
async def test_get_monthly_cost_usd_aggregation(temp_db) -> None:
    from ohmystock.journal.schema import init_schema

    conn = sqlite3.connect(str(temp_db))
    try:
        init_schema(conn)
        rows = [
            (None, "claude-haiku-4-5-20251001", 0, 0, 0.01, "2026-04-01T10:00:00+08:00"),
            (None, "claude-haiku-4-5-20251001", 0, 0, 0.02, "2026-04-15T10:00:00+08:00"),
            (None, "claude-haiku-4-5-20251001", 0, 0, 0.03, "2026-04-29T10:00:00+08:00"),
            (None, "claude-haiku-4-5-20251001", 0, 0, 0.10, "2026-05-01T10:00:00+08:00"),
        ]
        with conn:
            conn.executemany(
                "INSERT INTO llm_costs"
                "(decision_id, model, input_tokens, output_tokens, cost_usd, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
    finally:
        conn.close()

    assert abs(get_monthly_cost_usd("2026-04") - 0.06) < 1e-9
    assert abs(get_monthly_cost_usd("2026-05") - 0.10) < 1e-9
    assert get_monthly_cost_usd("2026-03") == 0.0
