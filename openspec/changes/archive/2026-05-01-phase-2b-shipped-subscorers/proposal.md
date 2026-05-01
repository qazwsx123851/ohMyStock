## Why

`phase-2b-scoring-engine` shipped the engine and registry but only one `_always_zero_placeholder` sub-scorer — every candidate currently scores `0` regardless of fundamentals. This change replaces the placeholder with **real sub-scorers backed by data already in our SQLite caches** (`get_kline`, `get_three_major_investors`, `get_margin_short`), so the daily Phase 2B run can begin producing meaningful `final_score` values that drive the LLM Decider gate at 65 (`workflow-cheatsheet.md` §6.1). Sub-scorers that depend on data sources we have **not yet implemented** (broker concentration, futures OI, TDCC, quarterly EPS, monthly revenue, news, analyst targets, search heat) stay out of this change and ship as deferred-stubs in `phase-2b-deferred-cli`.

## What Changes

- **DELETE** `src/ohmystock/scoring/_placeholder.py` and its registration in `scoring/__init__.py`. The corresponding placeholder requirement in `phase-2b-scoring-engine` capability is **REMOVED** (delta).
- **DELETE** `tests/test_scoring_placeholder.py`.
- Add 6 real sub-scorers backed by data we already cache, each as a pure `(ScoringContext) -> SubScoreResult` function registered via `@register_subscorer(...)`:
  - **Technical (4 sub-scorers, 25 of 40 cap):**
    - `trend_structure_ma` (10): `close > 5MA`, `5MA > 20MA`, `20MA > 60MA` — 3 conditions, all-or-nothing.
    - `trend_template_8` (5): Mark Minervini's 8 SEPA Trend Template conditions all true.
    - `stage_2_confirmed` (5): Stan Weinstein Stage 2 — `close > 30W MA (≈150-day)`, 30W MA rising, current price within 25% of 52-week high and ≥ 30% above 52-week low.
    - `volume_breakout_obv` (5): close breaks above 20-day high AND day-volume ≥ 1.4× 20-day average AND 5-day OBV slope positive.
  - **Chip (2 sub-scorers, 9 of 25 cap):**
    - `foreign_5d_net_buy` (5): `sum(foreign_net, last 5 trading days) > 0`, scaled `0..5` by lots threshold (band-based, full points at ≥ 1000 lots).
    - `trust_5d_net_buy` (4): `sum(invest_trust_net, last 5 trading days) > 0`, scaled `0..4` (full points at ≥ 500 lots).
- Each sub-scorer lives in its own file under `src/ohmystock/scoring/subscorers/` and is wired into the registry via an explicit import in `scoring/__init__.py` (matching the placeholder pattern). Engine code in `_engine.py` is **not** touched.
- New unit tests `tests/test_subscorer_<name>.py` per sub-scorer with synthetic `ScoringContext` literals — no data-layer mocks needed since sub-scorers are pure.
- New end-to-end test `tests/test_scoring_engine_real_subscorers.py` replacing `test_scoring_engine_e2e.py` — confirms `score_watchlist` produces a non-zero `final_score` when given a synthetic-but-realistic `ScoringContext`.
- Reverse-import isolation guard updated in `tests/test_scoring_reverse_import.py` (already exists) — confirms adding sub-scorers does not pull `fastapi`/`uvicorn`/`starlette`.

**Out of scope (next change `phase-2b-deferred-cli`):**
- 16 deferred-stub sub-scorers returning `status="skipped"`: K-line patterns (8), RS Percentile (7), broker concentration (7), futures OI (3), margin tightening (2), borrow change (-3..+2), TDCC concentration (2), EPS YoY (8), EPS QoQ (5), monthly revenue YoY (6), quarterly revenue YoY (3), institutional 30-day holding (3), analyst target upgrades (3), SUE (3), important announcements (2), search heat (-2..+2).
- `ohmystock score watchlist` CLI subcommand.
- Catalyst correction (`+5` / `-10`) and monthly-revenue bonus (`+5`) — land with their respective sub-scorers.
- WFA / SEPA golden-sample calibration of point bands — happens after all sub-scorers exist.

## Capabilities

### New Capabilities
_(None — this change adds requirements to the existing `phase-2b-scoring-engine` capability.)_

### Modified Capabilities
- `phase-2b-scoring-engine`: REMOVES the placeholder requirement (`_always_zero_placeholder`), ADDS six real sub-scorer requirements (trend structure / Trend Template / Stage 2 / volume breakout / foreign 5-day / trust 5-day) and a sub-scorer file-layout requirement (`subscorers/` package with one file per sub-scorer).

## Impact

- **New code:**
  - `src/ohmystock/scoring/subscorers/__init__.py` — package marker; imports each sub-scorer module to trigger registration.
  - `src/ohmystock/scoring/subscorers/trend_structure_ma.py`
  - `src/ohmystock/scoring/subscorers/trend_template_8.py`
  - `src/ohmystock/scoring/subscorers/stage_2_confirmed.py`
  - `src/ohmystock/scoring/subscorers/volume_breakout_obv.py`
  - `src/ohmystock/scoring/subscorers/foreign_5d_net_buy.py`
  - `src/ohmystock/scoring/subscorers/trust_5d_net_buy.py`
  - `tests/test_subscorer_trend_structure_ma.py`, `tests/test_subscorer_trend_template_8.py`, `tests/test_subscorer_stage_2_confirmed.py`, `tests/test_subscorer_volume_breakout_obv.py`, `tests/test_subscorer_foreign_5d_net_buy.py`, `tests/test_subscorer_trust_5d_net_buy.py`.
  - `tests/test_scoring_engine_real_subscorers.py`.
- **Edited code:**
  - `src/ohmystock/scoring/__init__.py` — replace `_placeholder` import with `subscorers` package import.
- **Deleted code:**
  - `src/ohmystock/scoring/_placeholder.py`
  - `tests/test_scoring_placeholder.py`
- **Code consumed (no edits):**
  - `ohmystock.indicators.core.sma`, `ohmystock.indicators.core.ema` — for moving averages.
  - Existing `BarRow`, `three_major` rows, `margin_short` rows shapes.
  - `ohmystock.scoring.registry.register_subscorer`, `dispatch`, `list_subscorers`.
  - `ohmystock.scoring.context.ScoringContext`.
  - `ohmystock.scoring.models.SubScoreResult`.
- **DB / migrations:** none.
- **Tools / contracts:** future `phase_2b_tool` registration still deferred to LLM Decider change.
- **Docs:** `workflow-cheatsheet.md` §5/§10 remain SSOT; no doc edits required. `openspec/specs/phase-2b-scoring-engine/spec.md` will absorb the delta on archive.
