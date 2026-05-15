"""Tests for ``MaskedEventSerializer`` — public SSE channel mask contract.

The parametric DENYLIST test is the legal-compliance surface for SITC mask
guarantees (see ``docs/auth-and-mask.md`` §3.1 and §4.1). It feeds a "fat"
payload containing every DENYLIST field plus every legal whitelisted field
through the serializer for every documented ``event_type`` and asserts no
DENYLIST field survives.

Spec: openspec/changes/web-public-shell-and-mask/specs/eventbus-public-mask/spec.md
"""

from __future__ import annotations

import pytest

from ohmystock.eventbus import (
    DENYLIST_FIELDS,
    PUBLIC_WHITELIST,
    AdminEventSerializer,
    Event,
    MaskedEventSerializer,
    SymbolMaskTable,
)
from ohmystock.eventbus.serializers import TWSE_CODE_RE


@pytest.fixture
def mask_table() -> SymbolMaskTable:
    return SymbolMaskTable({"2330": "半導體", "2317": "電子零組件"})


@pytest.fixture
def serializer(mask_table: SymbolMaskTable) -> MaskedEventSerializer:
    return MaskedEventSerializer(mask_table)


# ---- Whitelist behaviour ----------------------------------------------------


def test_whitelisted_field_passes_through(serializer: MaskedEventSerializer) -> None:
    event = Event(
        event_type="decider_thinking",
        agent="decider",
        payload={"symbol": "2330", "confidence_so_far": 0.5},
    )
    out = serializer.serialize(event)["payload"]
    assert out["confidence_so_far"] == 0.5


def test_unknown_event_type_yields_empty_payload(
    serializer: MaskedEventSerializer,
) -> None:
    event = Event(
        event_type="not_in_whitelist",
        agent="x",
        payload={"anything": "here", "symbol": "2330"},
    )
    out = serializer.serialize(event)["payload"]
    assert out == {}


# ---- DENYLIST belt-and-suspenders ------------------------------------------


_FAT_PAYLOAD: dict[str, object] = {
    # Every DENYLIST field (synthetic placeholder values).
    "symbol": "2330",
    "company_name": "TSMC",
    "price": 800.0,
    "expected_price": 798.0,
    "quantity": 1000,
    "pnl_twd": 50000,
    "account_id": "F123456789",
    "api_key": "secret",
    "broker_order_id": "BRK-001",
    "reasoning": "2330 突破 20MA",
    "query": "VCP 2330",
    "symbols": ["2330", "2317"],
    "failure_reason": "WFA Sharpe < 0",
    # Every legal whitelist field across all 16 event types.
    "universe_size": 1700,
    "candidate_count": 12,
    "pattern": "VCP",
    "score": 0.8,
    "confidence_so_far": 0.5,
    "confidence": 0.72,
    "action": "entry",
    "timeout_at": "2026-04-27T14:00:00+08:00",
    "journal_kind": "entry",
    "result_count": 5,
    "review_id": "2026-04",
    "node_name": "data_loader",
    "node_index": 1,
    "proposals_created_count": 3,
    "proposal_id": "p001",
    "priority": "high",
    "target_section": "§6.4",
    "reason_category": "monthly_drawdown",
    "severity": "halt",
    # Synthesised fields (whitelist would normally fill these from input).
    "masked_symbol": "STK-PRE-EXISTING",
    "industry_hint": "industry-pre-existing",
    "reasoning_summary": "pre-existing",
}


@pytest.mark.parametrize("event_type", sorted(PUBLIC_WHITELIST.keys()))
def test_no_denylist_field_leaks_in_any_whitelisted_event(
    serializer: MaskedEventSerializer, event_type: str
) -> None:
    event = Event(event_type=event_type, agent="test", payload=dict(_FAT_PAYLOAD))
    out = serializer.serialize(event)["payload"]
    leaked = DENYLIST_FIELDS & out.keys()
    assert not leaked, f"{event_type} leaked DENYLIST fields: {leaked}"


@pytest.mark.parametrize("event_type", sorted(PUBLIC_WHITELIST.keys()))
def test_reasoning_summary_never_contains_raw_4digit_code(
    serializer: MaskedEventSerializer, event_type: str
) -> None:
    """The hot leak path: ``reasoning`` text containing real TWSE codes must
    be transformed into ``reasoning_summary`` with codes stripped. Other
    whitelisted fields (``review_id``, ``timeout_at``, ...) legitimately
    contain year-shaped digits; we don't penalize them.
    """
    event = Event(event_type=event_type, agent="test", payload=dict(_FAT_PAYLOAD))
    out = serializer.serialize(event)["payload"]
    summary = out.get("reasoning_summary")
    if summary is None:
        return
    assert not TWSE_CODE_RE.search(summary), (
        f"{event_type}: reasoning_summary contains a 4-digit code: {summary!r}"
    )


