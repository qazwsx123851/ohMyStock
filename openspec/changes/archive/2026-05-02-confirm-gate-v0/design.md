## Context

Phase 3 currently halts at `kind=entry` rows with `decision_status="pending_confirm"` written by `ohmystock.decider.orchestrator.decide_entry`. To complete a trade end-to-end, the system needs a deterministic, testable path from a pending row to either:

- **confirm** → paper broker fill → `decision_status="confirmed"` + `actual_entry_price` / `actual_qty` / `human_confirmed_by` / `human_confirmed_at` written into the same row's `payload_json`;
- **reject** → new `kind=reject` row with `reject_layer="human"` + original entry's `decision_status` flipped to `"rejected"`;
- **expire** → new `kind=expire` row + original entry's `decision_status` flipped to `"expired"` (one-shot CLI sweep, no daemon).

The `journal_entries.kind` CHECK already accepts `entry / exit / reject / expire` (see `src/ohmystock/journal/schema.py:24`), and the FTS5 triggers already cover updates of `payload_json`. So **no DDL migration is required** — the change is pure application code + JSON payload extensions.

The constraints that shape the design:

1. The `EntryDecisionInput` already lives in the journal: every confirmed trade can be priced from the LLM's snapshot (`candidate.current_price`) without re-fetching market data. This makes the broker shim deterministic.
2. The decider already enforces `final_sizing_pct ≤ 25.0` (§2.1 rule 12) — the broker just needs `qty = floor(default_capital * sizing_pct / 100 / current_price / 1000) * 1000` (TWSE 1000-share lots).
3. Sizing/ATR/Risk Gate are deferred — the v0 fill writes `actual_entry_price` and `actual_qty` but leaves the `stop_loss_price` / `atr_at_entry` / `risk_regime_at_entry` fields untouched (still `null`).
4. Every confirm gate function is **caller-owned-transaction**: signature takes `conn: sqlite3.Connection`, never opens or closes its own connection; `BEGIN/COMMIT/ROLLBACK` are inside the function but the connection is the caller's. Mirrors the pattern already used by `decider/_journal_writer.py`.

## Goals / Non-Goals

**Goals:**
- A solo human user can run `ohmystock confirm --list` to see what's pending, then `ohmystock confirm <decision_id>` to fill or `--reject` to refuse, and `--sweep-expired` to garbage-collect old pending rows.
- Confirm gate is unit-testable with an in-memory SQLite — no broker, no LLM, no network.
- The fill path is deterministic enough that integration tests can assert exact `actual_entry_price` and `actual_qty` values.
- The trade-journal payload schema is documented (delta spec) so Phase 5 review can rely on consistent field names.

**Non-Goals:**
- Auto-execute mode (`OHMYSTOCK_AUTO_EXECUTE=true` path with the 9-line breaker) — Phase 3.5.
- Real Shioaji simulator wiring — separate change after `paper/shioaji_client.py` gets fleshed out.
- Risk Gate (`strategies/risk_gate.py`) — separate change; v0 fill skips Risk Gate (the LLM has not yet been blocked by Risk Gate signals because that capability does not exist).
- Sizing Service / ATR Service — same reason; v0 uses `final_sizing_pct` from the entry payload as-is.
- REST endpoint `/api/decisions/{id}/confirm` — Phase 4 web-admin.
- Background daemon / cron for auto-expire — `--sweep-expired` is one-shot; Phase 4 admin UI may add a poller.
- Concurrent confirms (two operators on same row) — out of scope for solo dev; SQLite default journal mode is sufficient (see Risks for the BEGIN IMMEDIATE mitigation).

## Decisions

### D1. Lifecycle: UPDATE the entry row in place vs. INSERT a separate "fill" row

**Decision:** UPDATE the original `kind=entry` row's `payload_json` in place; do **not** introduce a `kind=fill`.

**Rationale:** `docs/llm-decision-schema.md` §4.1 shows `kind=entry` containing both `decision_status="confirmed"` and `actual_entry_price` / `human_confirmed_by` / `human_confirmed_at`, so the schema author intended one row per entry decision. Adding `kind=fill` would require a new CHECK value (DDL migration), break Phase 5 join logic (`§4.5.2` matches by `decision_id`, expects 1 entry + 0/1 exit), and duplicate snapshot fields (`stage`, `rs_percentile`, etc.).

