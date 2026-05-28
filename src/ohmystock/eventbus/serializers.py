"""Event → JSON-shaped dict serializers.

Two serializers, one envelope shape:

* ``AdminEventSerializer`` — full payload pass-through for ``/api/admin/events``.
* ``MaskedEventSerializer`` — public-channel whitelist + DENYLIST + symbol mask
  for ``/api/public/events``.

Both return the same top-level shape (``event_id``, ``timestamp``, ``event_type``,
``agent``, ``payload``); only ``payload`` differs. Neither JSON-encodes — callers
are responsible for ``json.dumps``.

Spec: openspec/specs/eventbus-emitters/spec.md §"AdminEventSerializer"
      openspec/changes/web-public-shell-and-mask/specs/eventbus-public-mask/spec.md
"""

from __future__ import annotations

import re
from typing import Any

from ohmystock.eventbus.events import Event
from ohmystock.eventbus.mask_table import SymbolMaskTable


class AdminEventSerializer:
    @staticmethod
    def serialize(event: Event) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type,
            "agent": event.agent,
            "payload": event.payload,
        }


# Per-event_type whitelist of payload fields that MAY cross the public boundary.
# Spec source of truth: docs/backend-eventbus.md §4.2 PUBLIC_WHITELIST.
PUBLIC_WHITELIST: dict[str, set[str]] = {
    "screener_started":    {"universe_size"},
    "screener_completed":  {"candidate_count"},
    "pattern_detected":    {"masked_symbol", "industry_hint", "pattern", "score"},
    "decider_thinking":    {"masked_symbol", "industry_hint", "confidence_so_far"},
    "decision_made":       {
        "masked_symbol", "industry_hint", "confidence",
        "reasoning_summary", "action",
    },
    "awaiting_confirm":    {"masked_symbol", "industry_hint", "timeout_at"},
    "order_sent":          {"masked_symbol", "industry_hint"},
    "journal_written":     {"journal_kind", "masked_symbol"},
    "journal_queried":     {"result_count"},
    "review_node_started": {"review_id", "node_name", "node_index"},
    "review_completed":    {"review_id", "proposals_created_count"},
    "proposal_created":    {"proposal_id", "priority", "target_section"},
    "wfa_started":         {"proposal_id"},
    "wfa_passed":          {"proposal_id"},
    "wfa_failed":          {"proposal_id"},  # NOT failure_reason — leaks strategy
    "risk_off_triggered":  {"reason_category", "severity"},
    "swarm_run_started":   {"run_id", "preset", "nodes"},
    "swarm_run_completed": {"run_id", "preset", "elapsed_ms"},
    "swarm_run_failed":    {"run_id", "preset"},
    "swarm_node_started":  {"run_id", "preset", "node"},
    "swarm_node_completed": {"run_id", "preset", "node", "elapsed_ms"},
}

# Hard fail-safe: anything in this set is popped from the public payload AFTER
# the whitelist pass, even if some future change accidentally lists it.
DENYLIST_FIELDS: frozenset[str] = frozenset({
    "symbol",
    "company_name",
    "price",
    "expected_price",
    "quantity",
    "pnl_twd",
    "account_id",
    "api_key",
    "broker_order_id",
    "reasoning",  # original LLM text; may contain real 4-digit codes
    "query",      # FTS5 query string; may contain real symbols
    "symbols",    # screener result list; only candidate_count is public
    "failure_reason",
})

# 4-digit TWSE code regex. ``\b`` ensures it matches whole-token codes only
# (still matches years like "2026" by design — false positives are acceptable
# noise, false negatives are a compliance failure).
TWSE_CODE_RE = re.compile(r"\b\d{4}\b")
_REASONING_REPLACEMENT = "STK-?"


class MaskedEventSerializer:
    def __init__(self, mask_table: SymbolMaskTable) -> None:
        self._mask_table = mask_table

    def serialize(self, event: Event) -> dict[str, Any]:
        whitelist = PUBLIC_WHITELIST.get(event.event_type, set())
        payload = event.payload
        out: dict[str, Any] = {}

        # 1. symbol → masked_symbol (and industry_hint) if whitelisted.
        symbol = payload.get("symbol")
        if symbol is not None and "masked_symbol" in whitelist:
            out["masked_symbol"] = self._mask_table.mask(symbol)
            if "industry_hint" in whitelist:
                out["industry_hint"] = self._mask_table.industry_of(symbol)

        # 2. reasoning → reasoning_summary with 4-digit-code strip.
        reasoning = payload.get("reasoning")
        if isinstance(reasoning, str) and "reasoning_summary" in whitelist:
            out["reasoning_summary"] = TWSE_CODE_RE.sub(
                _REASONING_REPLACEMENT, reasoning
            )

        # 3. Direct pass-through for everything else in the whitelist.
        for key in whitelist:
            if key in ("masked_symbol", "industry_hint", "reasoning_summary"):
                continue
            if key in payload:
                out[key] = payload[key]

        # 4. Belt-and-suspenders: pop any DENYLIST field even if a future
        #    whitelist accidentally allowed it.
        for forbidden in DENYLIST_FIELDS:
            out.pop(forbidden, None)

        return {
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type,
            "agent": event.agent,
            "payload": out,
        }
