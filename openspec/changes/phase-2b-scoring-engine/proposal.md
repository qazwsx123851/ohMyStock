## Why

Phase 2B is the keystone of the daily TW pipeline (`workflow-cheatsheet.md` §5). The `final_score ≥ 65` gate (§6.1, line 329) is what hands candidates to the LLM Decider. Before the rubric's individual sub-scorers can be wired, the **engine** that composes them needs to exist: the public `score_watchlist()` entrypoint, the `Phase2BCandidate` output schema, the sub-scorer registry, the Risk-Off ceiling logic, and deterministic sort + truncation. This change ships only that engine — small, focused, testable end-to-end against a single "always-zero" sub-scorer placeholder. Real sub-scorers follow in `phase-2b-shipped-subscorers` and the 16 deferred stubs follow in `phase-2b-deferred-cli`.

## What Changes

- New public function `score_watchlist(asof_date, candidates, *, risk_off_resolver=lambda: False, top_n=None, _conn=None, _today=None) -> dict` in `ohmystock.scoring` returning the standard envelope `{ok, elapsed_ms, data, error}`.
- New Pydantic models `Phase2BCandidate` and `SubScoreResult` in `ohmystock.scoring.models` — the inter-module contract that Phase 2A and the Swarm Input Assembler will depend on.
- New `ScoringContext` dataclass in `ohmystock.scoring.context` holding pre-loaded `bars`, `three_major`, `margin_short` per candidate.
- New sub-scorer registry in `ohmystock.scoring.registry`: `@register_subscorer(category, name, max_points)` decorator, `dispatch(name, ctx) -> SubScoreResult` that overwrites name/category/max from registry metadata and clamps `points` to `[0, max]`, `list_subscorers()` enumerator.
- One placeholder sub-scorer `_always_zero_placeholder` in category `technical` with `max_points=0`, registered via the registry. Sole purpose: keep the engine end-to-end testable until real sub-scorers ship. It returns `status="scored"`, `points=0`, `evidence={"placeholder": True}`. Removed (not edited) in `phase-2b-shipped-subscorers`.
- Engine logic: input validation (envelope `INVALID_INPUT`), context loading via existing `get_kline` / `get_three_major_investors` / `get_margin_short`, aggregation across registered sub-scorers, category sub-totals (capped at 40 / 25 / 25 / 10), `final_score` = sum of `scored` points capped at 100, Risk-Off ceiling at 50 when injected resolver returns `True`, light classification (≥65 / 50–64 / <50), sort by `final_score` desc then `symbol` asc, optional `top_n` truncation, determinism.

**Out of scope (follow-on changes):**
- Real sub-scorers backed by indicators / chip / market-data — `phase-2b-shipped-subscorers`.
- 16 deferred-stub sub-scorers — `phase-2b-deferred-cli`.
- `ohmystock score watchlist` CLI subcommand — `phase-2b-deferred-cli`.
- `strategies/risk_gate.py` evaluator — caller still passes a `risk_off_resolver` callable.

## Capabilities

### New Capabilities
- `phase-2b-scoring-engine`: pure scoring engine — `score_watchlist()` envelope, `Phase2BCandidate` + `SubScoreResult` models, sub-scorer registry contract, Risk-Off ceiling, light classification, deterministic sort + truncation. Self-contained and end-to-end testable via a single placeholder sub-scorer; real sub-scorers register via the same decorator in follow-on changes without touching engine code.

### Modified Capabilities
_(None — new capability, no requirements changed in existing specs.)_

## Impact

- **New code**:
  - `src/ohmystock/scoring/__init__.py` — re-exports `score_watchlist`, `Phase2BCandidate`, `SubScoreResult`, and triggers placeholder sub-scorer registration.
  - `src/ohmystock/scoring/models.py` — Pydantic `SubScoreResult`, `Phase2BCandidate`.
  - `src/ohmystock/scoring/context.py` — `ScoringContext` dataclass.
  - `src/ohmystock/scoring/registry.py` — registry + dispatch + `list_subscorers`.
  - `src/ohmystock/scoring/_engine.py` — `score_watchlist` implementation.
  - `src/ohmystock/scoring/_placeholder.py` — `_always_zero_placeholder` sub-scorer (deleted in `phase-2b-shipped-subscorers`).
  - `tests/test_scoring_models.py`, `tests/test_scoring_registry.py`, `tests/test_scoring_engine.py`, `tests/test_scoring_reverse_import.py`.
- **Code consumed (no edits)**: `ohmystock.data.market_data.get_kline`, `ohmystock.chip.three_major.get_three_major_investors`, `ohmystock.chip.margin_short.get_margin_short`.
- **DB / migrations**: none — engine is stateless; reads existing caches via the existing data APIs.
- **Tools / contracts**: future `phase_2b_tool` registration deferred to the LLM Decider change.
- **Docs**: `workflow-cheatsheet.md` §5 remains the rubric SSOT. No doc edits required.