**Alternatives considered:**
- Append-only `kind=fill` row with foreign key to entry → cleaner audit trail, but requires CHECK migration + updates to FTS5 triggers + breaks Phase 5 join logic.
- Status table separate from `journal_entries` → adds a join, complicates the data model for marginal gain.

The trade-off accepted: in-place UPDATE means we lose the original `pending_confirm` payload after confirm. Mitigation: `human_confirmed_at` provides the timestamp, and the row's `created_at` is the original LLM decision time, so the decision-to-confirm latency is recoverable. If a stronger audit trail is needed later, an `entry_status_history` log table can be added without changing the gate's API.

### D2. Reject lifecycle: separate `kind=reject` row + flip entry status

**Decision:** `reject` action writes **two** mutations atomically: (a) INSERT a new `kind=reject` row with `reject_layer="human"`, and (b) UPDATE the original `kind=entry` row's `decision_status` to `"rejected"`.

**Rationale:** Mirrors the existing `reject_layer="llm"` pattern (one `kind=reject` row per layer). The status flip on the original row prevents double-confirm and surfaces the row's terminal state without joining tables.

**Alternative rejected:** Only flip the entry status (no `kind=reject` row). Rejected because Phase 5 review counts rejects per layer, and a `reject_layer="human"` row is the SSOT for "human said no" events.

### D3. Expire lifecycle: same shape as reject, but driven by sweep + clock

**Decision:** `sweep_expired(conn, *, clock, timeout_minutes)` finds all rows where `kind="entry"`, `payload_json.decision_status="pending_confirm"`, and `created_at + timeout_minutes < clock.now()`. For each, atomically: (a) INSERT new `kind=expire` row, (b) UPDATE the original entry's `decision_status` to `"expired"`. Returns the list of swept `decision_id` values for CLI to print.

**Rationale:** Per `docs/llm-decision-schema.md` §4.4, `kind=expire` is its own row. Using a sweep instead of background daemon keeps v0 dependency-free and matches the solo-dev "I run it when I think about it" workflow. Clock is injected (same pattern as `decider/orchestrator.py`) for testability.

**Edge case:** if `confirm <decision_id>` is called on an already-expired row (sweep happened), it returns an error and exits non-zero — without writing anything (the expire row already exists). If confirm is called on a pending row whose age **just** crossed the timeout (no sweep ran yet), v0 chooses to allow the confirm (lazy enforcement). Phase 4 admin UI can tighten this with a poller; v0 stays simple.

### D4. Paper broker shim: PaperBroker Protocol + FakePaperBroker default

**Decision:** Define `PaperBroker(Protocol)` with one method `submit_market_order(symbol: str, qty: int, side: Literal["buy"], reference_price: float) -> Fill`. Provide `FakePaperBroker` that fills at `reference_price` with `filled_qty == requested qty`, no slippage, no partial fills, deterministic `fill_ts` from injected clock.

**Rationale:** Real Shioaji simulator wiring needs auth, a network round-trip, and live trading-hour checks — all of which would block testing. The fake covers the gate's contract surface (gate doesn't care which broker, it just needs `Fill`). Phase 3.5 / future change can implement `ShioajiPaperBroker` against the same Protocol without changing the gate.

**Why no slippage / no partial fills?** v0 is single-user, paper-only, and `reference_price` is from the LLM's snapshot — model accuracy lives in the LLM, not the broker. Adding random slippage adds test flakiness. Future change can add a `SlippagePaperBroker` decorator if needed for backtest realism.

### D5. Qty calculation: floor to TWSE 1000-share lot

**Decision:** `qty = max(1000, floor(default_capital_twd * (final_sizing_pct / 100) / current_price / 1000) * 1000)`. The `max(1000, ...)` guarantees at least one round lot — a lot smaller than 1000 shares is the odd-lot market on TWSE, which the paper broker doesn't simulate. If the resulting notional exceeds `default_capital_twd`, we still write the order (no notional cap in v0; that's Risk Gate's job in a future change).

**Rationale:** TWSE rule. Cleaner than rejecting tiny orders. The `default_capital_twd` is a config knob (`OHMYSTOCK_DEFAULT_CAPITAL_TWD`, default `1_000_000`) that will be replaced by the Sizing Service later.

