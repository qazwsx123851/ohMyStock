## Context

Phase 3 just shipped two changes that, together, give us a fully working **human** confirmation loop:

- `entry-decider-pm-node` writes a `kind=entry` row in `pending_confirm` state with sizing/ATR/confidence in payload.
- `confirm-gate-v0` exposes `confirm() / reject() / sweep_expired() / list_pending()` for a human user to act on that row.

The cheatsheet (`docs/workflow-cheatsheet.md` §6.7) and safety doc (`docs/safety-and-simulation.md` §2.9) always required a Mode B that lets the gate auto-confirm without a human, gated by five hard breakers. That is the gap this change closes — Phase 3.5 in the roadmap.

Constraints:
- Solo project, sim-only for at least 6 months. Live mode must remain physically impossible to auto-execute.
- All persistence is SQLite + JSON payload (`journal_entries`). No new tables.
- `confirm()` already writes the heavy fill + ATR + stop-loss math; the auto path must reuse it, not duplicate it.
- No CLI / scheduler / EventBus in this change (that's Phase 4). Auto-execute must be invokable as a pure Python function with an injectable clock and broker.

## Goals / Non-Goals

**Goals:**
- One pure function `try_auto_execute(conn, decision_id, broker, settings, ...)` that returns an `AutoExecuteResult` with `outcome ∈ {pass, flag_off, low_confidence, daily_limit, notional_limit, loss_lockout, live_broker, sizing_clamped_then_pass}`.
- Defense-in-depth: even with `OHMYSTOCK_AUTO_EXECUTE=true`, live broker still falls back; even with sim broker, every breaker is checked.
- Audit row written **on every call** (pass *and* fallback) so the journal is the single record of why an entry was or wasn't auto-executed.
- Sizing clamp (>30% deviation) does not block — it adjusts and emits an audit row showing both raw and clamped values, then proceeds.
- `auto_executed=True` set on the entry payload only when the auto path completes the confirm successfully.
- All breakers use the existing `journal_entries` SQL surface — no new tables.

**Non-Goals:**
- No CLI command (`ohmystock auto-execute --run`). Phase 4 work.
- No APScheduler integration. Phase 4 work.
- No EventBus emission of `auto_execute_decided` events. Phase 4 work.
- No alert/notification on fallback. Phase 4 work (separate `notifications` capability).
- No real Volatility Targeting formula for `system_sizing_pct` — see Decision 7 for the v0 stub.
- No `kind=exit` rows yet (exit-engine v0 just landed in another change but does not write `kind=exit`; loss-streak query gracefully degrades — see Decision 6).

## Decisions

### 1. Module placement: `ohmystock.safety.auto_execute`

Sits next to `confirm_gate.py`. Both implement Phase 3.5 safety surface; both write to `journal_entries`; both take an injectable Clock + Broker. Keeps the import graph linear:
```
decider.orchestrator → safety.confirm_gate → paper.broker
                     → safety.auto_execute → safety.confirm_gate (re-uses)
```
Alternatives considered: putting it in `paper/` (rejected — auto_execute is *policy*, not broker logic) or a new `phase35/` package (rejected — premature partition).

### 2. `try_auto_execute` reuses `confirm()` rather than duplicating

The auto path does **not** re-implement qty / ATR / stop-loss math. After breakers pass, it calls `confirm(conn, decision_id=..., broker=..., default_capital_twd=..., user="auto", auto_executed=True, clock=...)` inside the same transaction-managed call.

Rationale: the cheatsheet §6.6 sizing/ATR formula has *one* implementation. If we ever change it, only confirm-gate updates. Trade-off: `confirm()` gains an `auto_executed: bool = False` parameter (small modification — see Modified Requirements).

Alternatives considered: copy/paste the math (rejected — SSOT violation; cheatsheet §6.6 explicitly named confirm-gate as authority); have confirm-gate dispatch into auto-execute (rejected — backwards dependency, hides side-effects).

### 3. Breaker order: cheap → expensive → side-effecting

```
1. flag_off       — settings field, no IO
2. live_broker    — settings.OHMYSTOCK_BROKER == "shioaji-live"
3. low_confidence — read entry payload (1 SELECT, already needed)
4. notional_limit — compute qty * current_price, compare vs equity
5. daily_limit    — COUNT(*) on today's auto entries
6. loss_lockout   — read last 3 closed exits (LIMIT 3 SELECT)
7. sizing_clamped — pure compute on payload (NOT a fallback)
8. → confirm(...) — broker call, payload UPDATE
```

The first violation short-circuits and writes one audit row with that outcome. Sizing clamp is checked last (right before `confirm()`) and never causes a fallback — it only mutates the value being passed and adds a `sizing_clamped_then_pass` outcome label.

Alternatives considered: random order (rejected — stable order makes test scenarios deterministic and audit-log greppable); evaluate-all-then-decide (rejected — wastes IO on a doomed call).

### 4. Audit row format: one `kind=auto_execute_audit` per call

Every call to `try_auto_execute` writes exactly one audit row, regardless of outcome:

```json
{
  "decision_status": "auto_execute_audit",
  "outcome": "<one of 8 outcomes>",
  "decision_id_ref": "dec_2026-05-02T10-00-00_2330",
  "audit_at": "2026-05-02T10:15:00+08:00",
  "evidence": {
    "llm_confidence": 0.62,
    "min_confidence": 0.7,
    "auto_today_count": 2,
    "daily_limit": 5,
    "notional_twd": 250000,
    "max_notional_twd": 250000,
    "system_sizing_pct": 25.0,
    "raw_sizing_pct": 30.0,
    "clamped_sizing_pct": 25.0,
    "loss_streak_count": 0,
    "lockout_until": null,
    "broker_mode": "shioaji-sim"
  }
}
```

Only the relevant evidence keys for that outcome are filled (others omitted, not null, to keep payload small). Audit row's `symbol` matches the entry row's symbol (FK is `decision_id_ref` not a real FK — SQLite has no FK enforcement here).

Rationale: greppable by outcome (`SELECT … WHERE json_extract(payload, '$.outcome') = 'low_confidence'`); single row keeps querying simple; pass case still emits audit so `COUNT(kind='auto_execute_audit')` = `COUNT(try_auto_execute calls)`.

Alternatives considered: only audit fallbacks (rejected — can't tell "passed and confirmed" from "no call ever made"); audit per-breaker (rejected — N rows per call is messy).

### 5. Settings layer

```python
class Settings(BaseSettings):
    OHMYSTOCK_AUTO_EXECUTE: bool = False
    OHMYSTOCK_AUTO_EXECUTE_DAILY_LIMIT: int = 5
    OHMYSTOCK_AUTO_EXECUTE_MIN_CONFIDENCE: float = 0.7
    OHMYSTOCK_AUTO_EXECUTE_MAX_NOTIONAL_PCT: float = 0.25  # 25%
    OHMYSTOCK_AUTO_EXECUTE_MAX_SIZING_DEVIATION: float = 0.30  # 30%
    OHMYSTOCK_AUTO_EXECUTE_LOSS_LOCKOUT_HOURS: int = 24
    OHMYSTOCK_AUTO_EXECUTE_LOSS_PCT_THRESHOLD: float = -0.05  # -5%
    OHMYSTOCK_AUTO_EXECUTE_ACCOUNT_EQUITY_TWD: int = 1_000_000

    @model_validator(mode="after")
    def forbid_auto_execute_in_live(self):
        if self.OHMYSTOCK_AUTO_EXECUTE and self.OHMYSTOCK_BROKER == "shioaji-live":
            raise RuntimeError(
                "Refusing to start: OHMYSTOCK_AUTO_EXECUTE=true is not allowed "
                "when OHMYSTOCK_BROKER=shioaji-live. Live mode requires human confirm."
            )
        return self
```

Rationale: defaults match cheatsheet §6.7 exactly; all numbers exposed as env vars so I can dial them down for paranoid testing without touching code; **two-layer defense** (settings validator at process boundary + `live_broker` breaker at call boundary).

Alternatives considered: hard-code thresholds in the module (rejected — cheatsheet calls them out as tunable); single `AUTO_EXECUTE_PROFILE: Literal["safe","standard","aggressive"]` (rejected — premature; one user, one profile).

### 6. Loss-lockout query: graceful degrade until exit-engine writes journal rows

`exit-engine-v0` shipped but it currently emits `ExitDecision` dataclasses to a caller; it does not write `kind=exit` rows to `journal_entries` yet. Until that integration lands (separate change `exit-engine-journal-writer`), the loss-lockout query will always return zero matching rows and the breaker is effectively a no-op.

The `try_auto_execute` code SHALL still execute the query on every call (so the breaker activates automatically when exit rows start being written). Until then, the breaker can't trigger, but the audit row still records `loss_streak_count: 0` and `lockout_until: null` for traceability.

Trade-off: there's a window where Mode B has only 4 working breakers. Acceptable because (a) confidence + daily-limit + notional are the strongest, (b) sim-only, (c) followed up immediately by the exit-engine-journal-writer change. Documented as Risk R3 below.

### 7. `system_sizing_pct` v0 stub: stage-cap derived

The cheatsheet §6.6 Volatility Targeting formula isn't implemented yet (no module computes it). For v0, `system_sizing_pct` is derived from the §2.1 validator's stage caps:

```python
def system_sizing_pct(stage: int) -> float:
    return 10.0 if stage == 3 else 25.0
```

This is enough to make the deviation clamp meaningful for stage-3 entries (where the cheatsheet's hardest cap applies) and a no-op-ish for stage-1/2 (where `final_sizing_pct ≤ 25.0` already by validator).

When Volatility Targeting lands as its own change, `system_sizing_pct` becomes that function's output and this stub gets replaced. Documented in the spec as a v0 contract so the replacement is non-breaking.

Alternatives considered: skip the deviation clamp entirely until vol-targeting exists (rejected — cheatsheet §6.7 lists it as a Mode B safeguard; we want the wiring in place); fail-closed on stage-3 (rejected — too aggressive, stage-3 entries should still be reachable in auto mode if LLM proposes ≤ 10%).

### 8. Reading `account_equity_twd` from settings

Notional cap needs an equity value. Real broker would expose `broker.account_equity()` but `FakePaperBroker` does not. v0 reads `OHMYSTOCK_AUTO_EXECUTE_ACCOUNT_EQUITY_TWD` from Settings (default 1,000,000 — same as confirm-gate's `default_capital_twd` test default). Future integration with Shioaji `api.account_balance()` is a separate change.

### 9. Trade-journal / spec impact

- Modified `confirm-gate` capability gets ONE new requirement (the `auto_executed` parameter), and ONE modified requirement (the `confirm()` payload-update set adds `auto_executed`). All existing scenarios remain valid.
- Modified `entry-decider` capability gets ONE modified requirement (entry payload includes `system_sizing_pct`).
- New `auto-execute` capability has its own spec file with all the breaker requirements and audit format.

## Risks / Trade-offs

- **R1: A Mode B run could spam audit rows.** With one audit per `try_auto_execute` call and a future per-symbol scheduler running every minute, we could produce ~500 rows/day. → Mitigation: payload is small (~300 bytes). 500/day × 365 = ~50MB/year, well within SQLite. If it grows, future change can add `audit_at` index + monthly archival.

- **R2: A sim-mode `account_equity_twd` could drift from real broker equity, causing notional-limit to reject good signals or pass bad ones.** → Mitigation: v0 reads from Settings (single source); a future change wires `broker.account_equity()` for real Shioaji. The spec calls this out so the dependency is documented.

- **R3: Loss-lockout breaker is a no-op until exit-engine writes `kind=exit` rows.** → Mitigation: exit-engine-journal-writer is the very next change; until it lands, fallback to the other 4 breakers + sim-only. Documented in Decision 6 above.

- **R4: Race condition between `try_auto_execute` and a concurrent human `confirm()` on the same `decision_id`.** Both functions take `BEGIN IMMEDIATE`; the loser raises `OperationalError`. Auto-execute SHALL surface this as `outcome="lost_race"` (a 9th outcome added if needed) — for v0, the SQLite OperationalError propagates (caller should retry the entire orchestration). Acceptable for v0 because there's only one process / one user.

- **R5: A bug in `try_auto_execute` could leave the entry in `pending_confirm` even after `confirm()` succeeded.** → Mitigation: `confirm()` already commits its own transaction; the audit row is written *after* `confirm()` returns successfully in the auto path. If audit-row write fails, entry is correctly confirmed but missing audit — better than the reverse. The spec captures this ordering.

## Migration Plan

No data migration required (JSON payload extensions are backwards-compatible).

Rollout:
1. Land this change — auto path exists but `OHMYSTOCK_AUTO_EXECUTE` defaults to `false` so behavior is unchanged.
2. Manually flip the flag in `.env.local` once (after verifying breaker thresholds match my risk tolerance).
3. Watch trade journal for 1 week of `kind=auto_execute_audit` rows; if outcomes look sensible, leave on.
4. Rollback: set `OHMYSTOCK_AUTO_EXECUTE=false` in `.env.local`. No code rollback needed.

## Open Questions

- **Q1: Should `try_auto_execute` accept a list of `decision_id`s and process in batch?** → Defer to Phase 4 scheduler. v0 is one-at-a-time; the scheduler can loop.
- **Q2: Should sizing clamp be opt-out per call?** → No. The cheatsheet treats it as a hard rule, not a knob.
- **Q3: What user string should `confirm()` record when called by auto path?** → Hardcode `user="auto"` for v0. Differentiates from `"mark@local"` in queries.
