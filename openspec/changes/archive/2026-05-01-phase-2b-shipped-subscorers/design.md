## Context

`phase-2b-scoring-engine` (archived 2026-05-01) shipped the engine, registry, Pydantic contracts, Risk-Off ceiling, and one `_always_zero_placeholder` sub-scorer. The engine reads `bars` (250-day), `three_major` (30-day), and `margin_short` (30-day) per candidate from existing SQLite caches. Real sub-scorers were deferred to this change so the engine PR stayed reviewable. The `workflow-cheatsheet.md` §5/§10 rubric defines 22 sub-scorers across 4 categories totaling 100 points; this change ships 6 of them — the subset whose required data is already cached today (TWSE OHLCV, three-major lots, margin/short balance). The remaining 16 sub-scorers depend on data sources we have not yet implemented (broker concentration, futures OI, TDCC, quarterly EPS, monthly revenue, news, analyst targets, search heat) and ship as deferred-stubs in `phase-2b-deferred-cli`.

The contracts that callers depend on (`Phase2BCandidate`, `SubScoreResult`, envelope shape, registry decorator, Risk-Off ceiling) do not change in this change. Only the **set of registered sub-scorers** changes.

## Goals / Non-Goals

**Goals:**
- Replace the placeholder with 6 real sub-scorers totaling **34 max points** (technical: 25 of 40 cap; chip: 9 of 25 cap; fundamental/sentiment: 0 each). Final-score range with this change alone is `[0, 34]` — by design below the 65 green-light threshold; full 100-point coverage arrives after `phase-2b-deferred-cli` plus future calibration.
- Each sub-scorer is a **pure function** of `(ScoringContext) -> SubScoreResult` — no I/O, no globals, no side effects beyond the registry decorator. Synthetic-context unit tests cover every band.
- File-per-sub-scorer layout under `src/ohmystock/scoring/subscorers/` so adding/removing a sub-scorer is a one-file change. Engine in `_engine.py` is **not** edited.
- Three result statuses are honored: `scored` (data sufficient), `skipped` (data window too short for a valid signal), `error` (only on unexpected exceptions; clamped + caught by registry).
- Placeholder is fully removed (file + tests + spec requirement) so production output never carries a dead row.

**Non-Goals:**
- Calibration of point bands to historical SEPA winners — happens after all 22 sub-scorers exist (`workflow-cheatsheet.md` §12 SEPA Golden Sample WFA).
- The remaining 16 sub-scorers — `phase-2b-deferred-cli`.
- `ohmystock score watchlist` CLI subcommand — `phase-2b-deferred-cli`.
- Caching of sub-scorer outputs.
- Engine-level changes (no edits to `_engine.py`, `registry.py`, `models.py`, `context.py`).
- Catalyst correction (+5 / -10) and monthly-revenue bonus (+5) — those land alongside their owning sub-scorers.

## Decisions

### D1. File layout: one sub-scorer per file under `subscorers/`

```
src/ohmystock/scoring/
├── __init__.py        # imports subscorers package to trigger registration
├── _engine.py         # untouched
├── context.py         # untouched
├── models.py          # untouched
├── registry.py        # untouched
└── subscorers/
    ├── __init__.py                  # imports each module below
    ├── trend_structure_ma.py
    ├── trend_template_8.py
    ├── stage_2_confirmed.py
    ├── volume_breakout_obv.py
    ├── foreign_5d_net_buy.py
    └── trust_5d_net_buy.py
```

**Why:** matches the placeholder pattern (which lived as a single module); each sub-scorer is reviewable in isolation; deletion is `rm <file>` + drop one import line. The `subscorers/__init__.py` is the single import surface the package `__init__.py` consumes.
**Alternative rejected:** one `subscorers.py` file with all functions — couples reviews of unrelated rubric lines and grows unbounded as the remaining 16 land. Folder-per-category was considered but adds a second level of indirection for no current benefit at 6 sub-scorers.

### D2. Sub-scorers are pure; the registry decorator is the only side effect

```python
# src/ohmystock/scoring/subscorers/trend_structure_ma.py
from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreResult
from ohmystock.scoring.registry import register_subscorer

@register_subscorer(category="technical", name="trend_structure_ma", max_points=10)
def trend_structure_ma(ctx: ScoringContext) -> SubScoreResult:
    ...
```

Functions accept `ScoringContext` and return `SubScoreResult`. They never call data layers, never mutate `ctx`, never read settings. Tests construct `ScoringContext` literals — no mocks, no fixtures.

