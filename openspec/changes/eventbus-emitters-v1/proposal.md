## Why

`eventbus-emitters-v0` shipped 9 emitters; subsequent capability `admin-swarm-endpoints-and-pages` added 4 more (5 swarm event_types — one shared `SWARM_NODE_COMPLETED` between started+completed nodes). That leaves the 8 event_types that v0 explicitly deferred (`pattern_detected`, `journal_queried`, `review_node_started`, `review_completed`, `proposal_created`, `wfa_started`, `wfa_passed`, `wfa_failed`) still unwired — their producers (pattern detector → `scoring/subscorers/vcp_pivot.py`, FTS5 query path → `api/routes/journal.py`, Phase 5 reviewer → `review/pipeline.py`, proposal writer → `proposal/writer.py`, WFA validator → `validation/wfa.py`) have all shipped, so the gap is now purely a wiring task. In parallel, `MaskedEventSerializer.PUBLIC_WHITELIST` is missing entries for the 5 swarm event_types — meaning public SSE silently drops their entire payload today. This change closes both gaps so `/api/admin/events` exposes the full 21-event_type stream and `/api/public/events` ships swarm events with a deliberate (rather than accidental) projection.

## What Changes

- Wire 8 missing emitters at their producing call sites, all via `await safe_emit(...)`:
  - `scoring.subscorers.vcp_pivot.vcp_pivot` — emit `pattern_detected` when classifier returns a VCP / cup-handle / platform match with `score > 0` (i.e. evidence yields a pivot). Payload: `{"symbol": str, "pattern": "VCP"|"cup_handle"|"platform", "score": float}`. Agent: `pattern_analyst`.
  - `api.routes.journal.list_journal_entries` (and any future trade-journal FTS5 query path) — emit `journal_queried` after a SELECT against `journal_entries` returns rows. Payload: `{"query": str, "result_count": int}`. Agent: `librarian`.
  - `review.pipeline.run_review` — emit `review_node_started` immediately before each of the 5 nodes (`data_loader`, `attributor`, `aggregator`, `critic`, `proposer`) runs, and `review_completed` after the index entry is upserted on the happy path. Payloads: `{"review_id": str, "node_name": str, "node_index": int}` and `{"review_id": str, "proposals_created_count": int}` respectively. Agent: `reviewer`. Skip events when `dry_run=True` to preserve dry-run silence.
  - `proposal.writer.write_proposal` — emit `proposal_created` after `target.write_text(...)` succeeds. Payload: `{"proposal_id": str, "priority": "high"|"medium"|"low", "target_section": str}`. Agent: `proposer`. (write fail path raises before emit.)
  - `validation.wfa.run_validation` — emit `wfa_started` immediately after the proposal frontmatter is parsed and `status == "validating"` check passes (i.e. before window splitting / backtest runs); emit `wfa_passed` after the state machine transitions on `verdict == "pass"`; emit `wfa_failed` after the state machine transitions on `verdict == "fail"`. Payloads: `{"proposal_id": str}` for started/passed; `{"proposal_id": str, "failure_reason": str}` for failed (admin gets reason; public mask drops it). Agent: `validator`. `dry_run=True` SHALL still emit (validation is a gate, not a trial).
- Extend `MaskedEventSerializer.PUBLIC_WHITELIST` with the 5 missing swarm entries:
  - `swarm_run_started`: `{"run_id", "preset", "nodes"}` (drops `params` — may contain symbols).
  - `swarm_run_completed`: `{"run_id", "preset", "elapsed_ms"}`.
  - `swarm_run_failed`: `{"run_id", "preset"}` (drops `failed_node` + `error` — leak strategy implementation).
  - `swarm_node_started`: `{"run_id", "preset", "node"}`.
  - `swarm_node_completed`: `{"run_id", "preset", "node", "elapsed_ms"}`.
- Tests:
  - One unit test per new emitter, asserting (a) producer behaviour unchanged when no subscriber attached; (b) correct `event_type` + `agent` + payload shape when a subscriber is attached; (c) emit failure does not break the producer (re-use `safe_emit` discipline already covered by v0 tests).
  - One parametrised mask test: drive each new swarm `event_type` through `MaskedEventSerializer` with a maximal payload (every conceivable field including DENYLIST) and assert the output equals the documented whitelist projection.

## Capabilities

### Modified Capabilities
- `eventbus-emitters`: add 8 new emitter requirements (one per `event_type`). The 21-string registry requirement and `safe_emit` / `AdminEventSerializer` requirements remain unchanged.
- `eventbus-public-mask`: extend `PUBLIC_WHITELIST` with the 5 swarm entries (currently missing); reassert that any non-whitelisted field is dropped (no change to invariant, just new entries).

## Impact

- **Code (modified):**
  - `src/ohmystock/scoring/subscorers/vcp_pivot.py` (emit `pattern_detected`)
  - `src/ohmystock/api/routes/journal.py` (emit `journal_queried`)
  - `src/ohmystock/review/pipeline.py` (emit `review_node_started` x5, `review_completed`)
  - `src/ohmystock/proposal/writer.py` (emit `proposal_created`)
  - `src/ohmystock/validation/wfa.py` (emit `wfa_started`, `wfa_passed`, `wfa_failed`)
  - `src/ohmystock/eventbus/serializers.py` (extend `PUBLIC_WHITELIST`)
- **Code (new tests):** `tests/test_eventbus_emitters_v1.py`, `tests/test_eventbus_public_mask_swarm.py`.
- **Schema:** No DB changes.
- **Docs:** `docs/backend-eventbus.md` already lists the full 21-event_type table; bump §3.2 v0 wiring-status note to "21 of 21 emitted". After archive, update `.claude/rules/capability-map.md` row.
- **Risk:** Low. Each emit is `safe_emit`-wrapped (v0 invariant); a buggy emitter at worst drops its own event, never blocks the producing service. Mask additions only add fields to the public whitelist — no risk of new leakage because each new entry is reviewed against `DENYLIST_FIELDS`.
- **Deferred (still out of scope):**
  - Persistent event log / replay (no Phase 4 demand yet).
  - Event versioning (`decision_made.v2` etc., per `docs/backend-eventbus.md` §10).
  - Multi-worker Redis pub/sub (single uvicorn worker remains v1 deployment).
