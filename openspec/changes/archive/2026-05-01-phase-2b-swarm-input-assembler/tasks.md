## 1. Pydantic models and exceptions

- [x] 1.1 Create `src/ohmystock/swarm/models.py` with `CandidateSnapshot`, `ExistingPosition`, `MarketContext`, `RulesDigest`, `EntryDecisionInput` matching `docs/llm-decision-schema.md` §1 (v3.1) — with `model_config = ConfigDict(extra="forbid")` so unknown fields raise.
- [x] 1.2 Add SEPA-field validators to `CandidateSnapshot`: enforce `stage ∈ {1,2,3,4}`, `rs_percentile ∈ [0,99]`, `trend_template_passed ∈ [0,8]`, `vcp_quality ∈ {none,forming,textbook,breakout}`, and the `pivot_price ⇔ vcp_quality` invariant.
- [x] 1.3 Add `class AssemblerInputError(Exception)` and `class RulesDigestError(Exception)` in `src/ohmystock/swarm/_errors.py`; re-export from `src/ohmystock/swarm/__init__.py`.
- [x] 1.4 Add unit tests `tests/test_swarm_models.py`: round-trip the literal JSON example from `docs/llm-decision-schema.md` §1 through `EntryDecisionInput.model_validate_json`; assert SEPA-field validators reject each bad case (one test per scenario in `specs/swarm-input-assembler/spec.md`).

## 2. RulesDigest source file and loader

- [x] 2.1 Create `docs/_rules_digest.json` with the 3 SEPA must-have items (cheatsheet §6.3) and 8 bonus items (§6.4) — copy phrasing from `docs/llm-decision-schema.md` §1 example.
- [x] 2.2 Implement `ohmystock.swarm.load_rules_digest()` in `src/ohmystock/swarm/_rules_digest.py`: reads `docs/_rules_digest.json`, validates `len(must_have) == 3` and `len(bonus_items) == 8`, returns `RulesDigest`. Raise `RulesDigestError` on missing file, invalid JSON, or count mismatch.
- [x] 2.3 Add `scripts/build_rules_digest.py` (one-shot, not in production path): a stub script that documents the manual process for regenerating the digest from cheatsheet edits.
- [x] 2.4 Add unit tests `tests/test_rules_digest.py`: valid load, missing file, malformed JSON, wrong must-have count, wrong bonus count.

## 3. Adapters (Protocols + default implementations)

- [x] 3.1 In `src/ohmystock/swarm/_adapters.py`, define `MarketSnapshotProvider`, `PortfolioSnapshotProvider`, `JournalStatsProvider` as `typing.Protocol` classes with the methods called out in `design.md` §D3.
- [x] 3.2 Define data classes `MarketSnapshot`, `PortfolioSnapshot` in `_adapters.py` carrying the raw fields needed (TAIEX index state, risk_off boolean, positions list with sector/exposure, monthly_pnl_pct).
- [x] 3.3 Implement default `LiveMarketSnapshotProvider` wrapping `market_data_tool.get_index("TAIEX")` and `strategies.risk_gate.evaluate_preview()` — returns `MarketSnapshot` (NotImplementedError stub per user direction).
- [x] 3.4 Implement default `LivePortfolioSnapshotProvider` wrapping `portfolio_tool.get_positions()` plus sector lookup via `chip_data_tool` cached metadata; raise on missing sector (NotImplementedError stub per user direction).
- [x] 3.5 Implement default `LiveJournalStatsProvider` wrapping `trade_journal_tool.query` with helpers `recent_winrate(n)` and `consecutive_loss()` (NotImplementedError stub per user direction).
- [x] 3.6 Add tests `tests/test_swarm_adapters.py` using fakes that monkeypatch the underlying tools with envelope-shaped return values.

## 4. Tool and skill discovery

- [x] 4.1 Add `ohmystock.swarm.discover_available_tools()` returning `sorted(list(registry.list_registered()))` from `ohmystock.tools._registry`.
- [x] 4.2 Add `ohmystock.swarm.discover_available_skills()` walking `src/ohmystock/skills/**/*.yaml`, parsing the `name` frontmatter, returning sorted unique identifiers.
- [x] 4.3 Re-export both from `src/ohmystock/swarm/__init__.py`.
- [x] 4.4 Add tests `tests/test_swarm_discovery.py` with temporary skill directories + a stubbed registry.

## 5. Pure assembler

