## 1. Scaffold subscorers package

- [x] 1.1 Create directory `src/ohmystock/scoring/subscorers/` with empty `__init__.py`
- [x] 1.2 Add `tests/test_subscorers_layout.py` asserting `import ohmystock.scoring.subscorers` succeeds and that the package is a directory (not a single file)
- [x] 1.3 Run `pytest tests/test_subscorers_layout.py -q` and confirm it passes

## 2. Ship `trend_structure_ma` (technical, 10 pts)

- [x] 2.1 Write `tests/test_subscorer_trend_structure_ma.py` with: (a) full uptrend (120 monotonic closes) → `points=10, status=scored, conditions_passed=3`; (b) one-condition-fails case (close drops below ma5 on last bar) → `points=0`; (c) `len(bars) < 60` → `points=0, status=skipped, evidence={reason:"insufficient_bars", have, need:60}`; (d) flat closes → `points=0` (ma5 == ma20 fails strict inequality)
- [x] 2.2 Implement `src/ohmystock/scoring/subscorers/trend_structure_ma.py`: pure function decorated with `@register_subscorer(category="technical", name="trend_structure_ma", max_points=10)`, using `ohmystock.indicators.core.sma`; evidence keys `close, ma5, ma20, ma60, conditions_passed`
- [x] 2.3 Add `from ohmystock.scoring.subscorers import trend_structure_ma  # noqa: F401` to `subscorers/__init__.py`
- [x] 2.4 Run `pytest tests/test_subscorer_trend_structure_ma.py -q`; all cases pass

## 3. Ship `trend_template_8` (technical, 5 pts)

- [x] 3.1 Write `tests/test_subscorer_trend_template_8.py` with: (a) all 7 conditions pass on synthetic 252-bar SEPA-uptrend → `points=5, conditions_passed=7, of=7`; (b) condition 7 fails (close 30% below 52w high) → `points=0, conditions_passed=6`; (c) condition 3 fails (200-MA flat over 22 days) → `points=0`; (d) `len(bars) < 252` → `points=0, status=skipped, evidence.need=252`
- [x] 3.2 Implement `src/ohmystock/scoring/subscorers/trend_template_8.py`: compute `ma50`, `ma150`, `ma200`, `ma200_22ago`, `high_52w`, `low_52w`; evaluate the 7 conditions per spec; `points=5` only when all hold; evidence keys `cond1..cond7, conditions_passed, of`
- [x] 3.3 Add the import line to `subscorers/__init__.py`
- [x] 3.4 Run `pytest tests/test_subscorer_trend_template_8.py -q`

## 4. Ship `stage_2_confirmed` (technical, 5 pts)

- [x] 4.1 Write `tests/test_subscorer_stage_2_confirmed.py` with: (a) all 4 conditions pass → `points=5`; (b) `ma150 == ma150_5ago` (flat MA) → `points=0`; (c) close 31% below 52w high (within 25% rule fails) → `points=0`; (d) `len(bars) < 252` → `points=0, status=skipped, need=252`
- [x] 4.2 Implement `src/ohmystock/scoring/subscorers/stage_2_confirmed.py`: compute `ma150`, `ma150_5ago`, `high_52w`, `low_52w`; evaluate the 4 conditions; evidence keys `cond1..cond4, conditions_passed`
- [x] 4.3 Add import line to `subscorers/__init__.py`
- [x] 4.4 Run `pytest tests/test_subscorer_stage_2_confirmed.py -q`

## 5. Ship `volume_breakout_obv` (technical, 5 pts)

- [x] 5.1 Write `tests/test_subscorer_volume_breakout_obv.py` with: (a) breakout + 1.5× volume + rising OBV → `points=5`; (b) breakout but volume==1.0× avg → `points=0`; (c) volume 1.5× but no breakout (close < 20-day high) → `points=0`; (d) breakout + volume but OBV slope ≤ 0 → `points=0`; (e) `len(bars) < 21` → `status=skipped`
- [x] 5.2 Implement `src/ohmystock/scoring/subscorers/volume_breakout_obv.py`: compute `high_20d_prior` from `bars[-21:-1]`, `vol_today` from `bars[-1].v`, `avg_vol_20d` from `bars[-21:-1]`, OBV cumulative sum over last 6 bars (sign of close-diff times volume), `obv_slope_5d = obv[-1] - obv[-6]`; evidence keys `breakout, volume_ratio, obv_slope_5d, conditions_passed`
- [x] 5.3 Add import line to `subscorers/__init__.py`
- [x] 5.4 Run `pytest tests/test_subscorer_volume_breakout_obv.py -q`

## 6. Ship `foreign_5d_net_buy` (chip, 5 pts)

