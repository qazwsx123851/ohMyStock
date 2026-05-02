## 1. Foundation: types, serializer, safe_emit

- [x] 1.1 Create `src/ohmystock/eventbus/types.py` with `EventType` (StrEnum, 16 members) and `Agent` (StrEnum, 9 members) per spec §"Canonical event_type and agent constants"
- [x] 1.2 Add unit test `tests/test_eventbus_types.py` asserting both enums have the exact expected member sets and `EventType.DECISION_MADE == "decision_made"` round-trip
- [x] 1.3 Create `src/ohmystock/eventbus/serializers.py` with `class AdminEventSerializer` exposing `@staticmethod serialize(event: Event) -> dict[str, Any]`
- [x] 1.4 Add unit test `tests/test_admin_event_serializer.py` covering 5-key shape, `+08:00` timestamp round-trip, and "no mask / no field strip" invariants
- [x] 1.5 Add `safe_emit(event: Event) -> None` async function to `src/ohmystock/eventbus/__init__.py`; catch `Exception` only, let `BaseException` (incl. `CancelledError`) propagate
- [x] 1.6 Add unit test `tests/test_safe_emit.py` covering: (a) happy-path delivers to subscriber, (b) `bus.emit` raising `RuntimeError` is swallowed, (c) `CancelledError` propagates

## 2. Producer wiring: screener

- [x] 2.1 Identify the screener entry function (run `grep -rn "def run_screener\|def screen\|def filter_universe" src/ohmystock/screener/`); confirm async-friendly emit site
- [x] 2.2 Emit `EventType.SCREENER_STARTED` after `universe_size` is known; emit `EventType.SCREENER_COMPLETED` on success path with `candidate_count` and full `symbols` list
- [x] 2.3 Add `tests/test_screener_emitter.py` covering happy-path two-events, exception-path-only-started, no-subscriber tolerance per spec §"Screener emitter" scenarios

## 3. Producer wiring: decider

- [x] 3.1 Modify `src/ohmystock/decider/orchestrator.py` `decide_entry()` to emit `EventType.DECIDER_THINKING` after candidate validation, payload `{"symbol", "confidence_so_far": 0.0}`
- [x] 3.2 After `pending_confirm` row commit (success path) emit `EventType.DECISION_MADE` with `action="entry"`, payload from swarm output
- [x] 3.3 In §2.1 system override validator-rejected path, emit `EventType.DECISION_MADE` with `action="skip"`
- [x] 3.4 Extend `tests/test_decider_orchestrator.py` for entry-path 2-event sequence, skip-path emission, and exception-path no-emit (delivered via new `tests/test_decider_emitter.py`)

## 4. Producer wiring: confirm-gate

- [x] 4.1 Modify `src/ohmystock/decider/_journal_writer.py` `write_pending_confirm()` to emit `EventType.AWAITING_CONFIRM` after commit, payload `{"symbol", "timeout_at", "expected_price"}` from the entry payload (delivered via orchestrator post-commit emit, since the writer is inside the atomic block)
- [x] 4.2 Modify `src/ohmystock/safety/confirm_gate.py` `confirm()` to emit `EventType.ORDER_SENT` after fill row commit, payload `{"symbol", "price", "quantity", "broker_order_id": fill.fill_ts}`
- [x] 4.3 Verify failure paths (`ConfirmGateError`, `BrokerError`) do **not** emit `order_sent`; add explicit assertions in `tests/test_confirm_gate.py` (delivered via new `tests/test_confirm_gate_emitter.py`)
- [x] 4.4 Add `awaiting_confirm` happy-path assertion to existing decider tests; add `order_sent` happy-path + broker-failure-no-emit assertions to existing confirm-gate tests (delivered via new emitter test files)

## 5. Producer wiring: journal

- [x] 5.1 Locate the central row-insert helper(s) in `src/ohmystock/journal/`; if writes are scattered, add a single `_emit_journal_written(kind, symbol)` helper called from each commit site (added as `emit_journal_written` in `journal/__init__.py`)
- [x] 5.2 Emit `EventType.JOURNAL_WRITTEN` after each `conn.commit()`, payload `{"journal_kind": kind, "symbol": symbol}` (wired into orchestrator entry+reject+parse-error paths, confirm-gate reject + sweep_expired, exit-engine close, auto-execute audit row)
- [x] 5.3 Add `tests/test_journal_emitter.py` covering at least three `kind` values (`entry`, `fill`, `exit`); assert no emit when commit fails (e.g., unique constraint conflict)