**Why:** the engine pre-loads the context (D3 in `phase-2b-scoring-engine` design); putting I/O inside sub-scorers would break that contract and re-introduce the test surface area we just paid down.

### D3. Insufficient data → `status="skipped"`, not `"error"`

When a sub-scorer needs N bars (e.g., `trend_template_8` needs 250 for the 200-day MA + 52-week range) and `len(ctx.bars) < N`, it returns `status="skipped"`, `points=0`, `evidence={"reason": "insufficient_bars", "have": <int>, "need": <int>}`. `error_message` stays `None`.

**Why:** `status="error"` is reserved for **unexpected** failures (cache schema drift, registry corruption, unhandled exception). Insufficient history is **expected** for newly-listed symbols and not a defect — the engine's existing aggregator already excludes `skipped` from sums (per `phase-2b-scoring-engine` D4). Surfacing it as `skipped` keeps the LLM Decider's input assembler honest about coverage without polluting the error channel.

**Status decision rule per sub-scorer:**

| Sub-scorer            | Min data required                                 | Skipped when                                  |
|-----------------------|---------------------------------------------------|-----------------------------------------------|
| trend_structure_ma    | 60 bars (for 60-day MA tail)                     | `len(ctx.bars) < 60`                          |
| trend_template_8      | 250 bars (for 200-day MA + 52-week range)        | `len(ctx.bars) < 250`                         |
| stage_2_confirmed     | 252 bars (for 30-week MA + 52-week range)        | `len(ctx.bars) < 252`                         |
| volume_breakout_obv   | 21 bars (20-day high + 1 breakout day, OBV slope on last 5) | `len(ctx.bars) < 21`               |
| foreign_5d_net_buy    | 5 three_major rows                                | `len(ctx.three_major) < 5`                    |
| trust_5d_net_buy      | 5 three_major rows                                | `len(ctx.three_major) < 5`                    |

### D4. Band-based scoring functions live with their sub-scorer, not in a shared module