- [x] 6.1 Write `tests/test_subscorer_foreign_5d_net_buy.py` with bands: (a) sum=1500 → `points=5`; (b) sum=1000 → `points=3` (boundary); (c) sum=1001 → `points=5`; (d) sum=350 → `points=2`; (e) sum=200 → `points=1` (boundary); (f) sum=0 → `points=0`; (g) sum=-300 → `points=0`; (h) `len(three_major) < 5` → `status=skipped, need=5`
- [x] 6.2 Implement `src/ohmystock/scoring/subscorers/foreign_5d_net_buy.py`: sum `foreign_net` over last 5 rows; band logic per spec; evidence keys `net_5d_lots, rows_used`
- [x] 6.3 Add import line to `subscorers/__init__.py`
- [x] 6.4 Run `pytest tests/test_subscorer_foreign_5d_net_buy.py -q`

## 7. Ship `trust_5d_net_buy` (chip, 4 pts)

- [x] 7.1 Write `tests/test_subscorer_trust_5d_net_buy.py` with bands: (a) sum=600 → `points=4`; (b) sum=301 → `points=4`; (c) sum=300 → `points=2` (boundary); (d) sum=250 → `points=2`; (e) sum=100 → `points=1` (boundary); (f) sum=0 → `points=0`; (g) sum=-50 → `points=0`; (h) `len(three_major) < 5` → `status=skipped`
- [x] 7.2 Implement `src/ohmystock/scoring/subscorers/trust_5d_net_buy.py`: sum `invest_trust_net` over last 5 rows; band logic per spec; evidence keys `net_5d_lots`
- [x] 7.3 Add import line to `subscorers/__init__.py`
- [x] 7.4 Run `pytest tests/test_subscorer_trust_5d_net_buy.py -q`

## 8. Wire subscorers package into top-level scoring

- [x] 8.1 Add `from ohmystock.scoring import subscorers  # noqa: F401` to `src/ohmystock/scoring/__init__.py` (immediately after the `registry` import; do **not** remove the placeholder import yet — that happens in section 10)
- [x] 8.2 Run `pytest tests/test_scoring_*.py -q` and confirm all existing tests still pass (placeholder + 6 new sub-scorers coexist)
- [x] 8.3 Verify `list_subscorers()` now returns 7 entries (placeholder + 6 real), alphabetically sorted

## 9. Add end-to-end engine test with real sub-scorers

- [x] 9.1 Write `tests/test_scoring_engine_real_subscorers.py` with helper `_make_max_score_ctx()` returning `(bars_252, three_major_5_rows, margin_short_5_rows)` constructed so all 6 sub-scorers hit their full-points conditions
- [x] 9.2 Add test: `score_watchlist("2026-04-30", ["2330"])` with all data sources mocked to return the helper output → `data.candidates[0].subscores` has length 7 (placeholder + 6) initially; after section 10 it becomes 6, `final_score == 34`, classification `"red"`
- [x] 9.3 Add test: mocked `get_kline` returns 30 bars while `get_three_major_investors` returns 5 strong rows → `trend_structure_ma`, `trend_template_8`, `stage_2_confirmed`, `volume_breakout_obv` all `status="skipped"`; `foreign_5d_net_buy` and `trust_5d_net_buy` have `status="scored"` with non-zero points
- [x] 9.4 Run `pytest tests/test_scoring_engine_real_subscorers.py -q`

## 10. Remove the placeholder

- [x] 10.1 Delete `src/ohmystock/scoring/_placeholder.py`
- [x] 10.2 Replace `from ohmystock.scoring import _placeholder  # noqa: F401` with `from ohmystock.scoring import subscorers  # noqa: F401` in `src/ohmystock/scoring/__init__.py` (consolidate so only the subscorers import remains)
- [x] 10.3 Delete `tests/test_scoring_placeholder.py`
- [x] 10.4 Delete `tests/test_scoring_engine_e2e.py` (replaced by `test_scoring_engine_real_subscorers.py`)
- [x] 10.5 Update `tests/test_scoring_engine_real_subscorers.py` expectations: `subscores` length is now 6 (no placeholder), `final_score == 34`
- [x] 10.6 Run `pytest tests/test_scoring_*.py tests/test_subscorer_*.py -q`; all pass

## 11. Reverse-import isolation guard

- [x] 11.1 Run `tests/test_scoring_reverse_import.py` (existing) and confirm `import ohmystock.scoring` still does not pull `fastapi`/`uvicorn`/`starlette` after sub-scorer additions
- [x] 11.2 If the test does not already cover `import ohmystock.scoring.subscorers` directly, extend it to assert the same isolation for the subscorers package

## 12. Whole-suite verification

- [x] 12.1 Run `pytest -q` on the entire test suite; confirm green
- [x] 12.2 Run `python -c "from ohmystock.scoring import score_watchlist; from ohmystock.scoring.registry import list_subscorers; print(list_subscorers())"` and visually confirm exactly 6 entries: `foreign_5d_net_buy, stage_2_confirmed, trend_structure_ma, trend_template_8, trust_5d_net_buy, volume_breakout_obv`
- [x] 12.3 Confirm `_always_zero_placeholder` is **not** in the registry output

## 13. OpenSpec validation

- [x] 13.1 Run `openspec validate phase-2b-shipped-subscorers --strict` and confirm no errors
- [x] 13.2 Run `openspec status --change phase-2b-shipped-subscorers` and confirm `isComplete: true` (or all `applyRequires` artifacts done)
