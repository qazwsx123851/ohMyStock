## 1. Decider snapshot — add `atr_14_pct` field

- [x] 1.1 Modify `src/ohmystock/decider/_journal_writer.py::write_entry_pending_confirm` to write `"atr_14_pct": entry_input.candidate.atr_14_pct` into payload (alongside the existing `current_price` snapshot)
- [x] 1.2 Update `tests/test_decider_orchestrator.py::test_enter_payload_contains_required_fields` `required_keys` to include `"atr_14_pct"` and assert `payload["atr_14_pct"] == <expected from fixture>`
- [x] 1.3 Run `uv run pytest tests/test_decider_orchestrator.py tests/test_cli_decide.py -q`; confirm green

## 2. Confirm Gate — backfill `atr_at_entry` + `stop_loss_price`

- [x] 2.1 Modify `src/ohmystock/safety/confirm_gate.py::confirm` to read `atr_14_pct` from payload (raise `ConfirmGateError(code="payload_invalid")` if missing) and compute `atr_at_entry = fill.fill_price * atr_14_pct / 100.0`, `stop_loss_price = max(fill.fill_price * 0.94, fill.fill_price - 2.0 * atr_at_entry)` after broker fill (per spec §6.6 normal-market case)
- [x] 2.2 Add the two computed values to the UPDATE payload in `_update_entry_payload` (alongside the existing 5 confirm fields)
- [x] 2.3 Update `tests/test_confirm_gate.py::test_confirm_success_updates_entry_and_returns_result`: extend `_seed_pending` to include `atr_14_pct=2.85`; add 2 new assertions on `atr_at_entry` (≈ 23.712) and `stop_loss_price` (≈ 784.576)
- [x] 2.4 Add new test `test_confirm_payload_invalid_when_missing_atr_14_pct`: seed payload without `atr_14_pct`, expect `ConfirmGateError(code="payload_invalid")`, message contains `"atr_14_pct"`, entry status remains `pending_confirm`
- [x] 2.5 Update existing `test_confirm_payload_missing_current_price_raises_payload_invalid` if needed (likely no change — separate field)
- [x] 2.6 Run `uv run pytest tests/test_confirm_gate.py tests/test_cli_confirm.py -q`; confirm green

## 3. Exit engine — pure function `evaluate_position`

- [x] 3.1 Create `src/ohmystock/exit_engine/__init__.py` with module docstring + spec link
- [x] 3.2 Create `src/ohmystock/exit_engine/evaluator.py` with imports + module docstring
- [x] 3.3 Define `ExitTag` (`Literal["hit_stop_loss","hit_t1","time_stop"]`), `ExitDecision` frozen dataclass, `ExitResult` frozen dataclass, `MarketDataLookup` Protocol per spec
- [x] 3.4 Implement `evaluate_position(entry_payload, close_price, asof_date) -> ExitDecision | None` per spec D5 decision tree (stop_loss → T1 → time_stop)
- [x] 3.5 Implement `_pnl(close, entry)` helper
- [x] 3.6 Define `ExitEngineError(Exception)` with `code: Literal["market_data_unavailable"]` and `failed_symbols: list[str]` attributes
- [x] 3.7 Write `tests/test_exit_engine.py::test_evaluate_position_*`: hit_stop_loss, hit_t1, time_stop, hold (None), stop+T1 prio (D5), missing-stop_loss_price ValueError, _pnl sign convention

## 4. Exit engine — orchestrator `evaluate_open_positions`

- [x] 4.1 Implement `evaluate_open_positions(conn, *, market_data, asof, clock, symbol_filter=None) -> list[ExitResult]` per spec
- [x] 4.2 Per-position transaction (`BEGIN IMMEDIATE` → INSERT kind=exit + UPDATE entry status=closed → COMMIT); collect failed_lookups for non-found close prices and raise `ExitEngineError` AFTER processing all rows (so successful rows have already committed)
- [x] 4.3 Re-export public symbols from `src/ohmystock/exit_engine/__init__.py`: `evaluate_position`, `evaluate_open_positions`, `ExitDecision`, `ExitResult`, `ExitTag`, `ExitEngineError`, `MarketDataLookup`
- [x] 4.4 Write `tests/test_exit_engine.py::test_evaluate_open_positions_*`: hit_t1 success (count + payload + entry status), hold (no row written), batch (one closed + one held), market_data unavailable raises ExitEngineError, already-closed entry skipped, symbol_filter narrows query
- [x] 4.5 Verify `kind=exit` row payload shape matches trade-journal-schema delta (exit_tag, exit_reason, actual_exit_price, pnl_pct, hold_days, exited_at, close_price_evaluated; no LLM cost fields)
- [x] 4.6 Run `uv run pytest tests/test_exit_engine.py -q`; confirm green

