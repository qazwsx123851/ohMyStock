"""Tests for AdminEventSerializer.serialize."""

from __future__ import annotations

from datetime import datetime

from ohmystock.eventbus.events import TPE, Event
from ohmystock.eventbus.serializers import AdminEventSerializer


def test_serialize_returns_5_canonical_keys() -> None:
    ev = Event(
        event_type="decision_made",
        agent="decider",
        payload={"symbol": "2330", "confidence": 0.72},
    )
    out = AdminEventSerializer.serialize(ev)
    assert set(out.keys()) == {"event_id", "timestamp", "event_type", "agent", "payload"}
    assert out["event_type"] == "decision_made"
    assert out["agent"] == "decider"
    assert out["payload"]["symbol"] == "2330"


def test_serialize_timestamp_has_tpe_offset_and_round_trips() -> None:
    ev = Event(event_type="decision_made", agent="decider")
    out = AdminEventSerializer.serialize(ev)
    assert isinstance(out["timestamp"], str)
    assert "+08:00" in out["timestamp"]
    parsed = datetime.fromisoformat(out["timestamp"])
    assert parsed.utcoffset() == TPE.utcoffset(None)


def test_serialize_does_not_mask_or_strip_payload() -> None:
    ev = Event(
        event_type="decision_made",
        agent="decider",
        payload={"symbol": "2330", "reasoning": "突破 20MA + 量能 1.5x"},
    )
    out = AdminEventSerializer.serialize(ev)
    assert out["payload"]["symbol"] == "2330"
    assert out["payload"]["reasoning"] == "突破 20MA + 量能 1.5x"
    assert "masked_symbol" not in out["payload"]


def test_serialize_payload_is_same_reference_no_deep_copy() -> None:
    payload = {"symbol": "2330"}
    ev = Event(event_type="decision_made", agent="decider", payload=payload)
    out = AdminEventSerializer.serialize(ev)
    assert out["payload"] is payload


def test_serialize_event_id_passes_through() -> None:
    ev = Event(event_type="decision_made", agent="decider")
    out = AdminEventSerializer.serialize(ev)
    assert out["event_id"] == ev.event_id
    assert out["event_id"].startswith("evt_")
