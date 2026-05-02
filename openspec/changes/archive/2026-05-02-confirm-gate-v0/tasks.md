## 1. Paper broker shim

- [x] 1.1 Create `src/ohmystock/paper/broker.py` with `PaperBroker` Protocol, `Fill` frozen dataclass, `BrokerError` exception, and `FakePaperBroker(clock, raise_on_submit=False)` default impl
- [x] 1.2 Re-export `PaperBroker`, `FakePaperBroker`, `Fill`, `BrokerError` from `src/ohmystock/paper/__init__.py` (preserve existing `shioaji_client` exports)
- [x] 1.3 Write `tests/test_paper_broker.py`: FakePaperBroker normal fill (matches Fill scenario in spec), `raise_on_submit=True` → BrokerError, `Fill.fill_ts` matches injected clock
- [x] 1.4 Run `make test` and confirm new tests pass; existing tests unchanged

## 2. Settings + .env.example

- [x] 2.1 Add `ohmystock_confirm_timeout_minutes: int = 30` and `ohmystock_default_capital_twd: int = 1_000_000` to `src/ohmystock/config.py:Settings` with `field_validator` enforcing `> 0`
- [x] 2.2 Append two lines to `.env.example` under a new `# --- Confirm Gate v0 ---` section: `OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES=30` and `OHMYSTOCK_DEFAULT_CAPITAL_TWD=1000000`
- [x] 2.3 Extend `tests/test_cli.py` settings cases: defaults, env override, ≤0 ValidationError for both new fields (5 new test cases minimum)
- [x] 2.4 Run `make test`; confirm new + existing settings tests pass

## 3. Confirm gate core — clock, errors, dataclasses

- [x] 3.1 Create `src/ohmystock/safety/confirm_gate.py` with module docstring + spec link
- [x] 3.2 Add `Clock` Protocol + `_SystemClock` + `system_clock` (TZ `+08:00`, mirror `decider/orchestrator.py:40-56` pattern; consider sharing if duplicate ≥3 places)
- [x] 3.3 Define `ConfirmGateError(Exception)` with `code: Literal[...]` and `cause: Exception | None` attributes
- [x] 3.4 Define `ConfirmResult`, `RejectResult`, `PendingEntry` frozen dataclasses per spec field list

## 4. Confirm gate — confirm() function

- [x] 4.1 Implement `confirm(conn, *, decision_id, broker, default_capital_twd, user, clock) -> ConfirmResult` per spec steps 1-9 (`BEGIN IMMEDIATE` → SELECT → status check → qty calc → broker submit → UPDATE → COMMIT)
- [x] 4.2 Implement helper `_compute_qty(default_capital_twd, final_sizing_pct, current_price) -> int` with `max(1000, floor(...) * 1000)` formula
- [x] 4.3 Implement helper `_update_entry_payload(conn, decision_id, updates: dict) -> None` that merges JSON via `json_set` or `json_patch` (Python-side merge → write back is fine; SQLite json1 also OK)
- [x] 4.4 Write `tests/test_confirm_gate.py::test_confirm_*`: success path (5 sub-checks per spec scenario "confirm 成功"), not_found, not_pending (status=confirmed), broker_failed (rollback verified), payload_invalid
- [x] 4.5 Write parametrized `tests/test_confirm_gate.py::test_compute_qty` covering the three qty scenarios in spec (16.5%×1M/832, 16.5%×1M/100, 25%×1M/50)

## 5. Confirm gate — reject() function

- [x] 5.1 Implement `reject(conn, *, decision_id, reason, user, clock) -> RejectResult` per spec steps 1-5 (`BEGIN IMMEDIATE` → SELECT → status check → INSERT kind=reject → UPDATE entry status → COMMIT)
- [x] 5.2 Add empty-`reason` ValueError guard at function entry (before opening transaction)
- [x] 5.3 Reject-row payload shape per `trade-journal-schema` delta: `decision_status="rejected"`, `reject_layer="human"`, `reject_reason`, `rejected_by`, `rejected_at`; **no LLM cost fields**
- [x] 5.4 Write `tests/test_confirm_gate.py::test_reject_*`: success (count + payload + entry status), not_pending, empty-reason ValueError

## 6. Confirm gate — sweep_expired() function

- [x] 6.1 Implement `sweep_expired(conn, *, timeout_minutes, clock) -> list[str]` per spec steps 1-5
- [x] 6.2 Add `timeout_minutes <= 0` ValueError guard at function entry
- [x] 6.3 Use `datetime.fromisoformat(created_at)` + UTC compare to avoid TZ off-by-eight bugs
- [x] 6.4 Expire-row payload shape per `trade-journal-schema` delta: `decision_status="expired"`, `expire_reason="confirm timeout after <N> minutes"`, `expired_at`
- [x] 6.5 Write `tests/test_confirm_gate.py::test_sweep_*`: expired single, untouched-when-not-expired, batch of 3 expired, idempotent (second sweep is no-op), ValueError on `timeout_minutes=0` and `-5`

