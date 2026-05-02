## Why

Confirm Gate v0 ships as **human-only** — every LLM-decided entry sits in `pending_confirm` until I press confirm in CLI/UI. That is the right default, but cheatsheet §6.7 / safety §2.9 always called for a Mode B (`OHMYSTOCK_AUTO_EXECUTE=true`) where the gate auto-confirms when five hard breakers all pass and falls back to the human queue when any breaker trips. This change closes Phase 3.5 by adding that toggle and the breakers, on top of the just-shipped confirm-gate-v0 and entry-decider-pm-node.

Without this, every LLM signal still requires me-in-the-loop, which defeats the whole "agent runs unattended in sim mode" point of the project.

## What Changes

- New module `ohmystock.safety.auto_execute` exposing `try_auto_execute(...) -> AutoExecuteResult` (one decision per pending_confirm entry; calls `confirm(...)` on pass, leaves the row pending and writes an audit row on any breaker fallback).
- Five hard breakers per safety §2.9 / cheatsheet §6.7:
  1. `OHMYSTOCK_AUTO_EXECUTE=true` (default `false` — when off, every call is a fallback with `outcome="flag_off"`).
  2. LLM `confidence >= 0.7` (read from latest entry payload `llm_confidence`).
  3. Daily LLM-decided executed count `< 5` (count of `kind=entry` rows where `auto_executed=true` and `human_confirmed_at` falls within today TPE midnight → now).
  4. Single-order notional `<= account_equity_twd * 0.25` (notional = `qty * current_price`, computed with the same `_compute_qty` rule as confirm-gate).
  5. Loss-streak lockout: if 3 most recent closed exits (kind=exit, source=auto) all show `realized_pnl_pct < -0.05`, lock out for 24h after the last exit's `closed_at`.
- Sizing-deviation clamp (NOT a fallback): if `final_sizing_pct` deviates from `system_sizing_pct` by `> 30%`, clamp `final_sizing_pct` to `min(final_sizing_pct, system_sizing_pct)` before computing qty. Audit row records both raw and clamped values.
- New settings field `OHMYSTOCK_AUTO_EXECUTE: bool = False` (pydantic-settings, env-driven, validator forbids `true` when `OHMYSTOCK_BROKER == "shioaji-live"`).
- New trade-journal kind `kind="auto_execute_audit"` recording every fallback (`pass | flag_off | low_confidence | daily_limit | notional_limit | loss_lockout | live_broker | sizing_clamped`). Pass-with-clamp writes one audit row alongside the normal confirm path.
- Confirmed entries gain payload field `auto_executed: bool` (true when entered via auto path, false when entered via human `confirm()`).
- **No CLI / EventBus / web-admin work in this change** — those land later in Phase 4. Auto-execute is invokable as a Python function only; a tiny `apscheduler`-style runner can be wired up afterward.

## Capabilities

### New Capabilities
- `auto-execute`: hard-breaker gate that promotes a `pending_confirm` entry to `confirmed` without human input when all five breakers pass; otherwise leaves the row pending and writes an audit trail. Live-broker mode is a hard short-circuit even if the flag is on.

### Modified Capabilities
- `confirm-gate`: extend `confirm(...)` to accept an `auto_executed: bool = False` flag (defaults to current behavior — human confirm sets `auto_executed=False`); add the new payload field to the entry-status update set; re-export `try_auto_execute` from `ohmystock.safety` for symmetry. No human-flow scenarios change.
- `entry-decider`: extend the entry payload written by `decide_entry` to include `system_sizing_pct` (already computed by `validate_decider_output`'s overrides path but currently dropped). Required so the auto-execute breaker can detect / clamp deviations without re-computing the §2.1 covenant. No decider scenarios change other than the additional payload field.

## Impact

- **Code**:
  - `src/ohmystock/safety/auto_execute.py` (new, ~250 lines)
  - `src/ohmystock/safety/__init__.py` (re-export)
  - `src/ohmystock/safety/confirm_gate.py` (`auto_executed` parameter on `confirm()`; payload field added)
  - `src/ohmystock/decider/_journal_writer.py` (write `system_sizing_pct` into entry payload)
  - `src/ohmystock/config/settings.py` (`OHMYSTOCK_AUTO_EXECUTE` field + `model_validator` cross-check vs broker mode)
  - `tests/safety/test_auto_execute.py` (new)
- **Schema**:
  - Trade journal: new `kind="auto_execute_audit"` rows. Schema is JSON payload-only — no migration needed.
  - Entry payload: two new fields (`auto_executed`, `system_sizing_pct`). Backwards-compatible (older rows simply lack them).
- **Docs**:
  - `docs/llm-decision-schema.md` §4 — list new payload fields and the new `kind`.
  - `docs/safety-and-simulation.md` §2.9 — link to spec for the breaker thresholds (now a code SSOT).
- **Out of scope (deferred)**:
  - CLI command `ohmystock auto-execute --run` and APScheduler job — Phase 4 (`backend-eventbus-mvp` will own job orchestration).
  - EventBus emission for audit rows — Phase 4.
  - Email/Telegram alert on fallback — Phase 4 (uses notify channel from `notifications` capability not yet specced).
- **No live trading impact**: the validator forbids the flag in live mode, and `try_auto_execute` short-circuits to fallback if `broker.is_simulation` is False.
