"""Immutable Event payload for the EventBus pub/sub.

TPE is the Asia/Taipei UTC+8 timezone — all event timestamps are stamped
in TPE so downstream serializers can treat them uniformly without
per-event tz inference.

Spec: docs/backend-eventbus.md §2.2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

TPE = timezone(timedelta(hours=8))


@dataclass(frozen=True, slots=True)
class Event:
    event_type: str
    agent: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=lambda: datetime.now(TPE))
