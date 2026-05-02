## Context

The `EventBus` class at `src/ohmystock/eventbus/bus.py` and its `Event` dataclass at `src/ohmystock/eventbus/events.py` were shipped by `fastapi-bootstrap` (archived as `2026-04-28-fastapi-bootstrap`). It is a single-process asyncio pub/sub: `subscribe()` returns a `maxsize=1024` Queue, `unsubscribe(q)` removes it, `emit(event)` fans out non-blocking via `put_nowait` and silently drops on `QueueFull`. The module-level singleton `bus` is the only instance.

`ohmystock.api.app.create_app()` registers `/healthz` and `/api/admin/events`. The latter currently uses `_admin_event_stream` which sleeps 15 s and yields `event: heartbeat` indefinitely — it never calls `bus.subscribe()`.

Five services have shipped without emitting: `ohmystock.screener`, `ohmystock.decider.orchestrator`, `ohmystock.safety.confirm_gate`, `ohmystock.exit_engine.evaluator`, `ohmystock.safety.auto_execute`. The journal writer (`ohmystock.journal`) sits underneath all four trade-side services and is the natural cross-cutting emit point for `journal_written`.

`docs/backend-eventbus.md` §3.2 defines 14 canonical `event_type` strings; §3.3 defines the admin JSON shape; §4.1 sketches the AdminEventSerializer. Phases 4 and 4.5 will layer auth and a masked serializer on top of what this change ships.

## Goals / Non-Goals

**Goals:**
- Define the canonical `event_type` registry as Python constants so emitters and tests cannot diverge from the spec.
- Wire the 9 emit points listed in the proposal into already-shipped services with **zero behavioural change** to the producer's primary write/return path on bus failure.
- Replace `/api/admin/events` heartbeat with a real bus subscriber that yields events as SSE in admin JSON shape, with a comment-frame keepalive every 15 s for proxy compatibility.
- Cover each emit with unit tests that prove (a) absence-tolerance (no subscriber → no error), (b) shape correctness with a subscriber attached, (c) failure-tolerance (`emit` raising → service still succeeds).
- One end-to-end integration test: call `confirm()` while a `TestClient` SSE consumer is attached, observe the expected event sequence.

**Non-Goals:**
- Bearer auth on `/api/admin/events` (deferred to Phase 4 dedicated change `web-admin-bearer-auth`).
- Public/masked serializer or `/api/public/events` endpoint (Phase 4.5).
- Persistent event log / replay buffer / "events since last connect" (deferred — admin SSE is live-only for v0).
- New `event_type` strings beyond the 14 in `docs/backend-eventbus.md` §3.2.
- Wiring `pattern_detected`, `review_*`, `proposal_created`, `wfa_*`, `journal_queried` (their producers are not yet built).
- Persistence guarantees: events lost during disconnect or queue overflow are gone — by design.

## Decisions

### D1 — `event_type` constants live in a dedicated module

`src/ohmystock/eventbus/types.py` exports a `Final` `EventType` namespace (or a frozen `StrEnum`) with the 14 strings, plus `Agent` constants (`SCANNER`, `DECIDER`, `TRADER`, `LIBRARIAN`, `REVIEWER`, `PROPOSER`, `VALIDATOR`, `GUARD`, `PATTERN_ANALYST`).

**Why:** Emitters and tests need a single source of truth. Free-form strings will drift. A `StrEnum` keeps `event.event_type == "decision_made"` working (preserving the `Event` dataclass shape — no schema migration) while letting tests `import EventType; EventType.DECISION_MADE`.

**Alternatives considered:**
- Inline strings: rejected — drift risk between emitter, serializer, test.
- `dataclass`-per-event-type with typed payloads: rejected — too much ceremony for v0; payload schema is enforced by serializer + tests, not by Python types. Revisit when `pattern_detected` and `review_*` ship.

### D2 — Emit is best-effort via a `safe_emit` helper

A small helper exported from `src/ohmystock/eventbus/__init__.py`:

```python
async def safe_emit(event: Event) -> None:
    try:
        await bus.emit(event)
    except Exception:  # noqa: BLE001 — bus failures must not break producers
        pass
```

