## Context

Phase 2B scoring already ships 6 real sub-scorers + 16 deferred stubs. The deferred package was a placeholder strategy: stubs register with `status="skipped"` so the engine and the registry layout tests stay green even before the real sub-scorers exist. With the swarm input assembler now in place, two of those stubs are blocking end-to-end usage: the assembler refuses any candidate without `rs_percentile`, `vcp_quality`, or `pivot_price`. Both fields are computed by sub-scorers, so the simplest unblock is to promote the relevant stubs to real implementations.

The cheatsheet (`docs/workflow-cheatsheet.md`) is the SSOT for sub-scorer behaviour:
- §1 第二層 / §2 (8) — RS Percentile threshold 65 (vs US 70), 252-day weighted, TWSE+OTC liquidity-filtered universe.
- §6.5 / §6 K 線品質 — VCP > cup-handle > platform > classic, 8 pts max, with pivot breakout volume ≥ 1.4× 20DMA in `[pivot, pivot×1.05]`.
- `_extract_sepa_fields` in `_engine.py` already reads `rs_percentile.evidence["rs_percentile"]` and `vcp_pivot.evidence["vcp_quality"]` / `["pivot_price"]` — the wiring is in place; only the sub-scorer bodies are missing.

Stakeholder: solo developer using the assembler offline. The bar is "this passes its own contract tests and lets the assembler return a valid `EntryDecisionInput`" — not "production-grade IBD-grade RS computation". Universe seeding is intentionally minimal so we don't drag in TWSE-wide universe building (separate change).

## Goals / Non-Goals

**Goals:**
- A real `rs_percentile` sub-scorer that returns `status="scored"` with a populated `evidence["rs_percentile"]` integer in `[0, 99]`.
- A real `vcp_pivot` sub-scorer that returns `status="scored"` with `evidence["vcp_quality"]` and conditionally `evidence["pivot_price"]` (positive float when quality ∈ {textbook, breakout}, else `None`).
- `Phase2BCandidate` from `score_watchlist` carries non-None SEPA fields whenever the input bars suffice — making `oms assemble-entry-input` work end-to-end.
- Same input layout as existing real sub-scorers (one file per scorer in `subscorers/`, frozen `_NEED_BARS` and `_MAX_POINTS` constants, `register_subscorer` decorator).

**Non-Goals:**
- Production-grade TWSE+OTC universe construction (≥1000 symbols). The seed list is good enough; the escape hatch documents how to upgrade.
- Daily universe refresh / persistence — the universe is a process-local in-memory list.
- Industry RS percentile (a separate cheatsheet line item, lives in a future sub-scorer).
- Refactoring the deferred-stub registration pattern.
- Touching the assembler — its contract is already correct.

## Decisions

### D1. Promotion strategy: move-and-rewrite, don't keep deferred shadow
We physically move `deferred/rs_percentile.py` → `rs_percentile.py` (and `deferred/kline_patterns.py` → `vcp_pivot.py`). The deferred entry is removed. This keeps "real vs deferred" honest: a sub-scorer is in `deferred/` iff it returns `status="skipped"`. Counts in `test_subscorers_layout.py` shift from 16 → 14.

Alternative considered: leave the deferred stubs in place and add real sub-scorers under different names. Rejected — the registry doesn't allow duplicate names, and parallel real/stub modules invite drift.

### D2. RS Percentile algorithm — IBD-style weighted, 252 day, percentile-rank against universe
For each symbol `s` in `universe ∪ {candidate}`:

```
ret(s) = 0.4 × pct_change(closes_s, 63d)    # last quarter, weighted heaviest
       + 0.2 × pct_change(closes_s, 126d)   # last half-year
       + 0.2 × pct_change(closes_s, 189d)   # 3 quarters
       + 0.2 × pct_change(closes_s, 252d)   # last year
```

Then `rs_percentile(candidate) = round(percentile_rank(ret(candidate), [ret(s) for s in universe]) * 99)` — clamped to `[0, 99]`. This matches the Marketsmith / IBD weighting and produces an integer compatible with the schema's `Field(ge=0, le=99)`.

Scoring: `≥65 → 3 / ≥80 → 5 / ≥90 → 7` (cheatsheet §6.5 line 277).

Universe loader returns a list of `(symbol, closes)` tuples. Default seed = 5 TWSE large-caps. Tests inject fakes via `set_rs_universe(...)` to avoid pulling real klines.

Why a callable hook instead of importing `data.market_data.get_kline` directly: the sub-scorer must remain side-effect-light (uses the existing `ScoringContext.bars` for the candidate; only universe symbols need extra fetches). Wrapping the fetch behind `set_rs_universe_loader(loader_fn)` lets tests stub without monkeypatching `get_kline`.

### D3. VCP / Pivot algorithm — pragmatic, not textbook
Mark Minervini's textbook VCP detection requires multi-month pattern recognition. We don't need that to populate the schema field — we need *something* that emits a valid `vcp_quality` ∈ `{none, forming, textbook, breakout}` and a `pivot_price` when applicable. Heuristics:

