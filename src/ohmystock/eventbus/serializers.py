"""Event → JSON-shaped dict serializers.

AdminEventSerializer returns the full ``{event_id, timestamp, event_type,
agent, payload}`` shape used by ``/api/admin/events``. The masked /
public-facing serializer is a separate Phase 4.5 capability and not
implemented here.

The serializer does NOT JSON-encode — callers (e.g. the SSE stream) are
responsible for ``json.dumps``. Returning a dict keeps tests structural
and lets a future masked serializer share the same input shape.

Spec: openspec/specs/eventbus-emitters/spec.md §"AdminEventSerializer"
"""

from __future__ import annotations

from typing import Any

from ohmystock.eventbus.events import Event


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
