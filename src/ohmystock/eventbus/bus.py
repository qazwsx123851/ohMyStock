"""EventBus — asyncio Queue pub/sub for backend events.

Each subscriber gets a bounded asyncio.Queue (maxsize=1024). emit() fans out
non-blocking via put_nowait; on QueueFull (slow consumer), the event is silently
dropped for that subscriber to keep the producer healthy. The dropped-event
visibility / metric lands in a later change.

Spec: docs/backend-eventbus.md §2.2
"""

from __future__ import annotations

from asyncio import Queue, QueueFull

from ohmystock.eventbus.events import Event


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Queue[Event]] = []

    def subscribe(self) -> Queue[Event]:
        q: Queue[Event] = Queue(maxsize=1024)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: Queue[Event]) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def emit(self, event: Event) -> None:
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except QueueFull:
                pass


bus = EventBus()