## 6. Producer wiring: auto-execute

- [x] 6.1 Modify `src/ohmystock/safety/auto_execute.py` `try_auto_execute()` to emit `EventType.RISK_OFF_TRIGGERED` after audit row commit, *only* when `outcome` is in {`flag_off`, `low_confidence`, `live_broker`, `notional_limit`, `daily_limit`, `loss_lockout`}
- [x] 6.2 Map outcome → severity per design D4 / spec table (`flag_off`/`low_confidence` → `warn`; everything else → `halt`)
- [x] 6.3 Extend `tests/test_auto_execute.py` for: low_confidence emit, notional_limit emit, pass-no-emit, sizing_clamped_then_pass-no-emit (delivered via new `tests/test_auto_execute_emitter.py`)

## 7. Admin SSE replacement

- [x] 7.1 Replace `_admin_event_stream` in `src/ohmystock/api/app.py` with a generator that calls `bus.subscribe()`, loops on `asyncio.wait_for(q.get(), timeout=15.0)`, yields serialized events on `Event` and `ServerSentEvent(comment="keepalive")` on `TimeoutError`, calls `bus.unsubscribe(q)` in `finally`
- [x] 7.2 Verify `sse-starlette` `ServerSentEvent(comment=...)` API works as expected; if not, fall back to manually-yielded `: keepalive\n\n` raw string (works as expected)
- [x] 7.3 Add `tests/test_admin_sse_subscribes.py` covering: real-event broadcast in admin JSON shape, idle-keepalive within 16 s, unsubscribe-on-disconnect (spy on `bus.unsubscribe`), no-auth still works

## 8. End-to-end integration test

- [x] 8.1 Write `tests/test_eventbus_e2e.py` that uses `httpx.AsyncClient` (or `TestClient` with streaming) to open `/api/admin/events`, runs a confirm-gate happy path in a background `asyncio.Task`, and asserts the consumer receives `awaiting_confirm` → `order_sent` → `journal_written` events in order (delivered as direct generator-driven SSE consumer; ASGITransport buffers SSE so direct generator pump is more reliable)

## 9. Best-effort failure tolerance regression coverage

- [x] 9.1 Add a parametrized test that monkeypatches `bus.emit` to raise `RuntimeError` and runs each producer happy path (screener, decider, confirm-gate, auto-execute, journal) — asserts every producer's primary write/return is unaffected
- [x] 9.2 Add a queue-full test: pre-fill a `maxsize=1` subscriber queue, run `try_auto_execute` with a `low_confidence` payload, assert auto_execute returns the expected `AutoExecuteResult` and the audit row is committed

## 10. Docs and SSOT alignment

- [x] 10.1 After spec deltas archive into `openspec/specs/eventbus-emitters/spec.md`, add a row to CLAUDE.md §5 (the SSOT table) pointing at `openspec/specs/eventbus-emitters/spec.md` for the emitter contract
- [x] 10.2 Add a one-line note to `docs/backend-eventbus.md` near §3.1 / §3.2 confirming v0 wires 9 of the 16 event_types and listing the 7 deferred (5 review/proposal/wfa + `pattern_detected` + `journal_queried`)
- [x] 10.3 Run `openspec validate eventbus-emitters-v0 --strict` and fix any diagnostics — output: "Change 'eventbus-emitters-v0' is valid"

## 11. Verification before archive

- [x] 11.1 `pytest tests/ -k "eventbus or emitter or sse or admin"` — 78 passed
- [x] 11.2 `pytest tests/` — 744 passed (no regressions in screener / decider / confirm-gate / exit-engine / auto-execute / journal tests)
- [x] 11.3 Manual smoke: start `uvicorn ohmystock.api.app:create_app --factory` in one shell, `curl -N http://localhost:8000/api/admin/events` in another, run `ohmystock evaluate-exits --asof 2026-05-02` (or any CLI that touches the journal) in a third, and observe the live event stream — verified by user 2026-05-02: `uv run uvicorn ohmystock.api.app:create_app --factory --reload` started cleanly on `127.0.0.1:8000`, `GET /api/admin/events` returned `200 OK` with keepalive frames flowing. Cross-process events from CLI are not visible to the running uvicorn server's SSE by design (in-process EventBus only) — this is a documented v0 limitation and does not affect Phase 4 web-admin since all UI-driven actions will live in server endpoints