def test_contrived_whitelist_with_denylist_field_still_pops_it() -> None:
    """If a future change accidentally allows 'symbol' in a whitelist,
    DENYLIST_FIELDS post-pass MUST still remove it."""
    table = SymbolMaskTable({})
    serializer = MaskedEventSerializer(table)
    original = PUBLIC_WHITELIST.get("test_contrived")
    PUBLIC_WHITELIST["test_contrived"] = {"symbol", "confidence"}
    try:
        event = Event(
            event_type="test_contrived",
            agent="test",
            payload={"symbol": "2330", "confidence": 0.5},
        )
        out = serializer.serialize(event)["payload"]
        assert "symbol" not in out
        assert out.get("confidence") == 0.5
    finally:
        if original is None:
            PUBLIC_WHITELIST.pop("test_contrived", None)
        else:
            PUBLIC_WHITELIST["test_contrived"] = original


# ---- symbol → masked_symbol + industry_hint --------------------------------


def test_decision_made_swaps_symbol_for_masked_label(
    serializer: MaskedEventSerializer,
) -> None:
    event = Event(
        event_type="decision_made",
        agent="decider",
        payload={
            "symbol": "2330",
            "confidence": 0.72,
            "action": "entry",
            "reasoning": "突破 20MA + 量能",  # no 4-digit code
        },
    )
    out = serializer.serialize(event)["payload"]
    assert out["masked_symbol"] == "STK-A"
    assert out["industry_hint"] == "半導體"
    assert out["confidence"] == 0.72
    assert out["action"] == "entry"
    assert "symbol" not in out
    assert "reasoning" not in out


def test_industry_hint_falls_through_to_other(
    mask_table: SymbolMaskTable,
) -> None:
    serializer = MaskedEventSerializer(mask_table)
    event = Event(
        event_type="decision_made",
        agent="decider",
        payload={"symbol": "9999", "confidence": 0.5, "action": "skip"},
    )
    out = serializer.serialize(event)["payload"]
    assert out["industry_hint"] == "其他"


# ---- reasoning → reasoning_summary ----------------------------------------


def test_real_twse_code_in_reasoning_is_stripped(
    serializer: MaskedEventSerializer,
) -> None:
    event = Event(
        event_type="decision_made",
        agent="decider",
        payload={
            "symbol": "2330",
            "confidence": 0.72,
            "action": "entry",
            "reasoning": "2330 突破 20MA + 量能 1.5x",
        },
    )
    out = serializer.serialize(event)["payload"]
    assert out["reasoning_summary"] == "STK-? 突破 20MA + 量能 1.5x"
    assert "2330" not in out["reasoning_summary"]


def test_year_like_4digit_is_also_stripped_documented_false_positive(
    serializer: MaskedEventSerializer,
) -> None:
    event = Event(
        event_type="decision_made",
        agent="decider",
        payload={
            "symbol": "2330",
            "confidence": 0.72,
            "action": "entry",
            "reasoning": "since 2026 the trend has held",
        },
    )
    out = serializer.serialize(event)["payload"]
    assert out["reasoning_summary"] == "since STK-? the trend has held"


def test_non_4digit_numbers_are_left_alone(
    serializer: MaskedEventSerializer,
) -> None:
    event = Event(
        event_type="decision_made",
        agent="decider",
        payload={
            "symbol": "2330",
            "confidence": 0.72,
            "action": "entry",
            "reasoning": "突破 20MA + 100 萬成交量 + 5MA",
        },
    )
    out = serializer.serialize(event)["payload"]
    assert out["reasoning_summary"] == "突破 20MA + 100 萬成交量 + 5MA"


# ---- Envelope shape ---------------------------------------------------------


def test_envelope_shape_matches_admin_serializer(
    serializer: MaskedEventSerializer,
) -> None:
    event = Event(
        event_type="decision_made",
        agent="decider",
        payload={"symbol": "2330", "confidence": 0.5, "action": "entry"},
    )
    admin_out = AdminEventSerializer.serialize(event)
    public_out = serializer.serialize(event)
    assert set(admin_out.keys()) == set(public_out.keys()) == {
        "event_id", "timestamp", "event_type", "agent", "payload",
    }
    for k in ("event_id", "timestamp", "event_type", "agent"):
        assert admin_out[k] == public_out[k]
