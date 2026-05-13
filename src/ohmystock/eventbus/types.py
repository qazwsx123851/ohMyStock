"""Canonical event_type and agent string constants.

EventType holds the 16 event_type strings defined in
docs/backend-eventbus.md §3.2. Agent holds the 9 agent strings used as the
``Event.agent`` field. Both are StrEnum so members compare equal to their
string values (``EventType.DECISION_MADE == "decision_made"``).

Emitters MUST reference these constants instead of inlining string literals.

Spec: openspec/specs/eventbus-emitters/spec.md
"""

from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
    SCREENER_STARTED = "screener_started"
    SCREENER_COMPLETED = "screener_completed"
    PATTERN_DETECTED = "pattern_detected"
    DECIDER_THINKING = "decider_thinking"
    DECISION_MADE = "decision_made"
    AWAITING_CONFIRM = "awaiting_confirm"
    ORDER_SENT = "order_sent"
    JOURNAL_WRITTEN = "journal_written"
    JOURNAL_QUERIED = "journal_queried"
    REVIEW_NODE_STARTED = "review_node_started"
    REVIEW_COMPLETED = "review_completed"
    PROPOSAL_CREATED = "proposal_created"
    WFA_STARTED = "wfa_started"
    WFA_PASSED = "wfa_passed"
    WFA_FAILED = "wfa_failed"
    RISK_OFF_TRIGGERED = "risk_off_triggered"
    SWARM_RUN_STARTED = "swarm_run_started"
    SWARM_RUN_COMPLETED = "swarm_run_completed"
    SWARM_RUN_FAILED = "swarm_run_failed"
    SWARM_NODE_STARTED = "swarm_node_started"
    SWARM_NODE_COMPLETED = "swarm_node_completed"


class Agent(StrEnum):
    SCANNER = "scanner"
    PATTERN_ANALYST = "pattern_analyst"
    DECIDER = "decider"
    TRADER = "trader"
    LIBRARIAN = "librarian"
    REVIEWER = "reviewer"
    PROPOSER = "proposer"
    VALIDATOR = "validator"
    GUARD = "guard"