## 5. CLI — `ohmystock evaluate-exits` subcommand

- [x] 5.1 Create `src/ohmystock/cli/_evaluate_exits.py` with Typer command per spec table (`--asof`, `--symbol`, `--price`, `--db`, `--json`)
- [x] 5.2 Validate `--asof` parses as `date.fromisoformat(...)` (exit 2 on failure with helpful stderr)
- [x] 5.3 Validate `--price` requires `--symbol` (exit 2 with stderr `"--price requires --symbol"`)
- [x] 5.4 Build a `MarketDataLookup` either from `--price` override (single-symbol dict) or from `ohmystock.swarm._live_market` (default)
- [x] 5.5 Open SQLite via `Settings().ohmystock_db_path` (or `--db` override), `init_schema(conn)`, call `evaluate_open_positions(...)`, format output
- [x] 5.6 Implement exit code mapping: 0 success, 2 usage, 3 ExitEngineError; print failed symbols to stderr on engine error
- [x] 5.7 Implement `--json` output with `{asof, evaluated, exit_code}` shape; each evaluated dict contains `decision_id, action, exit_tag, actual_exit_price, pnl_pct, hold_days`
- [x] 5.8 Register `evaluate-exits` in `src/ohmystock/cli/__init__.py` with help text containing literals `kind=exit`, `closed`, `hit_stop_loss`, `hit_t1`, `time_stop`
- [x] 5.9 Verify `uv run ohmystock evaluate-exits --help` shows all flags + lifecycle literals

## 6. CLI tests

- [x] 6.1 Create `tests/test_cli_evaluate_exits.py` using Typer `CliRunner` + monkeypatch
- [x] 6.2 Cover all 9 scenarios in `cli-and-config` delta spec (help, missing --asof exit 2, invalid date exit 2, --price without --symbol exit 2, hit_t1 success exit 0, 0-closed exit 0, mixed closed+held exit 0, market_data unavailable exit 3, --json output)
- [x] 6.3 Verify each test asserts exit code AND stdout/stderr substring (per scenario "THEN" clause)

## 7. Documentation

- [x] 7.1 Append a row to `CLAUDE.md` §5 唯一權威表: `Exit Engine v0 行為 → openspec/specs/exit-engine/spec.md (archive 後) + src/ohmystock/exit_engine/evaluator.py`
- [x] 7.2 Add a one-line note to `docs/design-zh-TW.md` near §4.10.3 Confirm Gate paragraph: `Exit Engine v0 (daily, full-position close on stop/T1/time_stop) 已實作於 ohmystock.exit_engine.evaluator；partial fills + Chandelier 待 Phase 4 position-tranches change。`
- [x] 7.3 Update `docs/llm-decision-schema.md` §4.2 metadata block: add one-liner that `actual_exit_price`, `pnl_pct`, `hold_days`, `exit_tag`, `exited_at`, `close_price_evaluated` 由 exit-engine v0 寫入；v0 三標籤 `hit_stop_loss / hit_t1 / time_stop` 為實作子集，其餘四標籤 `hit_t1_5 / chandelier / thesis_invalid / discretionary` 為 Phase 4+ 預留
- [x] 7.4 Update `docs/llm-decision-schema.md` §4.1: note that `atr_14_pct` is a new entry-payload snapshot field (decider writes), `atr_at_entry` + `stop_loss_price` are now non-null after confirm

## 8. Final validation

- [x] 8.1 Run `make test`; all tests pass (existing 641 + ~25 new) — actual: 671 passed (+30)
- [x] 8.2 Run `openspec validate exit-engine-v0 --strict`; verify pass
- [x] 8.3 Run `openspec status --change exit-engine-v0 --json`; confirm 4/4 artifacts done
- [ ] 8.4 Manual smoke (deferred — needs ANTHROPIC_API_KEY + a confirmed position): `ohmystock decide ... → ohmystock confirm <id> → ohmystock evaluate-exits --asof <date> --symbol XXXX --price <close>` end-to-end

## 9. OpenSpec archive

- [ ] 9.1 After all tasks pass, prompt user to run `/opsx:archive exit-engine-v0` to fold deltas into `openspec/specs/`
