## Why

Phase 3 PM Conclusion node now writes `kind=entry` rows with `decision_status="pending_confirm"`, but **nothing consumes them** — there is no path from "LLM said enter" to a paper broker fill. Without a confirm gate, the system cannot complete a single end-to-end trade and Phase 3's "LLM Decider + Confirm Gate + Trade Journal v3" goal stays half-done.

This change ships the **human-mode** half (`OHMYSTOCK_AUTO_EXECUTE=false` path) so a single trade can be walked through manually: signal → LLM enter → `ohmystock confirm` → paper broker fill → journal updated. The `auto` mode + 9-line breaker is explicitly deferred to Phase 3.5; the Risk Gate module and real Shioaji wiring are deferred to their own changes.

## What Changes

- Add `ohmystock.safety.confirm_gate` module with three pure functions (`confirm`, `reject`, `sweep_expired`) operating on a SQLite connection — atomic per call, no I/O outside the broker shim.
- Add `ohmystock.paper.broker` minimal shim: `PaperBroker` Protocol + `FakePaperBroker` (deterministic fill at candidate snapshot price) + `Fill` dataclass. Real Shioaji simulator wiring is **out of scope**.
- Add `ohmystock confirm` Typer subcommand with three actions: `--list` (show pending with TTL), `<decision_id>` (confirm + fill), `<decision_id> --reject [--reason ...]` (human reject), `--sweep-expired` (write `kind=expire` rows for any pending > timeout).
- Extend `kind=entry` payload lifecycle: introduce `decision_status ∈ {pending_confirm, confirmed, rejected, expired}` transitions, plus snapshot fields written at confirm time (`actual_entry_price`, `actual_qty`, `human_confirmed_by`, `human_confirmed_at`).
- Define `kind=reject` `reject_layer="human"` payload shape (new sibling to existing `reject_layer="llm"`).
- Define `kind=expire` payload shape (Requirement already mentions the kind value but no payload spec exists).
- Add config keys `OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES` (default `30`) and `OHMYSTOCK_DEFAULT_CAPITAL_TWD` (default `1_000_000`, used to translate `final_sizing_pct` → qty until Sizing Service ships). Live mode (`OHMYSTOCK_LIVE_MODE=true`) SHALL refuse to load this gate — guarded explicitly.

## Capabilities

### New Capabilities
- `confirm-gate`: human-mode confirm gate that consumes `pending_confirm` entries, calls the paper broker, and persists fill / reject / expire transitions atomically. Defines the `PaperBroker` Protocol contract and the deterministic `FakePaperBroker` used as the Phase 3 default.

### Modified Capabilities
- `trade-journal-schema`: extend `kind=entry` payload requirement with the four `decision_status` lifecycle transitions and the four confirm-time snapshot fields (`actual_entry_price`, `actual_qty`, `human_confirmed_by`, `human_confirmed_at`); add new requirement for `kind=reject` `reject_layer="human"` payload shape; add new requirement for `kind=expire` payload shape (the kind value is already in the CHECK constraint but no payload contract exists).
- `cli-and-config`: add `ohmystock confirm` subcommand (with `--list`, `<decision_id>`, `--reject`, `--sweep-expired` flags); add two new `Settings` fields (`ohmystock_confirm_timeout_minutes`, `ohmystock_default_capital_twd`); add live-mode guard that rejects loading the confirm gate when `OHMYSTOCK_LIVE_MODE=true`.

## Impact

- **Code (new):** `src/ohmystock/safety/confirm_gate.py`, `src/ohmystock/paper/broker.py`, `src/ohmystock/cli/_confirm.py`, `tests/test_confirm_gate.py`, `tests/test_paper_broker.py`, `tests/test_cli_confirm.py`.
- **Code (modified):** `src/ohmystock/cli/__init__.py` (register subcommand), `src/ohmystock/config.py` (two new fields), `.env.example` (two new lines), `tests/test_cli.py` (settings env coverage).
- **Schema:** No SQLite DDL changes — `kind=entry/reject/expire` are already valid in the CHECK constraint and the payload is JSON. Existing `init_schema(conn)` keeps working untouched.
- **Docs:** `docs/llm-decision-schema.md` already specifies the lifecycle (§4.1 / §4.3 / §4.4) — no doc edits needed beyond a one-line implementation pointer in CLAUDE.md §5.
- **Deferred (explicitly out of scope):** auto-execute mode (Phase 3.5 — needs the 9-line breaker), Risk Gate module (separate change), specialist swarm DAG (separate change), real Shioaji simulator wiring (separate change), `/api/decisions/{id}/confirm` REST endpoint (Phase 4 — web-admin).
- **Risk:** Low. Pure SQLite UPDATE / INSERT inside transactions; no live-broker path; no money movement; gated against `OHMYSTOCK_LIVE_MODE=true`.
