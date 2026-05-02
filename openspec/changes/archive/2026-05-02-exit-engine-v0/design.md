## Context

Confirm Gate v0 leaves filled positions with `decision_status="confirmed"` and `actual_entry_price` / `actual_qty` populated, but `stop_loss_price` and `atr_at_entry` are still `null` (deferred per `confirm-gate-v0`'s spec). Phase 5 review needs `kind=exit` rows joined on `decision_id` to compute realised P&L; currently no such rows exist.

The cheatsheet (`docs/workflow-cheatsheet.md` §6.6) defines the canonical exit policy:

```
正常市況：停損價 = max(進場價 × 0.94, 進場價 - 2.0 × ATR(14))
T1 (+6%) → 出場 50% (核心倉鎖獲利)
T1.5 (+12%) → 再出場 25%
衛星倉 25% → Chandelier(3×ATR(22))
```

Implementing the canonical 50/25/25 split requires a **position-tranches model** the journal does not have today (one `decision_id` would need 3 partial `kind=exit` rows). v0 explicitly accepts the simplification of "full-position close on T1" to ship the lifecycle without that data-model change. The cheatsheet's PF v1 (T1 full close) was 2.42 with +6% expected value — worse than v2's 2.0 / +15-25% but acceptable as a baseline for the loop.

`kind=exit` is already valid in the CHECK constraint (`src/ohmystock/journal/schema.py:24`). FTS5 triggers already fire on `payload_json` updates. So **no DDL migration**; this is pure application code + payload conventions.

The constraints that shape the design:

1. **Daily-only**: matches solo-dev "I run it after market close" workflow; avoids needing a live tick subscription.
2. **Caller-owned transaction**: same pattern as `safety/confirm_gate.py:_begin_immediate` — `evaluate_open_positions(conn, ...)` opens `BEGIN IMMEDIATE` per position.
3. **Snapshot-driven**: stop_loss_price computed once at confirm time; the engine never recomputes ATR. (Chandelier would re-evaluate; deferred.)
4. **Deterministic**: given `(entry_payload, close_price, asof_date)`, `evaluate_position` is a pure function — easy to unit-test without SQLite or market_data.

## Goals / Non-Goals

**Goals:**
- Solo human can run `ohmystock evaluate-exits --asof 2026-05-07` after market close and have all open positions evaluated; closed positions get `kind=exit` rows + `decision_status="closed"`.
- Each exit row is enough on its own for Phase 5 review (no joins back to entry needed for basic P&L — but the entry's snapshot fields are still preserved on the entry row for SEPA attribution).
- v0 evaluator is unit-testable without SQLite (the pure `evaluate_position` function is the contract; the writer is a thin SQLite wrapper).

**Non-Goals:**
- Partial fills (50/25/25 cheatsheet split) — Phase 4.
- Chandelier trailing stop — Phase 4 (depends on partial fills to make sense).
- Intraday evaluation / streaming — Phase 4.
- `thesis_invalid` auto-detection (re-fetch SEPA stage / RS / VCP) — Phase 4 / 5.
- `discretionary` exits via CLI — Phase 4 admin UI.
- Real broker sell call — Phase 4 once `paper.broker` supports `side="sell"`.
- Weak-market mode (`-1.5 × ATR` stop, `× 0.96`) — depends on Risk Gate's risk-off detection (Phase 3.5).
- Slippage on exit fills — `actual_exit_price` equals the daily close price evaluated; future change can layer on a slippage model.
- Concurrent evaluation runs (two terminals on same DB) — same posture as Confirm Gate; SQLite default journal mode + BEGIN IMMEDIATE is sufficient.

## Decisions

### D1. Full-position close on T1 (vs canonical 50% partial)

**Decision:** v0 closes 100% on `hit_t1` (close ≥ entry × 1.06). Document the deviation from cheatsheet §6.6 explicitly in the spec.

**Rationale:** The journal currently has no concept of position tranches — one `decision_id` is one position. Implementing 50/25/25 partials requires either (a) a new `journal_entries.tranche_id` column (DDL migration), (b) adding a `position_tranches` table (new schema), or (c) overloading multiple `kind=exit` rows per `decision_id` (breaks the §4.5.2 invariant "1 entry → 0 or 1 exit"). Each option is a separate, larger change. v0 accepts PF 2.42 / +6% EV (the cheatsheet's v1 baseline) to ship now.

**Alternatives considered:**
- (a)/(b)/(c) above — punted to Phase 4 with `position-tranches` capability change.
- Skip T1 entirely (only stop + time stop) — would never close winning positions, makes Phase 5 review unbalanced.

The trade-off accepted: PF goes from v2's 2.0 to v1's 2.42 but expected value drops from +15-25% to +6%. v0 ships now; partials change ships later.

### D2. Lifecycle: append `kind=exit` row + flip entry to `closed`

**Decision:** Each evaluation that closes a position writes **two** mutations atomically: (a) INSERT `kind=exit` row with `decision_id` linkage, (b) UPDATE entry's `decision_status` from `"confirmed"` to `"closed"`. Mirrors the reject path from confirm-gate-v0 D2.

**Rationale:** Phase 5 review's `data_loader` joins on `decision_id`; the join logic in `docs/llm-decision-schema.md` §4.5.2 expects "1 entry + 0/1 exit". Flipping `decision_status="closed"` lets the engine skip already-closed entries on the next evaluation pass without joining tables.

**Lifecycle terminal states:** `confirmed → closed` (this change), `pending_confirm → rejected/expired` (already in confirm-gate-v0). All four (`pending_confirm/confirmed/rejected/expired/closed`) are terminal — no transitions out.

### D3. Stop-loss & ATR backfilled at confirm time, not on-the-fly

**Decision:** Modify `confirm-gate.confirm()` to compute `stop_loss_price` + `atr_at_entry` from `actual_entry_price` and `atr_14_pct` (snapshotted on the entry payload by the decider). Exit engine reads `stop_loss_price` directly from the entry payload; never recomputes.

**Rationale:** The confirm-gate-v0 deferral was explicit ("待 ATR Service 計算"). Now that the exit engine needs the value, the cheapest source is the data already on the row — `atr_14_pct` is on the candidate snapshot (`swarm/models.py:CandidateSnapshot:32`), and the broker's `actual_entry_price` is known at confirm time. No new external dependency. Formula:

```python
atr_at_entry = actual_entry_price * atr_14_pct / 100   # percent → TWD absolute
stop_loss_price = max(actual_entry_price * 0.94, actual_entry_price - 2.0 * atr_at_entry)
```

For `actual_entry_price=832.0`, `atr_14_pct=2.85`: `atr_at_entry=23.71`, `stop_loss_price=max(782.08, 784.58)=784.58`.

**Alternative rejected:** Have the exit engine recompute on every call. Bad because (a) the ATR window in 5 days might give a different value than at entry, breaking the contract that "the stop is set at entry and never moves" (cheatsheet §6.6 normal-market case), and (b) it would require fetching historical bars on every evaluation — slow and dependency-heavy.

### D4. Evaluator API: pure function + thin SQLite wrapper

**Decision:** Two functions:

```python
def evaluate_position(
    entry_payload: dict,         # already-loaded JSON dict
    close_price: float,          # daily close as of asof_date
    asof_date: date,             # date being evaluated
) -> ExitDecision | None:        # None means "hold"
    ...

def evaluate_open_positions(
    conn: sqlite3.Connection,
    *,
    market_data: MarketDataLookup,   # protocol: get_close(symbol, asof) -> float
    asof: date,
    clock: Clock,
    symbol_filter: str | None = None,
) -> list[ExitResult]:
    ...
```

`evaluate_position` is pure — easy to parametrize across the three exit triggers without SQLite. `evaluate_open_positions` is the orchestrator: query open entries, fetch close prices, dispatch to `evaluate_position`, write rows.

**Why two functions instead of one method on a class?** Mirrors `decider.validator.validate_decider_output` (pure) + `decider.orchestrator.decide_entry` (writer) split that already works well in the codebase.

### D5. Decision tree order: stop-loss first, then T1, then time-stop

**Decision:** Triggers checked in this order:

1. `close ≤ stop_loss_price` → `hit_stop_loss` (downside protection wins)
2. `close ≥ entry × 1.06` → `hit_t1` (target met)
3. `days_held ≥ expected_holding_days × 2` → `time_stop` (forgotten position)
4. else → hold (no row written)

**Rationale:** A stop-loss hit on the same day as a +6% close is impossible (would require a wide intraday range we don't model in v0); but if both were ever true, downside protection dominates. T1 before time_stop matters: a position that closed +7% on its `expected_holding_days × 2` day should record `hit_t1`, not `time_stop`.

**P&L sign convention:** `pnl_pct = (close - entry) / entry × 100`, so stops are negative, T1 is +6.x, time_stops can be either sign.

### D6. CLI: `evaluate-exits --asof <date> [--symbol] [--price] [--json]`

```
ohmystock evaluate-exits --asof 2026-05-07
ohmystock evaluate-exits --asof 2026-05-07 --symbol 2330
ohmystock evaluate-exits --asof 2026-05-07 --symbol 2330 --price 882.0
ohmystock evaluate-exits --asof 2026-05-07 --json
```

- `--asof` is mandatory (no implicit "today" — operator should be explicit about which trading day's close they're using).
- `--symbol` filters to one position (useful for spot-checks).
- `--price` overrides the market_data lookup with a hardcoded close (testability + manual override when data is stale).
- `--json` emits one JSON dict per evaluated position with `decision_id, action ("closed"|"held"), exit_tag, pnl_pct` etc.

**Exit codes:**
- 0: evaluation completed (any number of positions closed, including zero).
- 2: usage error (missing `--asof`, invalid date, `--price` without `--symbol`).
- 3: market_data lookup failed (no close price available for some symbol; CLI prints the failing symbol(s) and exits without writing anything).

The `--price` override is single-symbol only because v0 doesn't take a multi-symbol price file; that can be added later if needed.

### D7. Market data lookup: thin Protocol, default uses live providers

**Decision:** Define `MarketDataLookup` Protocol with one method `get_close(symbol: str, asof: date) -> float | None`. The CLI's default implementation calls `ohmystock.swarm._live_market` (already in use by `ohmystock decide`), which goes through the existing FinMind / Shioaji fallback chain.

**Why a Protocol?** Tests can inject a `dict[(symbol, date), float]` lookup without hitting the network; v0 production uses the live providers; future changes can swap in a backtest historical-data lookup without touching the engine.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Full-position T1 close (D1) loses the satellite tranche's run-up; PF 2.42 / +6% EV vs cheatsheet target 2.0 / +15-25%. | Documented as explicit v0 simplification; `position-tranches` capability change scheduled for Phase 4 will recover the canonical behaviour. Phase 5 review can compute "what would v2 have made" by joining entry's `expected_holding_days` against post-exit returns. |
| `atr_14_pct` from candidate snapshot might be stale if there's a long gap between Phase 2B scoring and confirm. | Confirm Gate v0 already enforces 30-min timeout; in practice ATR doesn't move materially in 30 min. Documented as known gap; if confirm-gate timeout is ever extended, this assumption may need revisiting. |
| Daily-only evaluation misses intraday stop-loss hits that recovered by close. | Cheatsheet §6.6 explicitly addresses this: "盤中觸停損但收盤拉回 → 停損價下移至「收盤價 - 1.5×ATR」與「進場價 - 2×ATR」較低者". v0 just doesn't move the stop; future change can implement the trailing logic. |
| `time_stop` hardcoded to `expected_holding_days × 2`; LLM might propose unrealistic holding periods. | The decider already enforces `expected_holding_days ∈ [1, 30]` (entry-decider spec §2). 60-day max time_stop is acceptable; tunable later via config if needed. |
| `evaluate-exits` is manual; user must remember to run it each trading day. | Phase 4 admin UI will add a daily poller (cron or background task); v0 stays manual. The CLI is fast (single SELECT + N close-price lookups). |
| Exit happens on the wrong day if user passes a non-trading-day `--asof`. | v0 doesn't validate trading-day-ness — passes the date straight to `market_data.get_close`. If FinMind returns no data for that date, the lookup returns None and CLI exits 3 with the failing symbol. |

## Migration Plan

1. Land this change. No DDL migration; existing journal DBs work unchanged.
2. Run `make test`; existing 641 + ~25 new tests should pass.
3. Manual smoke (deferred — needs ANTHROPIC_API_KEY + a confirmed position): `ohmystock decide ... → ohmystock confirm <id> → wait for price move OR pass --price → ohmystock evaluate-exits --asof <date> --symbol XXXX --price <close>`.
4. No rollback procedure — adds modules + CLI command. Reverting removes them; the journal DB is unaffected.

## Open Questions

None blocking. The two main deferred items (partial fills, intraday evaluation) are explicitly Phase 4 scope and don't block v0 from being useful.
