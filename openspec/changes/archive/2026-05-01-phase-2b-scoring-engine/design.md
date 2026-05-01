## Context

`workflow-cheatsheet.md` §5 / §6.1 / §10 is the SSOT for the Phase 2B rubric (40 + 25 + 25 + 10 = 100, `final_score ≥ 65` triggers the LLM Decider, Risk-Off lowers the green-light ceiling to 50). The rubric is itself made of ~24 sub-scorers across four categories. Shipping all of them in one change is too large to review and would entangle the engine contract with sub-scorer internals; the next change (`phase-2b-shipped-subscorers`) ships real sub-scorers, and the one after (`phase-2b-deferred-cli`) ships the 16 deferred-stub sub-scorers + the `ohmystock score watchlist` CLI.

This change ships the **engine only** — the public function, the Pydantic contracts, the sub-scorer registry, the Risk-Off ceiling, deterministic sort + truncation — kept end-to-end testable via a single `_always_zero_placeholder` sub-scorer that the next change deletes.

Phase 1 / Phase 2A / Swarm Input Assembler all consume the same `Phase2BCandidate` schema, so the contract introduced here is a load-bearing inter-module seam.

## Goals / Non-Goals

**Goals:**
- One public function `score_watchlist(...)` returning the standard envelope `{ok, elapsed_ms, data, error}` (same convention as `get_kline`, `get_three_major_investors`, `screen_universe`). No exception escapes the boundary.
- One sub-scorer registry contract — adding a real sub-scorer in the next change is a `@register_subscorer(...)` decorator on a pure function plus an import in `scoring/__init__.py`. Engine code does not change.
- Clamp invariant: `0 ≤ points ≤ max_points`; category sub-total ≤ category cap; `final_score ≤ 100`.
- Risk-Off ceiling: when the injected `risk_off_resolver()` returns `True`, every candidate's `final_score` is min'd with 50 **before** classification.
- Deterministic ordering: `final_score` desc, then `symbol` asc; `top_n` truncates after sort.
- Reverse-import guard: `ohmystock.scoring` does not pull `fastapi` / `uvicorn` / `starlette` into `sys.modules`.

**Non-Goals:**
- Real sub-scorers (Trend Template, RS Percentile, EPS YoY, etc.) — `phase-2b-shipped-subscorers`.
- 16 deferred-stub sub-scorers and the CLI subcommand — `phase-2b-deferred-cli`.
- `strategies/risk_gate.py` evaluator — caller injects a `risk_off_resolver: Callable[[], bool]`.
- `phase_2b_tool` registration in `tools-contracts.md` — owned by the LLM Decider change.
- Catalyst correction (+5 / -10) and monthly-revenue bonus (+5) — those land with the corresponding sub-scorers in the follow-on changes; the engine sums what's registered.
- Caching of scoring output. Engine is stateless; callers that want persistence wrap the result.

## Decisions

### D1. Public entrypoint shape: envelope, not exceptions

```python
def score_watchlist(
    asof_date: str,
    candidates: list[str],
    *,
    risk_off_resolver: Callable[[], bool] = lambda: False,
    top_n: int | None = None,
    _conn: sqlite3.Connection | None = None,
    _today: str | None = None,
) -> dict:
```

Returns `{"ok": bool, "elapsed_ms": int, "data": <payload>|None, "error": {"code", "message", "retriable"}|None}`. `data.candidates` is a list of `Phase2BCandidate`-shaped dicts (after `model_dump()`). Error codes: `INVALID_INPUT`, `DATA_UNAVAILABLE`, `INTERNAL_ERROR`.

**Why:** identical to every other public data/strategy function in the repo today (`get_kline`, `screen_universe`, `run_backtest`). The future `phase_2b_tool` wraps this 1:1 with no extra translation.
**Alternative rejected:** raising domain exceptions — diverges from the pattern and forces UI/CLI to re-translate at every layer.

### D2. Sub-scorer registry: decorator + module-level dict, no class hierarchy

```python
@register_subscorer(category="technical", name="trend_template", max_points=5)
def trend_template(ctx: ScoringContext) -> SubScoreResult:
    ...
```

`register_subscorer` is module-state: a dict keyed by `name` whose value is `(fn, category, max_points)`. `dispatch(name, ctx) -> SubScoreResult` calls the function, then **overwrites** `result.name` / `result.category` / `result.max_points` from the registry metadata (so a sub-scorer cannot lie about its own contract) and clamps `points` to `[0, max_points]`. `list_subscorers()` returns a stable, alphabetically sorted list of metadata.

**Why:** the engine never imports any sub-scorer directly — it iterates `list_subscorers()`. This is what lets the follow-on changes add 24 sub-scorers without engine edits. Module-state is acceptable here because sub-scorer registration happens at import time and the registry is read-only afterward.
**Alternative rejected:** Strategy/Subclass hierarchy — too much ceremony for pure scoring functions; matches none of the existing module styles (data, indicators, chip, screener are all pure functions).
**Alternative rejected:** entry-points / setuptools plugins — over-engineered for a single-package solo repo.

