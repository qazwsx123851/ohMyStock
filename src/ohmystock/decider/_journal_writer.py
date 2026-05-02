"""SQLite write helpers for the decider orchestrator.

Three helpers, all parameterised on a caller-owned ``sqlite3.Connection``
(no I/O outside it). The caller (``orchestrator.decide_entry``) owns the
transaction boundary so it can roll back on failure.

Spec: openspec/changes/entry-decider-pm-node/specs/trade-journal-schema/spec.md
SSOT: docs/llm-decision-schema.md §4.1 / §4.3
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ohmystock.decider.models import DeciderOutput
from ohmystock.decider.node import LLMUsage
from ohmystock.swarm.models import EntryDecisionInput


_ENTRY_THESIS_MAX_CHARS = 500


def write_entry_pending_confirm(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    entry_input: EntryDecisionInput,
    raw: DeciderOutput,
    final: DeciderOutput,
    usage: LLMUsage,
    created_at: str,
) -> None:
    """Insert a ``kind=entry`` row in pending_confirm state.

    ``raw`` is the LLM's original output; ``final`` is the system-overridden
    output (for stage-3 sizing cap, or the same as raw if no override
    applied). ``proposed_sizing_pct`` is taken from ``raw`` (for traceability),
    ``final_sizing_pct`` is taken from ``final`` (so a stage-3 cap surfaces).
    ``stop_loss_price`` / ``atr_at_entry`` / ``risk_regime_at_entry`` are
    null until the next change wires Sizing/ATR/Risk Gate.
    """
    payload = {
        "llm_decision_id": raw.decision_id,
        "llm_model": usage.model,
        "llm_confidence": raw.confidence,
        "llm_reasoning": raw.reasoning,
        "entry_thesis": raw.reasoning[:_ENTRY_THESIS_MAX_CHARS],
        "cited_skills": list(raw.cited_skills),
        "must_have_check": [_must_have_dict(item) for item in raw.must_have_check],
        "bonus_score": raw.bonus_score,
        "bonus_breakdown": [_bonus_dict(item) for item in raw.bonus_breakdown],
        "proposed_sizing_pct": raw.proposed_sizing_pct,
        "final_sizing_pct": final.proposed_sizing_pct,
        "expected_holding_days": raw.expected_holding_days,
        "thesis_invalidation": list(raw.invalidation_conditions),
        "risk_flags": list(raw.risk_flags),
        "stage": raw.stage,
        "rs_percentile": raw.rs_percentile,
        "trend_template_passed": raw.trend_template_passed,
        "vcp_quality": raw.vcp_quality,
        "pivot_price": raw.pivot_price,
        "current_price": entry_input.candidate.current_price,
        "llm_input_tokens": usage.input_tokens,
        "llm_output_tokens": usage.output_tokens,
        "llm_cost_usd": usage.cost_usd,
        "decision_status": "pending_confirm",
        "stop_loss_price": None,
        "atr_at_entry": None,
        "risk_regime_at_entry": None,
        "auto_executed": False,
        "human_confirmed_by": None,
        "human_confirmed_at": None,
        "actual_entry_price": None,
        "actual_qty": None,
    }
    conn.execute(
        "INSERT INTO journal_entries"
        "(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'entry', ?, ?, ?)",
        (
            decision_id,
            entry_input.candidate.symbol,
            created_at,
            json.dumps(payload, ensure_ascii=False),
        ),
    )


def write_reject_llm(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    entry_input: EntryDecisionInput,
    raw: DeciderOutput | None,
    usage: LLMUsage | None,
    reject_reason: str,
    applied_overrides: list[str] | None = None,
    created_at: str,
) -> None:
    """Insert a ``kind=reject`` row with ``reject_layer='llm'``.

    ``raw=None`` and ``usage=None`` are accepted so the caller can record a
    JSON-parse-error reject before any structured output exists. In that
    case, ``llm_input_tokens`` / ``llm_output_tokens`` / ``llm_cost_usd`` are
    written as ``0`` and ``llm_confidence`` as ``None``.
    """
    payload: dict[str, Any] = {
        "decision_status": "rejected",
        "reject_layer": "llm",
        "reject_reason": reject_reason,
    }
    if applied_overrides:
        payload["applied_overrides"] = list(applied_overrides)

    if raw is not None:
        payload["llm_confidence"] = raw.confidence
    else:
        payload["llm_confidence"] = None

    if usage is not None:
        payload["llm_model"] = usage.model
        payload["llm_input_tokens"] = usage.input_tokens
        payload["llm_output_tokens"] = usage.output_tokens
        payload["llm_cost_usd"] = usage.cost_usd
    else:
        payload["llm_model"] = ""
        payload["llm_input_tokens"] = 0
        payload["llm_output_tokens"] = 0
        payload["llm_cost_usd"] = 0.0

    conn.execute(
        "INSERT INTO journal_entries"
        "(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, 'reject', ?, ?, ?)",
        (
            decision_id,
            entry_input.candidate.symbol,
            created_at,
            json.dumps(payload, ensure_ascii=False),
        ),
    )


def write_llm_cost(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    usage: LLMUsage | None,
    created_at: str,
) -> None:
    """Insert an ``llm_costs`` row.

    A ``None`` usage records ``input_tokens=0`` / ``output_tokens=0`` /
    ``cost_usd=0.0`` so a parse-error path still leaves a cost trail bound
    to the decision id.
    """
    if usage is None:
        model = ""
        input_tokens = 0
        output_tokens = 0
        cost_usd = 0.0
    else:
        model = usage.model
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cost_usd = usage.cost_usd

    conn.execute(
        "INSERT INTO llm_costs"
        "(decision_id, model, input_tokens, output_tokens, cost_usd, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (decision_id, model, input_tokens, output_tokens, cost_usd, created_at),
    )


def _must_have_dict(item: Any) -> dict[str, Any]:
    return {"name": item.name, "pass": item.pass_, "evidence": item.evidence}


def _bonus_dict(item: Any) -> dict[str, Any]:
    return {"name": item.name, "pass": item.pass_, "evidence": item.evidence}
