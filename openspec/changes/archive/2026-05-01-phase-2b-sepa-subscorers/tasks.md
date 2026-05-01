## 1. RS Percentile sub-scorer

- [x] 1.1 Create `src/ohmystock/scoring/_rs_universe.py` with module-level `_universe_loader` callable, default seed (5 TWSE large-caps: 2330, 2317, 2454, 3008, 2412) returning `[(symbol, list[float])]`, and public `set_rs_universe_loader(loader)` / `reset_rs_universe_loader()` helpers.
- [x] 1.2 Create `src/ohmystock/scoring/subscorers/rs_percentile.py` with `@register_subscorer(category="technical", name="rs_percentile", max_points=7)`. Implement `_NEED_BARS = 252`, IBD-weighted return formula (0.4×63d + 0.2×126d + 0.2×189d + 0.2×252d), percentile_rank vs universe loader output, scoring tiers (≥65→3, ≥80→5, ≥90→7), evidence keys (`rs_percentile`, `weighted_return`, `universe_size`).
- [x] 1.3 Delete `src/ohmystock/scoring/subscorers/deferred/rs_percentile.py` (the deferred stub) and remove its import from `subscorers/deferred/__init__.py`.
- [x] 1.4 Add `from ohmystock.scoring.subscorers import rs_percentile` to `src/ohmystock/scoring/subscorers/__init__.py`.
- [x] 1.5 Add tests `tests/test_subscorer_rs_percentile.py`: insufficient_bars skipped, top-decile scores 7, threshold tier mapping (3/5/7), valid range [0,99], custom universe loader honoured.

## 2. VCP Pivot sub-scorer

- [x] 2.1 Create `src/ohmystock/scoring/subscorers/vcp_pivot.py` with `@register_subscorer(category="technical", name="vcp_pivot", max_points=8)`. Implement `_NEED_BARS = 60`, classification rules (breakout / textbook / forming / none) per `design.md` §D3, evidence keys (`vcp_quality`, `pivot_price`, `range_pct`, `volume_ratio`, `contractions`).
- [x] 2.2 Delete `src/ohmystock/scoring/subscorers/deferred/kline_patterns.py` (the deferred stub) and remove its import from `subscorers/deferred/__init__.py`.
- [x] 2.3 Add `from ohmystock.scoring.subscorers import vcp_pivot` to `src/ohmystock/scoring/subscorers/__init__.py`.
- [x] 2.4 Add tests `tests/test_subscorer_vcp_pivot.py`: insufficient_bars skipped, breakout=8, textbook=6, forming=3, none=0, pivot_price invariant per quality.

## 3. Layout / engine wiring

- [x] 3.1 Update `tests/test_subscorers_layout.py` deferred-count assertion from `16` to `14`.
- [x] 3.2 Verify `_engine._extract_sepa_fields` already reads `rs_percentile.evidence["rs_percentile"]` and `vcp_pivot.evidence["vcp_quality"]` / `["pivot_price"]` (already prepared in the previous change — no change expected; add a regression test if missing).
- [x] 3.3 Add an end-to-end test `tests/test_scoring_engine_sepa_fields.py` that calls `score_watchlist("2026-04-30", ["2330"])` against synthesized 252-bar uptrend kline data and asserts the resulting candidate has all 5 SEPA fields populated.

## 4. Validation

- [x] 4.1 Run `openspec validate phase-2b-sepa-subscorers` and resolve any errors.
- [x] 4.2 Run the full test suite — confirm 0 regressions, ~25 new tests passing.
- [x] 4.3 Smoke-test the assembler: build a `score_watchlist` candidate that satisfies all SEPA fields, then call `build_entry_decision_input` with fakes; assert no `AssemblerInputError`.
- [x] 4.4 Run `openspec status --change phase-2b-sepa-subscorers` and confirm `isComplete: true`.
