"""Tests for the WFA validator emitters: wfa_started / wfa_passed / wfa_failed.

Reuses the synthetic-loader pattern from ``tests/validation/test_wfa.py`` so
the validator's full code path runs without network or strategy mocking.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import ohmystock.eventbus as eventbus_pkg
from ohmystock.data.sources.base import BarRow
from ohmystock.eventbus import EventBus, EventType
from ohmystock.validation import WfaValidationError, run_validation
from ohmystock.validation import wfa as wfa_module

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


def _synthetic_bars(n_days: int, base_price: float) -> list[BarRow]:
    rows: list[BarRow] = []
    current = date(2025, 1, 2)
    i = 0
    while len(rows) < n_days:
        if current.weekday() < 5:
            price = base_price + i * 0.5
            rows.append(
                BarRow(
                    ts=current.isoformat(),
                    o=price,
                    h=price,
                    l=price,
                    c=price,
                    v=1000,
                )
            )
            i += 1
        current = current.fromordinal(current.toordinal() + 1)
    return rows


def _make_validating_proposal(tmp_path: Path) -> Path:
    from ohmystock.proposal import (
        ProposalDraft,
        transition_proposal,
        write_proposal,
    )

    now = datetime(2026, 5, 28, tzinfo=_TPE)
    draft = ProposalDraft(
        topic="vcp-volume-threshold",
        target_section="§6.4",
        created_by="test",
        created_at=now,
        review_id=None,
        priority="high",
        description="d",
        motivation="ref metrics.json#/foo",
        diff_draft="d",
        expected_impact="i",
        risk_assessment="r",
        validation_plan="v",
        expected_improvement="e",
    )
    pending_path = write_proposal(draft, tmp_path)
    return transition_proposal(
        pending_path, new_status="validating", actor="test"
    )


def test_wfa_pass_emits_started_then_passed(
    fresh_bus: EventBus, tmp_path: Path
) -> None:
    fresh_bus.subscribe()
    proposal_path = _make_validating_proposal(tmp_path)
    bars = _synthetic_bars(253, 100.0)

    def loader(symbol: str, period_from: str, period_to: str) -> list[BarRow]:
        del symbol, period_from, period_to
        return bars

    report = run_validation(
        proposal_path,
        strategy_name="sma_cross",
        period={"from": "2025-01-02", "to": "2025-12-30"},
        param_overrides={"fast": 10},
        universe=["2330"],
        wfa_windows=5,
        in_sample_ratio=0.7,
        initial_capital=1_000_000,
        market_data_loader=loader,
    )
    assert report.verdict == "pass"

    events = [
        e
        for e in _drain(fresh_bus)
        if e.event_type
        in (EventType.WFA_STARTED, EventType.WFA_PASSED, EventType.WFA_FAILED)
    ]
    types = [e.event_type for e in events]
    assert types == [EventType.WFA_STARTED, EventType.WFA_PASSED]
    pid = events[0].payload["proposal_id"]
    assert pid == events[1].payload["proposal_id"]
    assert events[0].agent == "validator"


def test_wfa_fail_emits_started_then_failed(
    fresh_bus: EventBus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_bus.subscribe()
    proposal_path = _make_validating_proposal(tmp_path)
    bars = _synthetic_bars(253, 100.0)

    def loader(symbol: str, period_from: str, period_to: str) -> list[BarRow]:
        del symbol, period_from, period_to
        return bars

    call_state = {"i": 0}

    def fake_run_one(
        strategy: Any, _bars: Any, _period: Any, _capital: Any
    ) -> dict[str, float]:
        del strategy
        idx = call_state["i"] % 4
        call_state["i"] += 1
        if idx == 0:
            return {"sharpe": 1.0, "max_drawdown": -0.05, "win_rate": 0.5}
        if idx == 1:
            return {"sharpe": 1.0, "max_drawdown": -0.05, "win_rate": 0.5}
        if idx == 2:
            return {"sharpe": 2.0, "max_drawdown": -0.05, "win_rate": 0.5}
        return {"sharpe": 0.5, "max_drawdown": -0.05, "win_rate": 0.5}

    monkeypatch.setattr(wfa_module, "_run_one", fake_run_one)

    report = run_validation(
        proposal_path,
        strategy_name="sma_cross",
        period={"from": "2025-01-02", "to": "2025-12-30"},
        param_overrides={"fast": 10},
        universe=["2330"],
        wfa_windows=5,
        in_sample_ratio=0.7,
        initial_capital=1_000_000,
        market_data_loader=loader,
    )
    assert report.verdict == "fail"

    events = [
        e
        for e in _drain(fresh_bus)
        if e.event_type
        in (EventType.WFA_STARTED, EventType.WFA_PASSED, EventType.WFA_FAILED)
    ]
    types = [e.event_type for e in events]
    assert types == [EventType.WFA_STARTED, EventType.WFA_FAILED]
    assert "sharpe_gap" in events[1].payload["failure_reason"]


def test_wfa_empty_universe_emits_nothing(
    fresh_bus: EventBus, tmp_path: Path
) -> None:
    fresh_bus.subscribe()
    proposal_path = _make_validating_proposal(tmp_path)

    with pytest.raises(WfaValidationError):
        run_validation(
            proposal_path,
            strategy_name="sma_cross",
            period={"from": "2025-01-02", "to": "2025-12-30"},
            param_overrides={"fast": 10},
            universe=[],
            initial_capital=1_000_000,
            market_data_loader=lambda *a, **kw: [],
        )
    events = [
        e
        for e in _drain(fresh_bus)
        if e.event_type
        in (EventType.WFA_STARTED, EventType.WFA_PASSED, EventType.WFA_FAILED)
    ]
    assert events == []
