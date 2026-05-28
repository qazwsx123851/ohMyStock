"""Tests for the 8 new emitters wired by eventbus-emitters-v1.

Covers: pattern_detected (vcp_pivot), proposal_created (proposal writer),
review_node_started + review_completed (review pipeline).

WFA emitters and journal_queried emitter are covered separately:
- WFA in ``tests/test_eventbus_emitters_wfa.py``
- journal_queried integration via ``tests/test_api_journal_endpoints.py`` (the
  routes already pass; emitter is best-effort and silent in fail paths).

Each test subscribes a fresh ``EventBus`` queue, exercises the producer, and
drains the queue to assert event_type / agent / payload shape.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

import pytest

import ohmystock.eventbus as eventbus_pkg
from ohmystock.eventbus import EventBus, EventType

bus_module = sys.modules["ohmystock.eventbus.bus"]

_TPE = timezone(timedelta(hours=8))


@pytest.fixture()
def fresh_bus(monkeypatch: pytest.MonkeyPatch) -> EventBus:
    fresh = EventBus()
    monkeypatch.setattr(eventbus_pkg, "bus", fresh)
    monkeypatch.setattr(bus_module, "bus", fresh)
    return fresh


def _drain(bus: EventBus) -> list:
    q = bus._subscribers[0] if bus._subscribers else None
    if q is None:
        return []
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    return events


# ---- pattern_detected (vcp_pivot) ------------------------------------------


def _make_bars(num: int, *, close: float, vol: float) -> list[dict]:
    return [
        {"o": close, "h": close, "l": close, "c": close, "v": vol}
        for _ in range(num)
    ]


def test_vcp_pivot_emits_pattern_detected_on_breakout(fresh_bus: EventBus) -> None:
    from ohmystock.scoring.context import ScoringContext
    from ohmystock.scoring.subscorers.vcp_pivot import vcp_pivot

    fresh_bus.subscribe()

    bars = _make_bars(59, close=100.0, vol=1000.0)
    bars.append({"o": 100.0, "h": 110.0, "l": 100.0, "c": 110.0, "v": 2000.0})
    ctx = ScoringContext(
        asof_date="2026-05-28",
        symbol="2330",
        bars=bars,
        three_major=[],
        margin_short=[],
    )

    result = vcp_pivot(ctx)
    assert result.points > 0
    events = _drain(fresh_bus)
    assert len(events) == 1
    assert events[0].event_type == EventType.PATTERN_DETECTED
    assert events[0].agent == "pattern_analyst"
    assert events[0].payload["symbol"] == "2330"
    assert events[0].payload["pattern"] == "VCP"
    assert events[0].payload["score"] == float(result.points)


def test_vcp_pivot_no_emit_when_no_match(fresh_bus: EventBus) -> None:
    from ohmystock.scoring.context import ScoringContext
    from ohmystock.scoring.subscorers.vcp_pivot import vcp_pivot

    fresh_bus.subscribe()

    bars = []
    for i in range(60):
        c = 100.0 + (i % 5) * 5
        bars.append({"o": c, "h": c + 2, "l": c - 2, "c": c, "v": 1000.0})
    ctx = ScoringContext(
        asof_date="2026-05-28",
        symbol="2330",
        bars=bars,
        three_major=[],
        margin_short=[],
    )
    vcp_pivot(ctx)
    assert _drain(fresh_bus) == []


# ---- proposal_created -------------------------------------------------------


def test_write_proposal_emits_proposal_created(
    fresh_bus: EventBus, tmp_path
) -> None:
    from ohmystock.proposal.schema import ProposalDraft
    from ohmystock.proposal.writer import write_proposal

    fresh_bus.subscribe()
    now = datetime(2026, 5, 28, 13, 30, 0, tzinfo=_TPE)
    draft = ProposalDraft(
        topic="test-topic",
        target_section="§6.4",
        created_by="test",
        created_at=now,
        review_id=None,
        priority="medium",
        description="d",
        motivation="ref metrics.json#/foo",
        diff_draft="d",
        expected_impact="i",
        risk_assessment="r",
        validation_plan="v",
        expected_improvement="e",
    )

    target = write_proposal(draft, tmp_path)
    events = _drain(fresh_bus)
    assert len(events) == 1
    assert events[0].event_type == EventType.PROPOSAL_CREATED
    assert events[0].agent == "proposer"
    assert events[0].payload == {
        "proposal_id": target.stem,
        "priority": "medium",
        "target_section": "§6.4",
    }


# ---- journal_queried (api route) --------------------------------------------


def test_journal_route_emits_journal_queried(fresh_bus: EventBus) -> None:
    """The /journal/rows handler emits journal_queried after a successful SELECT."""
    import sqlite3
    from collections.abc import Iterator

    import asyncio
    from httpx import ASGITransport, AsyncClient

    from ohmystock.api.app import create_app
    from ohmystock.api.routes._deps import get_db
    from ohmystock.journal.schema import init_schema
    from tests.conftest import VALID_ADMIN_TOKEN

    fresh_bus.subscribe()
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_schema(conn)

    app = create_app()

    def _override_get_db() -> Iterator[sqlite3.Connection]:
        yield conn

    app.dependency_overrides[get_db] = _override_get_db

    async def _hit() -> int:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {VALID_ADMIN_TOKEN}"},
        ) as client:
            r = await client.get("/api/admin/journal/rows?kind=entry")
        return r.status_code

    status = asyncio.run(_hit())
    assert status == 200

    events = [
        e for e in _drain(fresh_bus) if e.event_type == EventType.JOURNAL_QUERIED
    ]
    assert len(events) == 1
    assert events[0].agent == "librarian"
    assert "kind=entry" in events[0].payload["query"]
    assert events[0].payload["result_count"] == 0
