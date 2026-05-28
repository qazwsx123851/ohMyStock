"""Verify ``MaskedEventSerializer`` projection for the 5 swarm event_types.

Each event_type is fed a maximal payload (every conceivable field including
DENYLIST entries) and the output payload SHALL equal the documented whitelist
projection exactly.
"""

from __future__ import annotations

import pytest

from ohmystock.eventbus import (
    PUBLIC_WHITELIST,
    Event,
    MaskedEventSerializer,
    SymbolMaskTable,
)


@pytest.fixture
def serializer() -> MaskedEventSerializer:
    return MaskedEventSerializer(SymbolMaskTable({"2330": "半導體"}))


_SWARM_EVENT_TYPES = [
    "swarm_run_started",
    "swarm_run_completed",
    "swarm_run_failed",
    "swarm_node_started",
    "swarm_node_completed",
]


@pytest.mark.parametrize("event_type", _SWARM_EVENT_TYPES)
def test_swarm_event_payload_projects_to_whitelist(
    serializer: MaskedEventSerializer, event_type: str
) -> None:
    fat_payload = {
        "run_id": "swr_abcdef012345",
        "preset": "phase5-review",
        "nodes": ["data_loader", "attributor"],
        "node": "data_loader",
        "elapsed_ms": 1234,
        "params": {"symbol": "2330", "from": "2026-04-01"},
        "failed_node": "critic",
        "error": {"code": "llm_timeout", "message": "..."},
        "symbol": "2330",
        "price": 800.0,
        "company_name": "leak",
    }
    out = serializer.serialize(
        Event(event_type=event_type, agent="reviewer", payload=fat_payload)
    )
    whitelist = PUBLIC_WHITELIST[event_type]
    assert set(out["payload"].keys()) == whitelist
    for field in ("params", "failed_node", "error", "symbol", "price", "company_name"):
        assert field not in out["payload"], (
            f"{event_type} leaked {field!r} into public payload"
        )


def test_swarm_run_started_keeps_run_id_preset_nodes(
    serializer: MaskedEventSerializer,
) -> None:
    out = serializer.serialize(
        Event(
            event_type="swarm_run_started",
            agent="reviewer",
            payload={
                "run_id": "swr_x",
                "preset": "p",
                "nodes": ["a", "b"],
                "params": {"k": "v"},
            },
        )
    )
    assert out["payload"] == {"run_id": "swr_x", "preset": "p", "nodes": ["a", "b"]}


def test_swarm_node_completed_keeps_elapsed_ms(
    serializer: MaskedEventSerializer,
) -> None:
    out = serializer.serialize(
        Event(
            event_type="swarm_node_completed",
            agent="reviewer",
            payload={
                "run_id": "swr_x",
                "preset": "p",
                "node": "data_loader",
                "elapsed_ms": 42,
            },
        )
    )
    assert out["payload"] == {
        "run_id": "swr_x",
        "preset": "p",
        "node": "data_loader",
        "elapsed_ms": 42,
    }


def test_swarm_run_failed_drops_failed_node_and_error(
    serializer: MaskedEventSerializer,
) -> None:
    out = serializer.serialize(
        Event(
            event_type="swarm_run_failed",
            agent="reviewer",
            payload={
                "run_id": "swr_x",
                "preset": "p",
                "failed_node": "critic",
                "error": {"code": "llm_timeout", "message": "..."},
            },
        )
    )
    assert out["payload"] == {"run_id": "swr_x", "preset": "p"}