Each sub-scorer that has bands (e.g., `foreign_5d_net_buy`'s lots → points mapping) implements the band inline. No `_bands.py` shared helper.

**Why:** SEPA calibration is going to retune individual bands one-at-a-time after WFA. Co-locating the band with the sub-scorer makes "tune one rubric line" a one-file diff. A shared helper would create cross-sub-scorer coupling that calibration churn keeps breaking.
**Alternative rejected:** generic `linear_band(x, brackets)` utility — saves ~5 lines per sub-scorer at the cost of obscuring the rubric. Per-sub-scorer prose tables in the file (in code, not docstrings) are easier to align against `workflow-cheatsheet.md` §10.

### D5. Sub-scorer formulas (precise, derived from cheatsheet §5/§10 + Minervini SEPA + Weinstein Stage 2)

All formulas use closing prices from `ctx.bars` (where `bars[i] = {ts, o, h, l, c, v, amount}`). MAs computed via existing `ohmystock.indicators.core.sma`. Index `-1` is the latest (most recent date) bar, matching `get_kline`'s ascending-by-date order.

**5.1 trend_structure_ma (max_points=10, technical)**
```
close       = bars[-1].c
ma5         = sma(closes, 5)[-1]
ma20        = sma(closes, 20)[-1]
ma60        = sma(closes, 60)[-1]
conditions  = [close > ma5, ma5 > ma20, ma20 > ma60]
points      = 10 if all(conditions) else 0      # all-or-nothing
status      = "scored"
evidence    = {"close": close, "ma5": ma5, "ma20": ma20, "ma60": ma60, "conditions_passed": int(sum(conditions))}
```
Skipped when `len(bars) < 60` (60-day MA needs 60 bars).

**Why all-or-nothing:** the cheatsheet §10 line `趨勢結構（均線多頭/EMA/布林）10` is a binary qualification gate in SEPA literature ("the stock must be in an uptrend on the daily chart"). Partial-credit scaling pulls in noisy candidates that the green-light gate at 65 specifically wants to filter out.

**5.2 trend_template_8 (max_points=5, technical)** — Mark Minervini's 8 conditions:
```
close       = bars[-1].c
ma50        = sma(closes, 50)[-1]
ma150       = sma(closes, 150)[-1]
ma200       = sma(closes, 200)[-1]
ma200_22ago = sma(closes, 200)[-23]               # 200-MA value 22 trading days earlier
high_52w    = max(bar.h  for bar in bars[-252:])
low_52w     = min(bar.l  for bar in bars[-252:])

conds = [
    close > ma150 and close > ma200,                                  # 1
    ma150 > ma200,                                                    # 2
    ma200 > ma200_22ago,                                              # 3 (200-MA trending up ≥1 month)
    ma50 > ma150 and ma50 > ma200,                                    # 4
    close > ma50,                                                     # 5
    close >= 1.30 * low_52w,                                          # 6 (≥30% above 52w low)
    close >= 0.75 * high_52w,                                         # 7 (within 25% of 52w high)
    # condition 8 (RS rank ≥ 70) deferred to RS Percentile sub-scorer in phase-2b-deferred-cli
]
all_pass    = all(conds)
points      = 5 if all_pass else 0                                    # all-or-nothing
status      = "scored"
evidence    = {"conditions_passed": int(sum(conds)), "of": len(conds), ...individual flags...}
```
Skipped when `len(bars) < 252`.

**Why 7 of 8 conditions, not 8:** the 8th condition is "RS Rank ≥ 70" which requires the universe-relative RS Percentile sub-scorer (cheatsheet §5 line `RS Percentile 7`) — that's deferred. Trend Template here gives full 5 points only when all SEPA-trend conditions are true; the RS confirmation arrives via its own sub-scorer in the deferred change. This is consistent with the rubric's separation (`Trend Template 8/8 全過 5` and `RS Percentile 7` are listed as two separate lines summing to 12 points).

**5.3 stage_2_confirmed (max_points=5, technical)** — Stan Weinstein Stage 2:
```
close       = bars[-1].c
ma150       = sma(closes, 150)[-1]                # ≈ 30-week MA on daily bars
ma150_5ago  = sma(closes, 150)[-6]                # rising over 5 days
high_52w    = max(bar.h  for bar in bars[-252:])
low_52w     = min(bar.l  for bar in bars[-252:])

conds = [
    close > ma150,                                # above 30W MA
    ma150 > ma150_5ago,                           # 30W MA rising
    close >= 1.30 * low_52w,                      # ≥30% above 52w low
    close >= 0.75 * high_52w,                     # within 25% of 52w high
]
points      = 5 if all(conds) else 0              # all-or-nothing
status      = "scored"
```
Skipped when `len(bars) < 252` (need 150-MA + 52-week window).

**Note:** Stage 2 and Trend Template share the 52-week range and a long MA — this is intentional in the cheatsheet (§5 lists both as separate 5-point lines). They reinforce each other; passing both requires the strongest tape.

**5.4 volume_breakout_obv (max_points=5, technical)**
```
high_20d_prior = max(bar.h for bar in bars[-21:-1])   # 20-day high EXCLUDING today
close          = bars[-1].c
vol_today      = bars[-1].v
avg_vol_20d    = mean(bar.v for bar in bars[-21:-1])
obv            = cumulative_sum(sign(close_diff) * volume) over last 6 bars
obv_slope_5d   = obv[-1] - obv[-6]                    # positive = accumulation

conds = [
    close > high_20d_prior,                           # breakout
    vol_today >= 1.4 * avg_vol_20d,                   # volume ≥ 1.4× 20d avg
    obv_slope_5d > 0,                                 # OBV trending up
]
points         = 5 if all(conds) else 0               # all-or-nothing
status         = "scored"
```
Skipped when `len(bars) < 21`.

**5.5 foreign_5d_net_buy (max_points=5, chip)**
```
last_5_rows = ctx.three_major[-5:]                    # 5 most recent trading days
net_5d      = sum(row["foreign_net"] for row in last_5_rows)   # lots
points      = (
    0   if net_5d <= 0
    else 1 if net_5d <= 200
    else 2 if net_5d <= 500
    else 3 if net_5d <= 1000
    else 5                                            # ≥ 1000 lots
)
status      = "scored"
evidence    = {"net_5d_lots": net_5d, "rows_used": len(last_5_rows)}
```
Skipped when `len(ctx.three_major) < 5`.

**Why 1000 lots for full points:** at TSMC's ~$1000 NTD price, 1000 lots ≈ NT$1B / day × 5 days = NT$5B foreign net buy — institutionally significant on a single name. The mid-tier (200/500) reflects mid-cap accumulation.

**5.6 trust_5d_net_buy (max_points=4, chip)**
```
last_5_rows = ctx.three_major[-5:]
net_5d      = sum(row["invest_trust_net"] for row in last_5_rows)
points      = (
    0   if net_5d <= 0
    else 1 if net_5d <= 100
    else 2 if net_5d <= 300
    else 4                                            # ≥ 500 lots → full 4 pts (no 3-pt tier)
)
status      = "scored"
```
Skipped when `len(ctx.three_major) < 5`.

**Why no 3-point tier:** the cheatsheet §5 line is `投信 5 日淨買超 4`. Mapping `0 / 1 / 2 / 4` matches the 0-or-thresholded structure of foreign with one fewer tier (since trust positions are typically smaller).

### D6. Engine wiring: package `__init__.py` imports `subscorers` package, which imports each module

```python
# src/ohmystock/scoring/__init__.py  (post-change)
from ohmystock.scoring.models import Phase2BCandidate, SubScoreResult
from ohmystock.scoring import registry  # noqa: F401
from ohmystock.scoring import subscorers  # noqa: F401 — registers all real sub-scorers
from ohmystock.scoring._engine import score_watchlist

__all__ = ["score_watchlist", "Phase2BCandidate", "SubScoreResult"]
```

```python
# src/ohmystock/scoring/subscorers/__init__.py
from ohmystock.scoring.subscorers import trend_structure_ma  # noqa: F401
from ohmystock.scoring.subscorers import trend_template_8  # noqa: F401
from ohmystock.scoring.subscorers import stage_2_confirmed  # noqa: F401
from ohmystock.scoring.subscorers import volume_breakout_obv  # noqa: F401
from ohmystock.scoring.subscorers import foreign_5d_net_buy  # noqa: F401
from ohmystock.scoring.subscorers import trust_5d_net_buy  # noqa: F401
```

The placeholder import line is **removed**. `_placeholder.py` is deleted. The deferred-stubs change (next change) will add a `subscorers/_deferred.py` (or similar) with one `@register_subscorer` per stub, returning `status="skipped"` — no edits to `_engine.py` or this `__init__.py` either time.

**Why explicit imports, not pkgutil/iter_modules autodiscover:** explicit imports keep import order deterministic, surface failures at package import (not at `score_watchlist` call time), and let reviewers see "what registers" in one file.

### D7. Test strategy: synthetic ScoringContext literals only

```python
# tests/test_subscorer_trend_structure_ma.py
from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.subscorers.trend_structure_ma import trend_structure_ma

def _ctx_with_closes(closes: list[float]) -> ScoringContext:
    bars = [{"ts": f"2026-04-{i:02d}", "o": c, "h": c, "l": c, "c": c, "v": 1000, "amount": 1000} for i, c in enumerate(closes, 1)]
    return ScoringContext(asof_date="2026-04-30", symbol="2330", bars=bars, three_major=[], margin_short=[])

def test_full_uptrend_scores_10():
    closes = list(range(1, 121))   # monotonic uptrend, 120 bars
    res = trend_structure_ma(_ctx_with_closes(closes))
    assert res.points == 10 and res.status == "scored"
```

**Why direct-call tests, not `dispatch()` tests:** sub-scorer tests verify the scoring logic; registry behavior (clamp, metadata overwrite) is already covered in the engine change's `test_scoring_registry.py`. Direct-call tests are also faster and surface failures at the function level rather than after registry indirection.

For each sub-scorer ship at minimum: 1 happy-path (full points), 1 boundary at each band threshold, 1 zero-points case, 1 `skipped` case (insufficient data).

The end-to-end test `tests/test_scoring_engine_real_subscorers.py` constructs a `ScoringContext` (via mocked `get_kline`/`get_three_major_investors`/`get_margin_short`) where all 6 sub-scorers `score`, asserts `final_score == sum_of_full_points` (= 34), classification == `red` (since 34 < 50), and the `subscores` list has length 6 (no placeholder).

### D8. Removing the placeholder — files, tests, and spec requirement

**Files to delete:**
- `src/ohmystock/scoring/_placeholder.py`
- `tests/test_scoring_placeholder.py`
- `tests/test_scoring_engine_e2e.py` (replaced by `test_scoring_engine_real_subscorers.py`)

**`__init__.py` edit:** drop the `from ohmystock.scoring import _placeholder` line; replace with `from ohmystock.scoring import subscorers`.

**Spec delta:** REMOVE the `Always-zero placeholder sub-scorer is registered` requirement (no migration needed — placeholder was internal scaffolding, never user-facing). ADD the new sub-scorer requirements.

**Why no soft-delete:** the placeholder's only purpose was end-to-end testability before real sub-scorers existed. Once real ones exist, the placeholder is dead weight that pollutes every candidate's `subscores` list.

### D9. Reverse-import isolation

The existing `tests/test_scoring_reverse_import.py` already verifies importing `ohmystock.scoring` does not pull `fastapi`/`uvicorn`/`starlette`. New sub-scorers MUST not import any of those (they only use `indicators`, `context`, `models`, `registry`). The existing test is sufficient; we add the same guard at module level for `ohmystock.scoring.subscorers` if it grows enough to deserve one (deferred — current test catches the regression at the package level).

## Risks / Trade-offs

- **[Score ceiling at 34/100 makes the green-light gate at 65 unreachable until `phase-2b-deferred-cli` ships]** → No green-light candidates emerge during this interim. Mitigation: documented as expected; `phase-2b-deferred-cli` follows immediately. Operational impact is zero today since the LLM Decider is also pre-implementation. Daily Phase 2B output is still useful for monitoring the engine and developing dashboards.
- **[Trend Template's deferred RS condition might cause "5-point Trend Template + 0-point RS"]** → A candidate that fails the universe-RS check still scores all 5 trend-template points, which the cheatsheet treats as a separate line. This is the cheatsheet's design (§5 splits them), but a reader might assume "Trend Template" semantically includes RS. Mitigation: `evidence` documents the deferred condition explicitly; `phase-2b-deferred-cli` ships RS Percentile, restoring the SEPA semantics.
- **[Lots-thresholds in foreign/trust 5-day are uncalibrated]** → The bands `200/500/1000` and `100/300/500` are educated guesses, not WFA-validated. Mitigation: marked as `# TODO(calibration)` in code; SEPA Golden Sample WFA (`workflow-cheatsheet.md` §12) calibrates after deferred-stubs ship. Bands live in their sub-scorer files (D4) so calibration is a single-file edit per sub-scorer.
- **[All-or-nothing scoring on Trend Template / Stage 2 is high-variance]** → A candidate failing one of 7 conditions drops 5 points. Mitigation: `evidence.conditions_passed` lets the LLM Decider see partial passes; partial-credit scaling can be added in a calibration change after seeing real distributions.
- **[`status="skipped"` candidates with short history score 0 silently]** → A newly-listed symbol with < 252 bars contributes nothing to `final_score` from the technical category. Mitigation: per-sub-scorer `evidence.reason="insufficient_bars"` makes it visible; the screener (`screener-tw-universe`) will not surface < 60-bar candidates anyway. Acceptable trade-off vs. fabricating scores from short history.
- **[Removing `_placeholder.py` breaks any external code that imports it]** → No external code imports it; it's an internal module. `tests/test_scoring_placeholder.py` is the only consumer and is also deleted.
- **[Engine end-to-end test gets larger]** → `test_scoring_engine_real_subscorers.py` has to construct realistic synthetic bars (≥ 252 bars, multiple chip rows) to drive all 6 sub-scorers to "scored". Mitigation: a single `_make_realistic_ctx()` helper in the test file; one happy-path test + one mixed-status test cover engine integration.

## Migration Plan

- **Order of edits within the change:**
  1. Add `subscorers/` package with all 6 modules and tests.
  2. Add the new end-to-end test (still passes alongside the placeholder).
  3. Verify everything passes with both placeholder + new sub-scorers.
  4. Delete `_placeholder.py`, drop the import, delete `test_scoring_placeholder.py` and `test_scoring_engine_e2e.py`.
  5. Re-run the full test suite.
- **DB / migrations:** none.
- **Rollback:** revert the change; placeholder behavior is restored. Nothing else depends on the new sub-scorer symbols yet (no CLI, no tool, no frontend).

## Open Questions

- **Q1.** Should the lots-thresholds in `foreign_5d_net_buy` / `trust_5d_net_buy` be normalized by the candidate's average daily volume (so a small-cap with proportionally large foreign buying scores like a large-cap)? **Tentative:** no for now — cheatsheet §10 specifies absolute lots; revisit during SEPA calibration.
- **Q2.** Should `volume_breakout_obv` distinguish "breakout" vs "near breakout" (e.g., within 1% of 20-day high)? **Tentative:** no — the cheatsheet uses strict breakout; near-breakout signals belong in the K-line patterns sub-scorer (deferred).
- **Q3.** When `len(bars) >= 60` but `< 252`, should `trend_template_8` and `stage_2_confirmed` partial-evaluate (e.g., compute 200-MA against shorter window)? **Tentative:** no — `skipped` keeps the rubric's semantics intact and avoids "score X looks similar to score Y" confusion. Resolved as `skipped` per D3.