All emitters call `await safe_emit(...)`. EventBus already drops on `QueueFull`; this catches the residual surface (serialization errors, cancellation propagation under shutdown, etc.).

**Why:** The bus is observability infrastructure. A trading service failing because the admin UI has a backed-up queue is unacceptable. Single chokepoint = single audit point for the "never block producer" invariant.

**Alternatives considered:**
- Per-service try/except: rejected — duplicates the pattern across 5+ files; harder to enforce at review time.
- Adding `try/except` inside `EventBus.emit`: rejected — hides bugs in `Event` construction (which should fail loudly during dev). The wrapper makes the intent explicit at the call site.

### D3 — `awaiting_confirm` and `order_sent` emit *after* the SQL commit, not before

The producer pattern in confirm-gate v0 is: write `pending_confirm` row → commit → return. The emit must happen **after** the journal write commits. If we emitted before commit, a downstream subscriber could observe an event for a row that never got persisted (e.g., commit failed). Same rule for `decision_made`, `journal_written`, `risk_off_triggered`.

**Why:** Subscribers should be able to query the journal by `decision_id` from an event payload and reliably find the row.

**Trade-off:** A crash between commit and emit drops the event. That is acceptable — events are observability, not durability. The `journal_entries` row is the source of truth.

### D4 — `risk_off_triggered` reuses the auto-execute breaker outcome strings

Auto-execute v0 defines breaker outcomes (`flag_off`, `low_confidence`, `daily_limit`, `notional_limit`, `loss_lockout`, `live_broker`). Each maps to a `risk_off_triggered` event:

| outcome | severity |
|---|---|
| `flag_off` | `warn` |
| `live_broker` | `halt` |
| `low_confidence` | `warn` |
| `notional_limit` | `halt` |
| `daily_limit` | `halt` |
| `loss_lockout` | `halt` |

