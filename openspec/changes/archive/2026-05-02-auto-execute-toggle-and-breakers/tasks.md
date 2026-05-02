## 1. Settings layer (defense-in-depth, layer 1)

- [x] 1.1 Add 8 `OHMYSTOCK_AUTO_EXECUTE*` fields to `src/ohmystock/config.py` with defaults from cheatsheet §6.7 (also added `ohmystock_broker` Literal, replaced previous `str|None` placeholder for `ohmystock_auto_execute` with typed `bool`)
- [x] 1.2 Add `forbid_auto_execute_in_live` `model_validator(mode="after")` raising `RuntimeError` on `auto_execute=true + broker=shioaji-live`
- [x] 1.3 Write `tests/test_settings_auto_execute.py` covering: defaults, sim+true OK, mock+true OK, live+true raises, live+false OK, env override roundtrip, invalid broker, non-positive int rejection
- [x] 1.4 Run `pytest tests/test_settings_auto_execute.py` — all 11 green

## 2. entry-decider delta: write `system_sizing_pct`

- [x] 2.1 Modify `src/ohmystock/decider/_journal_writer.py` `write_entry_pending_confirm`: add `"system_sizing_pct": 10.0 if raw.stage == 3 else 25.0` to payload dict
- [x] 2.2 Add 4 new scenarios to `tests/test_decider_orchestrator.py`: stage=2 → 25.0, stage=3 no-cap → 10.0, stage=3 capped → still 10.0, reject row missing field
- [x] 2.3 Run `pytest tests/test_decider_orchestrator.py` — all 16 green (12 existing + 4 new)

## 3. confirm-gate delta: `auto_executed` parameter

- [x] 3.1 Modify `src/ohmystock/safety/confirm_gate.py` `confirm()` signature: add `auto_executed: bool = False` keyword-only param
- [x] 3.2 In step 9 of `confirm()`, add `"auto_executed": auto_executed` to the `updates` dict passed to `_update_entry_payload`
- [x] 3.3 Add 2 new scenarios to `tests/test_confirm_gate.py`: default writes `auto_executed=False`, explicit `True` writes `auto_executed=True`
- [x] 3.4 Run `pytest tests/test_confirm_gate.py` — all 24 green (22 existing + 2 new)

## 4. auto-execute module: scaffold

- [x] 4.1 Create `src/ohmystock/safety/auto_execute.py` with module docstring, imports, `_TPE_TZ`, `system_clock`, and exception class `AutoExecuteError(code, message, cause=None)`
- [x] 4.2 Define `AutoExecuteOutcome` Literal and frozen dataclass `AutoExecuteResult(decision_id, outcome, confirm_result, evidence)`
- [x] 4.3 Define helper `_system_sizing_pct(stage: int) -> float` returning `10.0 if stage == 3 else 25.0` (matches the decider stub for round-trip consistency)
- [x] 4.4 Define helper `_today_tpe_midnight_iso(now_iso: str) -> str` for the daily-limit query bounds
- [x] 4.5 Add module to `src/ohmystock/safety/__init__.py` re-exports
- [x] 4.6 Extend `journal_entries` CHECK constraint in `src/ohmystock/journal/schema.py` to include `auto_execute_audit`; add one-shot migration for existing legacy DBs

## 5. auto-execute module: entry parsing + audit writer

- [x] 5.1 Implement `_parse_pending_entry(conn, decision_id)`; raises `AutoExecuteError(code="not_found"|"not_pending"|"payload_invalid")` per spec
- [x] 5.2 Implement `_write_audit(conn, *, decision_id, symbol, outcome, evidence, clock)` inserting `kind=auto_execute_audit` row with payload structure from spec
- [x] 5.3 (Helpers covered indirectly by E2E tests in §7; no separate helper test file added — evidence still surfaces in audit-row assertions)

## 6. auto-execute module: 5 breakers + sizing clamp + confirm

