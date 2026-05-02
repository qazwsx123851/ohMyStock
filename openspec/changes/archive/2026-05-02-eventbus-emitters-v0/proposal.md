## Why

Phases 0–3.5 ship a complete backend pipeline (screener → decider → confirm gate → exit engine → auto-execute breakers), and `backend-api-and-eventbus` set up the `EventBus` class plus a `/api/admin/events` SSE endpoint — **but nothing connects them**. Today the pipeline runs silently: zero services call `bus.emit()`, and the admin SSE returns a 15-second heartbeat that never subscribes to the bus. Phase 4 web-admin (18 pages, due 2026-08-11) cannot show a single live event without this wiring, and operationally there is no way to watch the existing CLI-driven flows end-to-end. This change closes the gap by emitting events from the services that already exist and turning `/api/admin/events` into a real bus consumer, so Phase 4 frontend work can start against a populated stream.

## What Changes

- Add `ohmystock.eventbus.types` defining the canonical 14 `event_type` string constants from `docs/backend-eventbus.md` §3.2 as a `Literal`/`Final` enum; the v0 wiring scope covers 9 of them (the 5 Phase-5 / pattern events stay defined-but-unemitted).
- Wire **best-effort, fire-and-forget** `bus.emit()` calls into 5 already-shipped services:
  - `screener` → `screener_started`, `screener_completed` (in `ohmystock.screener.runner` or equivalent CLI driver path)
  - `decider` → `decider_thinking`, `decision_made` (in `ohmystock.decider.orchestrator`)
  - `confirm-gate` → `awaiting_confirm` (when an entry transitions to `pending_confirm`), `order_sent` (after broker fill on confirm)
  - `journal` (cross-cutting) → `journal_written` (after every successful `kind` row insert in `ohmystock.journal`)
  - `auto-execute` → `risk_off_triggered` (whenever a breaker fires with severity mapped from the breaker `outcome`)
- Replace the heartbeat-only `_admin_event_stream` in `ohmystock.api.app` with a real subscriber: on connect, call `bus.subscribe()`, await `Queue.get()`, yield each `Event` as SSE (`event: <event_type>`, `data: <json>`), `bus.unsubscribe(q)` on disconnect, and keep a 15s keepalive comment frame so proxies don't drop idle connections.
- Add an `Event` → JSON serializer (`AdminEventSerializer.serialize(event) -> dict[str, Any]`) returning the `{event_id, timestamp, event_type, agent, payload}` shape from §3.3 of `docs/backend-eventbus.md`. (Public/masked serializer is **out of scope** — that's Phase 4.5.)
- Establish a **non-blocking emit contract**: emitters wrap `await bus.emit(event)` in a `try/except` (or a small `_safe_emit` helper) so any bus failure / cancellation never breaks the producing service path. EventBus is already drop-on-full; this change makes the producer side equally tolerant of unexpected exceptions (e.g., serialization errors).
- Tests: per emitter, assert (a) the service still works when no subscriber is attached, (b) the right `event_type` + payload shape is emitted when a subscriber is attached, (c) emit failure is swallowed and does not affect the service's primary write/return path. Plus an integration test driving `TestClient` against `/api/admin/events`, calling `confirm()` in a background task, and asserting the consumer receives the `awaiting_confirm` → `order_sent` → `journal_written` sequence.

## Capabilities

### New Capabilities
- `eventbus-emitters`: defines the canonical 14-string `event_type` registry, the per-service emitter contracts (which service emits which `event_type`, what payload fields are required, what the failure mode is), and the `AdminEventSerializer` JSON shape. Owns the spec invariants for "every emit is best-effort and never blocks the producer".

### Modified Capabilities
- `backend-api-and-eventbus`: replace the stub-heartbeat requirement on `/api/admin/events` with a real bus-subscriber requirement (subscribe on connect, yield `AdminEventSerializer`-serialized events, unsubscribe on disconnect, plus a comment keepalive). The endpoint stays no-auth in this change (Bearer auth is its own later change in Phase 4); only the body of the streaming requirement changes.

## Impact

- **Code (new):** `src/ohmystock/eventbus/types.py` (event_type constants + agent constants), `src/ohmystock/eventbus/serializers.py` (`AdminEventSerializer`), `tests/test_eventbus_emitters.py`, `tests/test_admin_sse_subscribes.py`.
- **Code (modified):** `src/ohmystock/api/app.py` (replace heartbeat generator with bus-subscriber generator), `src/ohmystock/screener/*.py` (emit `screener_started`/`screener_completed`), `src/ohmystock/decider/orchestrator.py` (emit `decider_thinking`/`decision_made`), `src/ohmystock/safety/confirm_gate.py` (emit `awaiting_confirm` at pending_confirm write + `order_sent` after broker fill), `src/ohmystock/safety/auto_execute.py` (emit `risk_off_triggered` on each breaker outcome ≠ `pass`), `src/ohmystock/journal/*.py` (emit `journal_written` after each `kind=*` row commit), plus matching test files.
- **Schema:** No SQLite or DB schema changes.
- **Docs:** Append CLAUDE.md §5 SSOT row pointing at `openspec/specs/eventbus-emitters/spec.md` (after archive) for the emitter ↔ event_type ↔ payload contract.
- **Risk:** Low. Emit failures are swallowed; no producer service depends on the bus succeeding. Worst case if the wiring is buggy: events drop silently — the system stays correct, the admin stream just shows fewer events. Caught by both unit tests (per emitter) and the integration test (full pipeline → SSE).
- **Deferred (explicitly out of scope):**
  - `pattern_detected` emitter (no pattern detector capability shipped yet).
  - `review_node_started` / `review_completed` / `proposal_created` / `wfa_started` / `wfa_passed` / `wfa_failed` (Phase 5 reviewer DAG not built).
  - `journal_queried` (no FTS5 query callsite consumes events yet).
  - Public/masked serializer + `/api/public/events` (Phase 4.5).
  - Bearer auth on `/api/admin/events` (Phase 4 dedicated change).
  - Persistent event log / replay (Phase 4 if needed for admin reload).
