"""Tests for ohmystock.eventbus.types — EventType / Agent StrEnums."""

from __future__ import annotations

from ohmystock.eventbus.types import Agent, EventType


def test_event_type_has_all_16_canonical_strings() -> None:
    expected = {
        "screener_started",
        "screener_completed",
        "pattern_detected",
        "decider_thinking",
        "decision_made",
        "awaiting_confirm",
        "order_sent",
        "journal_written",
        "journal_queried",
        "review_node_started",
        "review_completed",
        "proposal_created",
        "wfa_started",
        "wfa_passed",
        "wfa_failed",
        "risk_off_triggered",
    }
    assert {m.value for m in EventType} == expected


def test_agent_has_all_9_canonical_strings() -> None:
    expected = {
        "scanner",
        "pattern_analyst",
        "decider",
        "trader",
        "librarian",
        "reviewer",
        "proposer",
        "validator",
        "guard",
    }
    assert {m.value for m in Agent} == expected


def test_event_type_member_equals_string_literal() -> None:
    e = EventType.DECISION_MADE
    assert e == "decision_made"
    assert isinstance(e, str)


def test_agent_member_equals_string_literal() -> None:
    a = Agent.DECIDER
    assert a == "decider"
    assert isinstance(a, str)