### D6. Live mode posture

**Decision:** No new `OHMYSTOCK_LIVE_MODE` env var (the project is paper-only). Confirm Gate v0 ignores `OHMYSTOCK_AUTO_EXECUTE` entirely — it is **always** human mode. The CLI prints a one-line warning if `OHMYSTOCK_AUTO_EXECUTE=true` is set: `"warning: auto mode requires the Phase 3.5 breaker, falling back to human confirm"`.

**Rationale:** Simpler than introducing a guard env var. Makes the expectation explicit in CLI output. Phase 3.5 will add the auto path as a separate code path that respects the env var.

### D7. CLI command surface

```
ohmystock confirm --list                          # show pending, with TTL
ohmystock confirm <decision_id>                   # confirm + fill
ohmystock confirm <decision_id> --reject          # human reject (--reason "..." optional)
ohmystock confirm --sweep-expired                 # write expire rows for pending > timeout
```

`--list` reads from the same `OHMYSTOCK_DB_PATH` as `decide`, so no extra config. Default `--user` (for `human_confirmed_by`) is `os.getenv("USER", "unknown")` — overridable via `--user mark@local`.

Exit codes (mirror the `decide` subcommand):
- `0` — action succeeded (confirm filled, list ran, sweep completed)
- `1` — `--reject` succeeded (semantic non-zero, like `decide` returns 1 for an LLM reject — matches the "user-meaningful negative outcome" pattern)
- `2` — decision_id not found / not in pending state / already expired
- `3` — paper broker failure (e.g., FakePaperBroker raises)

`--list` always exits `0` (even with empty list).

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| In-place UPDATE loses the original pending payload (D1). | Original `created_at` is preserved + `human_confirmed_at` records confirm time. If audit trail is needed later, add `entry_status_history` table without breaking the gate API. |
| `final_sizing_pct` is a placeholder (Sizing Service not built); large positions possible if LLM proposes 25% × $1M = $250k notional. | v0 is paper-only and notional is capped by `OHMYSTOCK_DEFAULT_CAPITAL_TWD` × 25%. Risk Gate (separate change) will enforce real caps before Phase 3.5. |
| `--sweep-expired` is manual; pending rows can sit indefinitely if the user forgets. | Phase 4 admin UI will add a poller; for v0 the sweep is documented in CLAUDE.md and runs in seconds. |
| Concurrent confirms on the same `decision_id` (two terminal sessions). | Wrapped in `BEGIN IMMEDIATE` so SQLite locks the DB; second concurrent confirm sees the row is no longer `pending_confirm` and exits with `2`. |
| Clock injection bugs (TZ off-by-eight). | Reuse `_TPE_TZ = timezone(timedelta(hours=8))` from `decider/orchestrator.py:40` (factor it into a shared util if needed); all timestamps are ISO-8601 with `+08:00`. |
| `OHMYSTOCK_AUTO_EXECUTE=true` set by user expecting auto mode. | CLI prints the warning per D6 and still writes a human confirm. Phase 3.5 PR will replace the warning with the actual auto path. |
| `reference_price` in the entry payload is the snapshot price at LLM-decision time, not at confirm time — could be stale (up to `timeout_minutes`). | Documented as a known gap of v0; Phase 4 admin UI can pull live price at confirm time and pass to the gate. The Protocol already accepts `reference_price` so the API does not need to change. |

## Migration Plan

1. Land this change behind `confirm-gate-v0`. No DDL migration; existing journal DBs work unchanged.
2. Run `make test` — all existing 573+ tests should still pass; new `test_confirm_gate.py` / `test_paper_broker.py` / `test_cli_confirm.py` add coverage.
3. Manual smoke (deferred — needs a real Anthropic key + a market day): run `ohmystock decide ...` to write a pending row, then `ohmystock confirm --list` and `ohmystock confirm <id>` to fill.
4. No rollback procedure needed — the change adds modules and a CLI subcommand. Reverting the commit removes them; the journal DB is unaffected.

## Open Questions

None blocking. Two deferred items captured as Risks (sweep daemon, audit trail) are explicitly Phase 4 / future-change scope.