- Compute a **base** = the 20-bar window ending today.
- `range_pct` = `(max(highs) - min(lows)) / min(lows)`.
- **breakout**: today's close > prior-19-bar high AND today's volume ≥ 1.4× 20-DMA volume → `vcp_quality="breakout"`, `pivot_price = max(prior 19 highs)`.
- **textbook**: base `range_pct` < 0.10 AND at least 2 lower-high contractions visible in the last 60 bars → `vcp_quality="textbook"`, `pivot_price = max(highs[-20:])`.
- **forming**: base `range_pct` < 0.15 AND no breakout → `vcp_quality="forming"`, `pivot_price = None`.
- **none**: anything else → `vcp_quality="none"`, `pivot_price = None`.

Scoring (8 pts max):
- `breakout` → 8
- `textbook` → 6
- `forming` → 3
- `none` → 0

This is intentionally simple — the cheatsheet's stricter VCP criteria can layer on later. The contract for downstream (assembler / Phase 3 LLM) only requires the enum + pivot_price invariant, which this satisfies.

### D4. NEED_BARS conservative: 252 for RS, 60 for VCP
RS Percentile uses up to 252 closes. VCP only needs ~60 (20 for the base + 40 for contraction history). Both sub-scorers return `status="skipped"` with `evidence={"reason": "insufficient_bars", ...}` when ctx.bars is too short — same pattern as `trend_template_8` and `stage_2_confirmed`.

### D5. Universe loader is a module-level callable, not a global list
```python
_universe_loader: Callable[[], list[tuple[str, list[float]]]] = _default_seed_loader
```

Tests use `set_rs_universe_loader(lambda: [...])` to inject. Production code (when it lands) replaces it with a real loader that pulls klines for ~1000 TWSE+OTC symbols. The seed loader returns 5 large-cap symbols with synthetic constant-return series — usable in unit tests without network.

### D6. Sub-scorer max_points stays consistent with existing aggregator
- `rs_percentile`: max_points=7 (matches existing deferred stub registration; cheatsheet §6.5 line 277).
- `vcp_pivot`: max_points=8 (matches `K 線品質` line in cheatsheet §6.5; existing deferred stub `kline_patterns` registers with max_points=8).

`_engine._aggregate` clamps technical category at 40 — so even if all technical sub-scorers max out (5+5+5+8+5+10+7 = 45), the cap kicks in at 40. No change needed there.

## Risks / Trade-offs

- **[5-symbol seed universe is statistically meaningless]** → Mitigation: documented escape hatch `set_rs_universe_loader` lets the user inject a real universe at any time; assembler doesn't care about percentile accuracy, only its presence and range. Tests assert the algorithm shape, not numeric realism.
- **[VCP heuristics are crude]** → Mitigation: the contract is the schema invariant (`vcp_quality` enum + `pivot_price` correlation). Production-grade VCP is a separate cheatsheet refinement, not a blocker for the assembler.
- **[Moving files breaks imports]** → Mitigation: only `subscorers/__init__.py` and `subscorers/deferred/__init__.py` import these modules. The `_engine.py` SEPA-extraction code already looks up by registered *name*, not module path.
- **[Layout test counts drift]** → Mitigation: spec delta updates the count from 16 → 14 explicitly; layout test reads the count from the deferred package directory.
- **[Universe fetches add latency]** → Mitigation: default seed loader runs fully in-memory. Real production universes can layer in caching at the loader level.
- **[Dual `kline_patterns` / `vcp_pivot` confusion]** → Mitigation: the deferred file is renamed and moved in one operation; `subscorers/deferred/__init__.py` no longer imports `kline_patterns`. The cheatsheet vocabulary settles on "VCP/pivot" (§6.5), so `vcp_pivot.py` is canonical.

## Migration Plan

Greenfield from the engine's perspective — no production state migration. Steps:

1. Move `deferred/rs_percentile.py` → `rs_percentile.py`; rewrite body. Land + tests pass.
2. Move + rename `deferred/kline_patterns.py` → `vcp_pivot.py`; rewrite body. Land + tests pass.
3. Update `subscorers/__init__.py` to register the two new modules.
4. Update `subscorers/deferred/__init__.py` to drop the two old entries.
5. Update `tests/test_subscorers_layout.py` count assertion (16 → 14).
6. Run full pytest. The assembler should now succeed end-to-end on real Phase 2B output (provided live providers are mocked).

Rollback: revert. No persistent state to undo.

## Open Questions

- **Q1**: Should the seed universe include `0050` (Yuanta TW50 ETF) so the RS computation has at least one ETF data point? Decision pending: probably not — RS is for individual stocks, not ETFs. Will revisit if test assertions need it.
- **Q2**: Does the cheatsheet's "≥1.4× 20DMA" volume rule apply to the bar-of-breakout, or to the 5-day average around it? Reading §6.5 line 593 ("量價結構（OBV + 突破量 ≥ 1.4×）") suggests the bar itself. Implement bar-level; revisit if production trades show false positives.
- **Q3**: For `vcp_pivot.evidence["pivot_price"]`, do we need a separate `pivot_low` field (for stop-loss reference)? The schema only requires `pivot_price`, so no — but adding `pivot_low` to evidence is cheap if the LLM Decider needs it later. Decision: leave out of evidence for now; can add without schema change.
