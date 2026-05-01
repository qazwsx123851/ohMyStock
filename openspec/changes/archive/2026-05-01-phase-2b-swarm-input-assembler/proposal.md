## Why

Phase 2B scoring now produces ranked `Phase2BCandidate` rows (≥ 65 final_score), but `entry_decision_team` swarm has no formal way to consume them. Today every LLM node would have to re-fetch market state, portfolio state, and cheatsheet rules independently — duplicating tool calls and risking context drift between bull/bear/rule_checker/risk_simulator/PM nodes. We need one deterministic assembler that produces the exact `EntryDecisionInput` JSON defined in `docs/llm-decision-schema.md` §1, shared across all nodes, before Phase 3 LLM Decider can be wired up.

## What Changes

- Add `src/ohmystock/swarm/runner.py::build_entry_decision_input()` — single entry point that converts `Phase2BCandidate` + portfolio + market + cheatsheet rules digest into a v3.1-compliant `EntryDecisionInput` payload.
- Add `src/ohmystock/decider/models.py` (or `swarm/models.py`) Pydantic contracts for `EntryDecisionInput`, `CandidateSnapshot`, `MarketContext`, `RulesDigest` — strictly mirroring `llm-decision-schema.md` §1 (v3.1 includes SEPA fields: `stage`, `rs_percentile`, `trend_template_passed`, `vcp_quality`, `pivot_price`).
- Add a `RulesDigest` loader that extracts must-have / bonus / sizing-formula references from `docs/workflow-cheatsheet.md` §6.3 / §6.4 / §6.6 — cached at startup so we don't reparse on every candidate.
- Add a `MarketSnapshot` adapter (TAIEX index state + risk-off preview from `strategies/risk_gate.py`) and a `PortfolioSnapshot` adapter (sector exposure + total exposure + same-sector count) — both consumable by the assembler without forcing each LLM node to call tools.
- Compute `consecutive_loss_streak` and `recent_20_winrate` from `trade_journal_tool` so the assembler ships them in `market_context` rather than asking each node to query the journal.
- Discover `available_tools` from the tool registry and `available_skills` from skill YAML frontmatter — frozen into the payload so node selection sees the same option list.
- Provide a contract test suite that round-trips real Phase 2B candidates through the assembler and validates against `EntryDecisionInput` with `pydantic`, plus a snapshot test pinning the JSON shape to `llm-decision-schema.md` §1.
- Surface a CLI command (`oms assemble-entry-input <symbol|candidate-id>`) that emits the assembled JSON for offline inspection / fixture capture.

## Capabilities

### New Capabilities
- `swarm-input-assembler`: defines `build_entry_decision_input()`, the input contracts (`EntryDecisionInput` and dependencies), the cheatsheet rules digest source-of-truth, and the assembler's behavioural requirements (idempotency, schema strictness, deterministic ordering of `existing_positions`, error handling when upstream snapshots are missing).

### Modified Capabilities
- `phase-2b-scoring-engine`: append a requirement that `Phase2BCandidate.final_score ≥ 65` rows MUST be exposable via a stable iterator/repository surface that the assembler can consume — no field additions, but pinning the consumption contract.

## Impact

- **Code**:
  - New: `src/ohmystock/swarm/runner.py`, `src/ohmystock/swarm/_input_assembler.py`, `src/ohmystock/swarm/_rules_digest.py`, `src/ohmystock/decider/models.py` (or `swarm/models.py`), CLI subcommand under `src/ohmystock/cli/`.
  - Touches: `src/ohmystock/scoring/__init__.py` (export candidate iterator), `src/ohmystock/strategies/risk_gate.py` (expose `evaluate_preview()` if not present), `src/ohmystock/journal/*` (add `recent_winrate` / `consecutive_loss_streak` query helpers), `src/ohmystock/tools/_registry.py` (add `list_registered()` if needed).
- **APIs**: no REST endpoints in this slice — Phase 3 (`/api/decisions`) consumes the assembler later.
- **Dependencies**: no new third-party packages; uses existing `pydantic`, repo-internal scoring / portfolio / journal modules.
- **Specs**: new authority `swarm-input-assembler` spec; minor delta to `phase-2b-scoring-engine` for the consumption contract.
- **Docs**: `docs/design-zh-TW.md` §4.7.0 already declares this section the SSOT — once shipped, archive will sync the spec back into `openspec/specs/`.
- **Risks**: assembler must stay strictly in lockstep with `llm-decision-schema.md` §1; any drift breaks Phase 3 contract tests. Mitigated by snapshot tests and pinning the schema version (`input_schema_version: v3.1`).
