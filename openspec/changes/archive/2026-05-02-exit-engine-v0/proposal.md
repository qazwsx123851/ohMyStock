## Why

Confirm Gate v0 ships filled positions (`decision_status="confirmed"`) but **nothing closes them** — open positions accumulate forever, no `kind=exit` rows are ever written, and Phase 5 monthly review (the closed-loop goal of the project) has no realised P&L to attribute. Without an exit engine, every confirmed trade is a permanent open position from the journal's perspective.

This change ships a **daily, full-position** exit evaluator that consumes confirmed entries and writes `kind=exit` rows tagged with the closing reason. It deliberately leaves the more nuanced behaviours (T1/T1.5 partial fills, Chandelier trailing stops, intraday evaluation, automatic thesis-invalid detection) for later changes — the goal here is to complete the trade lifecycle so end-to-end loops become possible.

## What Changes

- Add `ohmystock.exit_engine` module with `evaluate_position(entry_payload, close_price, asof_date) -> ExitDecision | None` (pure function over snapshotted data) and `evaluate_open_positions(conn, *, market_data, asof, clock) -> list[ExitResult]` (atomic per-position writer).
- Add `ohmystock evaluate-exits --asof YYYY-MM-DD [--symbol XXXX] [--price FLOAT] [--json]` Typer subcommand.
- Implement v0's three exit triggers per `docs/workflow-cheatsheet.md` §6.6:
  - `hit_stop_loss` — close ≤ snapshotted `stop_loss_price`
  - `hit_t1` — close ≥ entry × 1.06 (full-position close, **not** the canonical 50% partial — explicit v0 simplification)
  - `time_stop` — `days_held ≥ expected_holding_days × 2`
- Write `kind=exit` row with payload (`exit_tag`, `actual_exit_price`, `pnl_pct`, `hold_days`, `exited_at`, `close_price_evaluated`) and flip the entry's `decision_status` to `"closed"` (new lifecycle terminal).
- **Backfill `stop_loss_price` + `atr_at_entry` at confirm time** — currently both are `null` per Confirm Gate v0 spec. Modify `confirm()` to compute both from the entry payload's `atr_14_pct` (snapshotted by decider) and the broker's `actual_entry_price`.
- Decider writes `atr_14_pct` into the pending_confirm payload (one new snapshot field, mirrors the `current_price` pattern from confirm-gate-v0).

## Capabilities

### New Capabilities
- `exit-engine`: daily evaluator that reads confirmed entries, evaluates ATR-stop / +6% target / 2× expected-holding-days, writes `kind=exit` rows + flips entry to `closed`. Defines the v0 evaluator API and the three v0 exit_tag values.

### Modified Capabilities
- `confirm-gate`: extend `confirm()` to compute and write `stop_loss_price` and `atr_at_entry` into the entry payload at confirm time (currently both are `null`); use the canonical formula `stop_loss_price = max(actual_entry_price × 0.94, actual_entry_price - 2 × atr_at_entry)` from cheatsheet §6.6 normal-market case.
- `trade-journal-schema`: extend `kind=entry` payload requirement with `atr_14_pct` snapshot field (decider writes) and tighten `stop_loss_price`/`atr_at_entry` to "non-null after confirm"; extend `decision_status` enum with `"closed"`; add new requirement for `kind=exit` payload v0 shape (only the three v0 exit_tag values defined; the other four — `hit_t1_5`, `chandelier`, `thesis_invalid`, `discretionary` — are deferred but reserved in the enum).
- `entry-decider`: modify `decide_entry`'s pending_confirm payload writer to include `atr_14_pct` snapshot (from `EntryDecisionInput.candidate.atr_14_pct`).
- `cli-and-config`: add `ohmystock evaluate-exits` subcommand.

## Impact

- **Code (new):** `src/ohmystock/exit_engine/__init__.py`, `src/ohmystock/exit_engine/evaluator.py`, `src/ohmystock/cli/_evaluate_exits.py`, `tests/test_exit_engine.py`, `tests/test_cli_evaluate_exits.py`.
- **Code (modified):** `src/ohmystock/safety/confirm_gate.py` (compute stop_loss_price + atr_at_entry on confirm), `src/ohmystock/decider/_journal_writer.py` (snapshot `atr_14_pct`), `src/ohmystock/cli/__init__.py` (register subcommand), `tests/test_confirm_gate.py` (new assertions for backfilled fields), `tests/test_decider_orchestrator.py` (new assertion for atr_14_pct snapshot).
- **Schema:** No SQLite DDL changes — `kind=exit` already in CHECK constraint (`journal/schema.py:24`); payload is JSON.
- **Docs:** Append CLAUDE.md §5 (exit engine SSOT row); one-line note in `design-zh-TW.md` near the exit pipeline mention.
- **Deferred (explicitly out of scope):**
  - Partial fills (T1 closes only 50%, T1.5 closes another 25%) — needs a position-tranches model the journal does not have; Phase 4.
  - Chandelier trailing stop on the 25% satellite — same reason.
  - Intraday evaluation — needs live market-data subscription; Phase 4.
  - `thesis_invalid` auto-detection — requires SEPA stage re-evaluation + RS percentile re-fetch + VCP pivot break detection; Phase 4 / 5.
  - `discretionary` exits — Phase 4 admin UI button; CLI doesn't drive these.
  - Real broker sell call — gate is paper-only journal updates (no `submit_market_order(side="sell")` yet); Phase 4 once Shioaji simulator is wired through `paper.broker`.
  - Weak-market mode (`max(price × 0.96, price - 1.5 × ATR)`) — depends on Risk Gate's risk-off detection; Phase 3.5.
- **Risk:** Low. Daily-only evaluation, full-position close, deterministic from snapshotted stop_loss_price + close price; no live broker, no money movement.
