"""Manual smoke for the public SSE channel — emit one synthetic event through
the real bus + MaskedEventSerializer + route generator and dump the masked
frame. Run with: ``uv run python scripts/smoke_public_events.py``

Not a pytest test — this is for ad-hoc verification during dev. The
equivalent assertion lives in
``tests/api/test_public_events_route.py::test_emit_decision_made_yields_masked_symbol_frame``.
"""

from __future__ import annotations

import asyncio
import json

from ohmystock.api.routes.public_events import (
    _public_event_stream,
    clear_mask_table,
    set_mask_table,
)
from ohmystock.eventbus import Event, SymbolMaskTable, bus


async def main() -> None:
    set_mask_table(SymbolMaskTable({"2330": "半導體"}))
    gen = _public_event_stream()
    try:
        msg_task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0)
        await bus.emit(
            Event(
                event_type="decision_made",
                agent="decider",
                payload={
                    "symbol": "2330",
                    "confidence": 0.72,
                    "action": "entry",
                    "reasoning": "2330 突破 20MA",
                },
            )
        )
        msg = await asyncio.wait_for(msg_task, timeout=2.0)
        body = json.loads(msg["data"])
        print("event_type:", body["event_type"])
        print("payload:", json.dumps(body["payload"], ensure_ascii=False))
        print("raw 2330 in frame text:", "2330" in msg["data"])
        print("raw symbol key in payload:", "symbol" in body["payload"])
        print("raw reasoning key in payload:", "reasoning" in body["payload"])
    finally:
        await gen.aclose()
        clear_mask_table()


if __name__ == "__main__":
    asyncio.run(main())