**Duplicate-registration policy:** `register_subscorer` raises `ValueError` if a `name` is already registered. Re-registration in tests goes through a `_reset_registry()` helper exposed in `scoring.registry` for test use only.

### D3. ScoringContext is loaded once per candidate, not per sub-scorer

```python
@dataclass(frozen=True)
class ScoringContext:
    asof_date: str
    symbol: str
    bars: list[dict]            # 250-bar slice from get_kline
    three_major: list[dict]     # 30-day slice from get_three_major_investors
    margin_short: list[dict]    # 30-day slice from get_margin_short
```

The engine fetches all three for each candidate **before** dispatching sub-scorers, so any sub-scorer can read any window. If a fetch returns `ok=False`, the candidate is recorded with `status="error"` per sub-scorer (see D4) and excluded from the green/yellow gates but still appears in `data.candidates` so callers can debug coverage.

**Why:** Phase 2B runs once per day on ≤ 100 candidates — three SQLite reads per candidate is cheap, and pre-loading lets sub-scorers stay pure (they receive a context, never an I/O handle). Tests can construct a `ScoringContext` literal without the data layer.
**Alternative rejected:** lazy-load from inside each sub-scorer — couples sub-scorers to the data layer and makes them harder to unit-test.

**Window sizes:** `bars` defaults to 250 (≈ 1 trading year, enough for SMA200 / RS Percentile lookback in the next change). `three_major` and `margin_short` default to 30 (covers "5-day net buy" + "consecutive-3-day" requirements with margin). Sub-scorers in the next change that need more (e.g., 252-day RS) will widen these constants in a single place.

### D4. SubScoreResult statuses: `scored` / `skipped` / `error`

```python
class SubScoreResult(BaseModel):
    name: str
    category: Literal["technical", "chip", "fundamental", "sentiment"]
    points: float                # NOT summed when status != "scored"
    max_points: float
    status: Literal["scored", "skipped", "error"]
    evidence: dict[str, Any] = {}
    error_message: str | None = None
```

- `scored`: counted toward `final_score`.
- `skipped`: data sufficient, sub-scorer chose not to score (e.g., catalyst sub-scorer with no news in window). `points` MUST be `0`. Not counted.
- `error`: data unavailable / sub-scorer raised. `points` MUST be `0`. Not counted; surfaced via `evidence` and `error_message` for debugging.

**Why:** `final_score` is the sum of `scored` points only. This avoids the "missing chip data silently lowers the score" pitfall and keeps the rubric ceiling honest — a candidate with chip-data outage scores e.g. `tech_subtotal + 0` not `tech_subtotal × incorrect_ratio`. Phase 2B downstream consumers (LLM Decider input assembler) read `status` to know whether a category was actually evaluated.

### D5. Category sub-totals capped, then summed; final cap at 100

```
tech_subtotal     = min(40, sum(scored points where category == "technical"))
chip_subtotal     = min(25, sum(scored points where category == "chip"))
fund_subtotal     = min(25, sum(scored points where category == "fundamental"))
sent_subtotal     = min(10, sum(scored points where category == "sentiment"))
final_score_raw   = tech_subtotal + chip_subtotal + fund_subtotal + sent_subtotal
final_score       = min(100, final_score_raw)
```

**Why:** `workflow-cheatsheet.md` §5 declares per-category caps (40/25/25/10) explicitly. Capping at the category boundary first means a single high-scoring sub-scorer can't blow past its category, and the negative borrow-rate band (-3 ~ +2) inside `chip` can't pull the chip subtotal below `0` (we floor at `0` per category as well — see D6).

### D6. Negative-points floor at the category level

`workflow-cheatsheet.md` §5 has bands like 借券餘額變化 `-3 ~ +2` and 搜尋熱度 `-2 ~ +2`. Per category, `subtotal = max(0, min(cap, sum(scored points)))`. A category cannot contribute negative points to the final.

**Why:** the SSOT lists the rubric out of 100 (positive); negative bands are within-category friction, not score deductions that the green-light gate at 65 should perceive as "this candidate is 95 on technicals so even after -8 elsewhere it's fine." Keeping per-category subtotals non-negative protects the gate's semantics.

### D7. Risk-Off ceiling is applied AFTER summing, BEFORE classification

```
if risk_off_resolver():
    final_score = min(final_score, 50)
classification = "green" if final_score >= 65 else "yellow" if final_score >= 50 else "red"
```

**Why:** §5 says "Risk-Off 期間：所有訊號天花板自動降為 50（即綠燈一律降黃）". Capping at 50 before classification makes that exact rule enforceable in one line. Note that the resolver is **injected as a callable** (not a flag) so a stale resolver state at engine entry doesn't get cached for the whole batch — the engine calls it once per `score_watchlist` invocation (not per candidate; the flag is global, not per-symbol).