`pass` and `sizing_clamped_then_pass` do **not** emit (they aren't risk-off events).

**Why:** Reuses existing audit-row contract. `severity` distinguishes informational gating (e.g., flag is off — expected by default) from actively blocked actions so the admin UI can colour them differently.

### D5 — `/api/admin/events` keeps a 15-second comment-frame keepalive

After replacing the heartbeat with a bus subscriber, an idle pipeline could leave the SSE connection silent for arbitrarily long. Many proxies (nginx default 60 s, Cloudflare 100 s) close idle SSE. To stay compatible, the streamer yields a comment frame (`: keepalive\n\n`) every 15 s when the queue has no event waiting.

**Implementation sketch:**

```python
async def _admin_event_stream():
    q = bus.subscribe()
    try:
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=15.0)
                yield {
                    "event": ev.event_type,
                    "data": json.dumps(AdminEventSerializer.serialize(ev)),
                }
            except asyncio.TimeoutError:
                yield ServerSentEvent(comment="keepalive")
    finally:
        bus.unsubscribe(q)
```

### D6 — `AdminEventSerializer.serialize` returns a plain dict (not a string)

```python
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
```

The SSE stream calls `json.dumps(...)` on the result. Returning a dict (not a JSON string) lets tests assert structure without parsing and lets a future Phase-4.5 masked serializer reuse the same input shape.

### D7 — Per-service emit-point placement

| event_type | call site | trigger condition |
|---|---|---|
| `screener_started` | `screener.runner.run_screener()` first line after universe size known | Always; payload `{universe_size}` |
| `screener_completed` | `screener.runner.run_screener()` final line before return | On success only; payload `{candidate_count, symbols}` (full list — see Q1) |
| `decider_thinking` | `decider.orchestrator.decide_entry()` after candidate validation, before swarm call | Always once per call; payload `{symbol, confidence_so_far: 0.0}` (placeholder; field name signals interim status) |
| `decision_made` | `decider.orchestrator.decide_entry()` after journal `pending_confirm` write commits | Always once per call; payload `{symbol, confidence, reasoning, action}` (`action="entry"` if pending_confirm row written, `"skip"` if validator-rejected) |
| `awaiting_confirm` | `decider._journal_writer.write_pending_confirm()` after commit | Always; payload `{symbol, timeout_at, expected_price}` |
| `order_sent` | `safety.confirm_gate.confirm()` after broker `submit_market_order` returns Fill, after journal commit | Only on successful confirm path; payload `{symbol, price=fill_price, quantity=filled_qty, broker_order_id=fill.fill_ts}` (v0 stand-in: FakePaperBroker has no real order id) |
| `journal_written` | `journal` central insertion helper right after `conn.commit()` | Always; payload `{journal_kind=kind, symbol}` |
| `risk_off_triggered` | `safety.auto_execute.try_auto_execute()` inside the audit-row write block, only when `outcome != "pass"` and `outcome != "sizing_clamped_then_pass"` | Per breaker fire; payload `{reason_category=outcome, severity}` per D4 table |

### D8 — Tests use a fresh bus via monkeypatch, not the module singleton

A test fixture `patched_bus()` monkeypatches `ohmystock.eventbus.bus.bus` to a fresh `EventBus()` and yields it plus a list-of-events spy. Avoids cross-test bleed without threading a `bus` parameter through every service signature.

**Decision:** monkeypatch for v0; revisit DI when there's a second non-test consumer of an alternate bus.

## Risks / Trade-offs

- **[Risk] Slow subscriber blocks the producer's queue, dropping events under load.** → Mitigation: `EventBus` already drops on `QueueFull`. Admin UI is single-user (Mark), human-speed; queue size 1024 is ample. Follow-up change can add a per-subscriber drop-counter metric if needed.
- **[Risk] `event.timestamp.isoformat()` produces non-deterministic test output.** → Mitigation: emitters that need pinned time accept the existing `_clock` injection used by confirm-gate / auto-execute and pass `Event(timestamp=clock.now())` explicitly when wired through a clock-aware service.
- **[Risk] `decider_thinking.payload.confidence_so_far: 0.0` placeholder may mislead admin UI consumers.** → Mitigation: spec calls this out explicitly; field name (`_so_far`) signals interim status. Phase 4 frontend treats `0.0` as "thinking, no estimate yet".
- **[Risk] `order_sent.broker_order_id = fill.fill_ts` collides if two confirms happen in the same TPE-second.** → Mitigation: TPE-second collisions are vanishingly rare for human-driven confirms. Spec marks v0; Phase 4 broker work that adds a real broker order id will replace it.
- **[Risk] Adding emit to the journal writer doubles up for the same logical event.** Example: confirm-gate writes a `kind=fill` row, which fires `journal_written`, but confirm-gate also fires `order_sent` separately. → By design — they describe different facets ("bytes hit disk" vs "broker filled"). Frontend treats them as ordered hints.
- **[Trade-off] `await safe_emit` adds an `await` point inside trade-side service paths.** → Acceptable: emit is constant-time (queue `put_nowait`), no I/O, no network. Adds a single event-loop yield per call.

## Migration Plan

No data migration. Code is purely additive in the producer services and replaces a stub in `app.py`.

**Deploy steps (single PR, can be split into commits per service if reviewers prefer):**
1. Land `eventbus.types`, `eventbus.serializers`, `eventbus.safe_emit`.
2. Land per-service emits (5 files: screener runner, decider orchestrator, confirm-gate, auto-execute, journal writer).
3. Land `app.py` change replacing heartbeat with bus subscriber.
4. Land tests.

**Rollback:** revert the commit. No state changes to undo.

## Open Questions

- Q1: Should `screener_completed.payload.symbols` be capped (e.g., first 100) for very large universes? — **Decision for v0:** include the full list; revisit if admin SSE bandwidth becomes a problem with full TW universe (~1700 symbols × ~6 chars each ≈ 10 KB; acceptable).
- Q2: Should `decision_made` fire with `action="skip"` for validator-rejected swarm outputs? — **Decision for v0:** yes. Admin UI benefits from seeing rejected decisions.
- Q3: Does `journal_written` for the auto-execute audit row double-emit alongside `risk_off_triggered`? — **Decision for v0:** yes — they describe different facets. Frontend correlates by `decision_id`.