- [x] 5.1 In `src/ohmystock/swarm/_input_assembler.py`, implement `_normalize_trigger_at(iso: str) -> str` that strips colons and the `+08:00` offset, raising `AssemblerInputError` if no offset is present.
- [x] 5.2 Implement `_candidate_to_snapshot(candidate: Phase2BCandidate, current_price: float) -> CandidateSnapshot`: round subtotals to int, copy SEPA fields, raise `AssemblerInputError` on missing SEPA fields. (Note: `ema20_distance_pct`/`atr_14_pct` now passed explicitly by caller rather than scraped from evidence dict — cleaner contract.)
- [x] 5.3 Implement `_build_market_context(candidate, market, portfolio, journal_stats) -> MarketContext`: sort positions, compute `same_sector_count`, fill `recent_20_winrate` / `consecutive_loss` from `journal_stats`.
- [x] 5.4 Implement `assemble(...) -> EntryDecisionInput` orchestrating the helpers above, threshold-gating `final_score >= 65`, building `decision_id`, and returning the validated model.
- [x] 5.5 Snapshot test `tests/test_input_assembler_snapshot.py`: pin the JSON output for a fixed input fixture so unintended drift fails CI.
- [x] 5.6 Determinism test `tests/test_input_assembler_determinism.py`: call assemble twice with identical inputs (including `trigger_at`); assert `model_dump(mode="json", by_alias=True)` is byte-equal.
- [x] 5.7 No-I/O test `tests/test_input_assembler_no_io.py`: monkeypatch `socket.socket`, `httpx.Client`, `sqlite3.connect` to raise; call `assemble` with prebuilt snapshots; assert it still succeeds.

## 6. Public runner entry point

- [x] 6.1 In `src/ohmystock/swarm/runner.py`, define `build_entry_decision_input(candidate, market, portfolio, journal_stats, rules_digest, available_tools, available_skills, *, trigger_at) -> EntryDecisionInput` that delegates to `_input_assembler.assemble`.
- [x] 6.2 Re-export `build_entry_decision_input`, `EntryDecisionInput`, `AssemblerInputError`, `load_rules_digest`, `discover_available_tools`, `discover_available_skills` from `src/ohmystock/swarm/__init__.py`.
- [x] 6.3 Contract test `tests/test_swarm_runner_contract.py`: end-to-end with the fixture from §5.5; validate against `EntryDecisionInput`.

## 7. Phase 2B scoring consumption surface

- [x] 7.1 Implement `iter_qualified_candidates(asof_date, *, threshold=65.0)` in `src/ohmystock/scoring/_repository.py` that loads via swap-in candidate loader, filters `final_score >= threshold`, sorts by `(-final_score, symbol)`, yields `Phase2BCandidate`. Loader defaults to `NotImplementedError` until persistence wires up; CLI passes candidates via `candidates=` kwarg.
- [x] 7.2 SEPA fields (`stage`, `rs_percentile`, `trend_template_passed`, `vcp_quality`, `pivot_price`) added to `Phase2BCandidate` as Optional with same constraints as `swarm/models.py`. Defaults to `None` for backward compat — assembler enforces non-None at consumption time.
- [x] 7.3 `_engine._extract_sepa_fields` reads sub-scorer evidence and populates SEPA fields on the candidate. When a value can't be derived (deferred sub-scorers not shipped yet), the field stays `None` and the assembler raises `AssemblerInputError` at consumption — explicit per spec rather than silent skip.
- [x] 7.4 Tests `tests/test_iter_qualified_candidates.py`: ordering, threshold filter, empty-result case, SEPA-field presence.

## 8. CLI

- [x] 8.1 Add `oms assemble-entry-input` subcommand in `src/ohmystock/cli/_assemble.py`: arguments `<symbol>`, `--asof YYYY-MM-DD`, `--trigger-at ISO-8601`, `--out PATH`.
- [x] 8.2 Wire it into `src/ohmystock/cli/__init__.py` (typer subcommand, not argparse — repo convention).
- [x] 8.3 The command loads the candidate via `iter_qualified_candidates` (`_candidates_via_score_watchlist` helper), default-builds Live providers (raise NotImplementedError until tools wire up), calls `build_entry_decision_input`, emits JSON.
- [x] 8.4 Tests `tests/test_cli_assemble_entry_input.py`: success path (stdout + `--out`), score-below-threshold non-zero exit, missing symbol error.

## 9. Validation and docs sync

- [x] 9.1 Run `openspec validate phase-2b-swarm-input-assembler` — clean.
- [x] 9.2 Run the full test suite — 408 passed (71 new, no regressions).
- [x] 9.3 `docs/design-zh-TW.md` §4.7.0 signature is an underspecification (it lists 4 inputs; the real implementation needs explicit `candidate_name`/`candidate_sector`/`current_price`/`ema20_distance_pct`/`atr_14_pct`/`distance_from_52w_high_pct`/`distance_from_52w_low_pct` kwargs because `Phase2BCandidate` doesn't carry per-day price/ATR fields). Leaving the doc as the conceptual SSOT; the spec file under `openspec/specs/swarm-input-assembler/spec.md` (post-archive) carries the real contract. Document this gap when the cheatsheet evolves to add price/ATR fields to `Phase2BCandidate`.
- [x] 9.4 `openspec status --change phase-2b-swarm-input-assembler` — `isComplete: true` once tasks above are checked.