### D8. Sort / truncate determinism

Two-key sort: `final_score` desc, then `symbol` asc (lexicographic). `top_n` (when not `None`) truncates after sort. Same inputs ⇒ same output, byte-for-byte.

**Why:** `screen_universe` already sorts by `symbol`; a stable secondary key on Phase 2B output keeps two consecutive runs idempotent and lets cached pipelines diff cleanly.

### D9. Placeholder sub-scorer + module loading

`scoring/_placeholder.py` defines `_always_zero_placeholder(ctx) -> SubScoreResult` registered with `category="technical"`, `max_points=0`. `scoring/__init__.py` imports `_placeholder` after `registry` so the registration runs at package import. The next change (`phase-2b-shipped-subscorers`) deletes `_placeholder.py` and removes the import — engine and registry stay untouched.

**Why:** without **at least one** registered sub-scorer the engine has nothing to dispatch and tests devolve into mocking the registry. A `max_points=0` placeholder lets the engine end-to-end test the full path without affecting `final_score`.

### D10. Validation matches the rest of the repo

- `asof_date` regex `^\d{4}-\d{2}-\d{2}$` and parseable.
- `candidates` non-empty list of `^\d{4,6}(KY)?$` strings (matches `screen_universe`).
- `top_n` either `None` or `int >= 1` (no `bool` aliasing — guard with `isinstance(top_n, bool)`).
- `risk_off_resolver` callable; if not callable, `INVALID_INPUT`.

Errors → `INVALID_INPUT` envelope. Data-layer errors propagate as a per-sub-scorer `status="error"`, **not** an envelope-level error — a partial Phase 2B result is more useful than a totally-failed one.

**Envelope-level `DATA_UNAVAILABLE`:** only when `get_kline` for a candidate returns `ok=False` AND there are zero registered sub-scorers that can run without bars. Today (with the placeholder) we never hit this; documented for completeness so the next change knows the rule.

**Envelope-level `INTERNAL_ERROR`:** unexpected exception inside the engine itself (not a sub-scorer; sub-scorer exceptions are caught and translated to `status="error"`).

## Risks / Trade-offs

- **[Registry global state]** → Tests that re-import sub-scorers in the same process can hit `ValueError: already registered`. Mitigation: `_reset_registry()` test helper; `conftest.py` calls it in a fixture for the scoring tests only. Keep the helper underscore-prefixed and excluded from `__init__.py` exports.
- **[Pre-loading bars/chip for every candidate when sub-scorers may not all need them]** → Wasted I/O. Mitigation: tolerable at Phase 2B's batch size (≤ 100 symbols × 3 SQLite SELECTs per day); revisit only if profiling shows it dominates. Document the assumption so the next change knows to extend windows in `ScoringContext`, not introduce lazy I/O.
- **[Negative-band sub-scorers can be silently wasted by the per-category 0 floor]** → A sub-scorer in the chip category whose contribution is `-3` (extreme borrow surge) is invisible if other chip sub-scorers already total to `0`. Mitigation: this is intentional per D6 (the rubric is positive-out-of-100); evidence-level reporting in `SubScoreResult.evidence` still surfaces the signal to the LLM Decider downstream.
- **[Risk-Off resolver injected per call, not read from a global flag]** → Inconsistent with `safety-and-simulation.md` §2.1 which envisions a global Risk Gate. Mitigation: deliberate — the engine should be testable without the safety subsystem. The future `strategies/risk_gate.py` evaluator becomes the default resolver passed by upstream callers (Phase 2B scheduler / CLI / tool).
- **[Placeholder leaves a `max_points=0` row in every result]** → Each candidate's sub-scorer list contains a noise entry until `phase-2b-shipped-subscorers` deletes it. Mitigation: short-lived (next change), and `evidence={"placeholder": True}` makes it self-documenting.

## Migration Plan

- No DB schema changes, no spec deletions, no public-API breakage.
- Adding the package: `src/ohmystock/scoring/` is new; no rename or move.
- Tests run in isolation via `pytest tests/test_scoring_*.py`.
- Rollback: delete `src/ohmystock/scoring/`, delete `tests/test_scoring_*.py`. Nothing else depends on the new symbols yet.

## Open Questions

- **Q1.** Should `data.candidates[*].subscores` include sub-scorers with `status="skipped"` to keep the per-symbol shape uniform? **Tentative:** yes, include all registered sub-scorers in every candidate's `subscores` list; downstream consumers (LLM Decider input assembler) prefer fixed-shape rows. Resolved in `specs/phase-2b-scoring-engine/spec.md` Requirement 4.
- **Q2.** Should `score_watchlist` cap `len(candidates)` (e.g., 200) at the input-validation layer? **Tentative:** no for now — the engine is stateless and the screener already produces ≤ 50 candidates at this step in the pipeline. Add a cap only if a misuse case appears.