- [x] 6.1 Implement `try_auto_execute(conn, *, decision_id, broker, settings, clock)` skeleton calling step 1 (parse entry)
- [x] 6.2 Add breaker 2 (`flag_off`): check `settings.ohmystock_auto_execute`, write audit, return on fallback
- [x] 6.3 Add breaker 3 (`live_broker`): check `settings.ohmystock_broker`, write audit, return on fallback
- [x] 6.4 Add breaker 4 (`low_confidence`): compare payload `llm_confidence` to settings threshold
- [x] 6.5 Add breaker 5 (`notional_limit`): reuse `confirm_gate._compute_qty`, compute notional, compare to equity*pct
- [x] 6.6 Add breaker 6 (`daily_limit`): SQL `COUNT` over today TPE window, compare to settings limit
- [x] 6.7 Add breaker 7 (`loss_lockout`): SELECT last 3 `kind=exit source=auto`, check 3-streak below threshold AND lockout window still active
- [x] 6.8 Add sizing clamp logic (step 8 in spec): compute deviation, if > threshold UPDATE entry payload `final_sizing_pct = min(...)` and label outcome `sizing_clamped_then_pass`
- [x] 6.9 Call `confirm(conn, ..., auto_executed=True, user="auto", clock=clock)`; on `ConfirmGateError` raise `AutoExecuteError(code="confirm_failed", cause=e)` without writing audit
- [x] 6.10 On confirm success, write audit row with full evidence dict; return `AutoExecuteResult`

## 7. auto-execute module: end-to-end tests

- [x] 7.1 Create `tests/test_auto_execute.py` with shared fixtures: in-memory SQLite with `init_schema`, `_FakeClock`, helpers `_seed_pending` / `_seed_auto_executed_entry` / `_seed_auto_exit` / `_audit_rows` / `_entry_status`
- [x] 7.2 Test `flag_off` scenario — audit row exists, entry still pending
- [x] 7.3 Test `live_broker` scenario — runtime mutation of `ohmystock_broker` to `shioaji-live`; redundant breaker fires
- [x] 7.4 Test `low_confidence` scenario — payload `llm_confidence=0.62`
- [x] 7.5 Test `notional_limit` scenario — set `max_notional_pct=0.20` to force trigger; assert audit evidence numeric
- [x] 7.6 Test `daily_limit` scenario — seed 5 prior `auto_executed=true` entries today, then attempt 6th
- [x] 7.7 Test `loss_lockout` scenario — seed 3 `kind=exit source=auto` rows pnl<-5%, recent `closed_at`; assert lockout_until ISO
- [x] 7.8 Test `loss_lockout` does NOT trigger when only 2 exits exist — outcome `pass`, entry confirmed
- [x] 7.9 Test `pass` scenario — all breakers OK, entry confirmed, `auto_executed=True`, `human_confirmed_by="auto"`, audit written
- [x] 7.10 Test `sizing_clamped_then_pass` scenario — stage=3 + `final_sizing_pct=20` → clamped to 10
- [x] 7.11 Test `not_pending` raises and writes no audit
- [x] 7.12 Test `not_found` raises and writes no audit
- [x] 7.13 Test `payload_invalid` (missing `stage`) raises and writes no audit
- [x] 7.14 Test `confirm_failed` (FakePaperBroker raise_on_submit=True) raises and writes no audit; entry stays pending

## 8. Integration smoke test + linting

- [x] 8.1 Run full `pytest` suite — 701 tests passing, no regressions in entry-decider / confirm-gate / exit-engine / journal schema
- [x] 8.2 Run `openspec validate auto-execute-toggle-and-breakers --strict` — change reports valid
- [x] 8.3 Type-check via the smoke import (no mypy/ruff configured in pyproject.toml; `from ohmystock.safety import try_auto_execute, ...` succeeds at runtime, which exercises module-level type annotations under Python 3.14)
- [x] 8.4 Manual sanity check: `python -c "from ohmystock.safety import try_auto_execute, AutoExecuteResult, AutoExecuteOutcome, AutoExecuteError; print('ok')"` — prints `ok`

## 9. Docs sync (lightweight)

- [x] 9.1 Update `docs/llm-decision-schema.md` §4.4.1 — added `kind=auto_execute_audit` row spec with payload structure, evidence-key matrix, and the two new entry-payload fields (`system_sizing_pct`, `auto_executed`)
- [x] 9.2 Update `docs/safety-and-simulation.md` §2.9 — added trailing SSOT pointer paragraph linking to `openspec/specs/auto-execute/spec.md` and the Settings field family
- [x] 9.3 Update `CLAUDE.md` §5 唯一權威表 — added row "Auto-execute Phase 3.5 — breaker thresholds + audit row format" pointing to spec + module + Settings