## 7. Confirm gate — list_pending() function

- [x] 7.1 Implement `list_pending(conn, *, clock, timeout_minutes) -> list[PendingEntry]` ordered by `created_at` ASC
- [x] 7.2 Compute `age_seconds`/`ttl_seconds` from clock + created_at; allow negative TTL for expired-but-not-swept rows
- [x] 7.3 Re-export `confirm`, `reject`, `sweep_expired`, `list_pending`, dataclasses, `ConfirmGateError`, `Clock`, `system_clock` from `src/ohmystock/safety/__init__.py`
- [x] 7.4 Write `tests/test_confirm_gate.py::test_list_pending_*`: two-row order check (10:00 before 10:10), no-results-for-confirmed/rejected/expired

## 8. decide_entry payload — add `current_price` snapshot field

- [x] 8.1 Modify `src/ohmystock/decider/_journal_writer.py::write_entry_pending_confirm` to write `current_price` from `entry_input.candidate.current_price` into the payload
- [x] 8.2 Update `tests/test_decider_orchestrator.py` payload assertions to include `current_price` field
- [x] 8.3 Update relevant assertion in `tests/test_cli_decide.py` if it inspects the payload (n/a — CLI test only inspects stdout JSON)

## 9. CLI — `ohmystock confirm` subcommand

- [x] 9.1 Create `src/ohmystock/cli/_confirm.py` with Typer `confirm` command supporting all flags from spec table
- [x] 9.2 Implement mutually-exclusive validation (`--list` ⊕ `<decision_id>` ⊕ `--sweep-expired`); use Typer callback or pre-check
- [x] 9.3 Implement OHMYSTOCK_AUTO_EXECUTE warning to stderr (one-line, exact message from spec)
- [x] 9.4 Implement exit code mapping: `0` for confirm/list/sweep success, `1` for reject success, `2` for not_found/not_pending/usage error, `3` for broker_failed
- [x] 9.5 Implement `--json` output: dict with `action`, `decision_id`, `fill`/`reject`/`expire`/`pending` payload, `exit_code`
- [x] 9.6 Register `confirm` in `src/ohmystock/cli/__init__.py`; ensure root help and `confirm --help` contain `pending_confirm` and `expire` literals

## 10. CLI tests

- [x] 10.1 Create `tests/test_cli_confirm.py` using Typer `CliRunner` + monkeypatch
- [x] 10.2 Cover all 11 scenarios in `cli-and-config` delta spec (help, list, confirm-success, reject-success, not_found, broker_failed, sweep with results, sweep empty, mutually-exclusive, AUTO_EXECUTE warning, --json)
- [x] 10.3 Verify each test asserts exit code AND stdout/stderr substring (per scenario "THEN" clause)

## 11. Documentation

- [x] 11.1 Append a row to `CLAUDE.md` §5 唯一權威表: `Confirm Gate v0 行為 → openspec/specs/confirm-gate/spec.md (archive 後) + src/ohmystock/safety/confirm_gate.py`
- [x] 11.2 Add a one-line note to `docs/design-zh-TW.md` §4.10.3 Confirm Gate paragraph: `Confirm Gate v0 (human-only) 已實作於 ohmystock.safety.confirm_gate；auto 模式 + 防線 9 待 Phase 3.5。`
- [x] 11.3 Update `docs/llm-decision-schema.md` §4.1 metadata block: add one-liner that `actual_entry_price`, `actual_qty`, `human_confirmed_by`, `human_confirmed_at` 由 confirm-gate 寫入

## 12. Final validation

- [x] 12.1 Run `make test`; all tests pass (641 passed, 1 warning — was 573 before; +68 new tests)
- [x] 12.2 Run `openspec validate confirm-gate-v0 --strict`; verify pass — "Change 'confirm-gate-v0' is valid"
- [x] 12.3 Run `openspec status --change confirm-gate-v0 --json`; 4/4 artifacts done, isComplete=true
- [ ] 12.4 Manual smoke (deferred — needs ANTHROPIC_API_KEY and trading day): `ohmystock decide --symbol 2330 --asof <date>` then `ohmystock confirm --list` and `ohmystock confirm <id>` end-to-end

## 13. OpenSpec archive

- [ ] 13.1 After all tasks pass, prompt user to run `/opsx:archive confirm-gate-v0` to fold deltas into `openspec/specs/`
