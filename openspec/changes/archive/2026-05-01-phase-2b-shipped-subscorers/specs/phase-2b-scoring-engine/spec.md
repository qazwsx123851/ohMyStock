## ADDED Requirements

### Requirement: Sub-scorer file layout under `subscorers/` package

The package `ohmystock.scoring` SHALL contain a sub-package `ohmystock.scoring.subscorers` with one Python module per registered sub-scorer. Each module SHALL define exactly one function decorated with `@register_subscorer(...)`. The package's `__init__.py` SHALL explicitly import each sub-scorer module so that registration happens at package import time. The top-level `ohmystock/scoring/__init__.py` SHALL import `ohmystock.scoring.subscorers` (replacing the prior `_placeholder` import). Sub-scorer modules MUST NOT import `fastapi`, `uvicorn`, `starlette`, or any I/O-performing module beyond `ohmystock.indicators`, `ohmystock.scoring.context`, `ohmystock.scoring.models`, and `ohmystock.scoring.registry`.

#### Scenario: Subscorers package is importable
- **WHEN** `import ohmystock.scoring.subscorers` runs
- **THEN** the import succeeds without `ImportError` and `list_subscorers()` includes every sub-scorer registered in this change

#### Scenario: Sub-scorer modules are pure
- **WHEN** any module under `ohmystock/scoring/subscorers/*.py` is imported
- **THEN** it does not pull `fastapi`, `uvicorn`, or `starlette` into `sys.modules`

### Requirement: trend_structure_ma sub-scorer

The system SHALL register a sub-scorer named `trend_structure_ma` in category `technical` with `max_points=10`. Given a `ScoringContext`, when `len(ctx.bars) < 60` it SHALL return `SubScoreResult(status="skipped", points=0, evidence={"reason": "insufficient_bars", "have": <int>, "need": 60})`. Otherwise it SHALL compute `close = bars[-1]["c"]`, `ma5 = sma(closes, 5)[-1]`, `ma20 = sma(closes, 20)[-1]`, `ma60 = sma(closes, 60)[-1]` (where `closes = [bar["c"] for bar in bars]`), and award `points = 10` only when **all three** of (`close > ma5`, `ma5 > ma20`, `ma20 > ma60`) hold; otherwise `points = 0`. `status` MUST be `"scored"` when `len(ctx.bars) >= 60`. `evidence` MUST include keys `close`, `ma5`, `ma20`, `ma60`, `conditions_passed` (int).

#### Scenario: All three conditions hold scores 10
- **GIVEN** `ctx.bars` with 120 monotonically-increasing closes (1, 2, ..., 120)
- **WHEN** `trend_structure_ma(ctx)` is called
- **THEN** `points == 10`, `status == "scored"`, `evidence["conditions_passed"] == 3`

#### Scenario: One condition fails scores 0
- **GIVEN** `ctx.bars` of length 120 where `close < ma5` (e.g., closes step up then drop on the last bar)
- **WHEN** `trend_structure_ma(ctx)` is called
- **THEN** `points == 0`, `status == "scored"`, `evidence["conditions_passed"] < 3`

#### Scenario: Insufficient bars yields skipped
- **GIVEN** `ctx.bars` of length 30
- **WHEN** `trend_structure_ma(ctx)` is called
- **THEN** `points == 0`, `status == "skipped"`, `evidence["reason"] == "insufficient_bars"`, `evidence["have"] == 30`, `evidence["need"] == 60`

### Requirement: trend_template_8 sub-scorer

The system SHALL register a sub-scorer named `trend_template_8` in category `technical` with `max_points=5`. Given a `ScoringContext`, when `len(ctx.bars) < 252` it SHALL return `status="skipped"`, `points=0`, `evidence={"reason": "insufficient_bars", "have": <int>, "need": 252}`. Otherwise it SHALL evaluate **seven** Mark Minervini SEPA Trend Template conditions on the latest bar:

1. `close > ma150 and close > ma200`
2. `ma150 > ma200`
3. `ma200 > ma200_22ago` (200-day MA value 22 trading days earlier)
4. `ma50 > ma150 and ma50 > ma200`
5. `close > ma50`
6. `close >= 1.30 * low_52w` (≥30% above 52-week low)
7. `close >= 0.75 * high_52w` (within 25% of 52-week high)

(The 8th original Minervini condition — RS Rank ≥ 70 — is deferred to the `RS Percentile` sub-scorer in `phase-2b-deferred-cli`.)

`points` SHALL be `5` only when **all seven** conditions hold; otherwise `0`. `status` MUST be `"scored"` when `len(ctx.bars) >= 252`. `evidence` MUST include `conditions_passed` (int) and `of` (int = 7) plus a per-condition flag map `cond1`..`cond7`.

#### Scenario: All seven conditions hold scores 5
- **GIVEN** `ctx.bars` length 252 representing a clean SEPA uptrend (closes rising, 50/150/200-MAs aligned upward, latest close near 52-week high)
- **WHEN** `trend_template_8(ctx)` is called
- **THEN** `points == 5`, `status == "scored"`, `evidence["conditions_passed"] == 7`, `evidence["of"] == 7`

#### Scenario: Six of seven conditions hold scores 0
- **GIVEN** `ctx.bars` length 252 where condition 7 fails (close 30% below 52-week high)
- **WHEN** `trend_template_8(ctx)` is called
- **THEN** `points == 0`, `status == "scored"`, `evidence["conditions_passed"] == 6`

#### Scenario: Insufficient bars yields skipped
- **GIVEN** `ctx.bars` length 100
- **WHEN** `trend_template_8(ctx)` is called
- **THEN** `points == 0`, `status == "skipped"`, `evidence["have"] == 100`, `evidence["need"] == 252`

### Requirement: stage_2_confirmed sub-scorer

The system SHALL register a sub-scorer named `stage_2_confirmed` in category `technical` with `max_points=5`. Given a `ScoringContext`, when `len(ctx.bars) < 252` it SHALL return `status="skipped"`, `points=0`. Otherwise it SHALL evaluate Stan Weinstein's Stage 2 conditions:

1. `close > ma150` (above 30-week MA, approximated as 150-day MA on daily bars)
2. `ma150 > ma150_5ago` (30-week MA rising over the prior 5 sessions)
3. `close >= 1.30 * low_52w` (≥30% above 52-week low)
4. `close >= 0.75 * high_52w` (within 25% of 52-week high)

`points` SHALL be `5` only when **all four** conditions hold; otherwise `0`. `status` MUST be `"scored"` when `len(ctx.bars) >= 252`. `evidence` MUST include per-condition flags and `conditions_passed`.

#### Scenario: All four Stage 2 conditions hold scores 5
- **GIVEN** `ctx.bars` length 252 with closes in a clean Stage 2 advance (close > rising 150-MA, near 52-week high)
- **WHEN** `stage_2_confirmed(ctx)` is called
- **THEN** `points == 5`, `status == "scored"`, `evidence["conditions_passed"] == 4`

#### Scenario: 30-week MA flat scores 0
- **GIVEN** `ctx.bars` length 252 where `ma150 == ma150_5ago` (flat MA)
- **WHEN** `stage_2_confirmed(ctx)` is called
- **THEN** `points == 0`, `status == "scored"`, `evidence["conditions_passed"] < 4`

#### Scenario: Insufficient bars yields skipped
- **GIVEN** `ctx.bars` length 200
- **WHEN** `stage_2_confirmed(ctx)` is called
- **THEN** `points == 0`, `status == "skipped"`, `evidence["need"] == 252`

### Requirement: volume_breakout_obv sub-scorer

The system SHALL register a sub-scorer named `volume_breakout_obv` in category `technical` with `max_points=5`. Given a `ScoringContext`, when `len(ctx.bars) < 21` it SHALL return `status="skipped"`. Otherwise it SHALL compute:

- `high_20d_prior = max(bar["h"] for bar in bars[-21:-1])` — 20-day high **excluding** today
- `close = bars[-1]["c"]`
- `vol_today = bars[-1]["v"]`
- `avg_vol_20d = mean(bar["v"] for bar in bars[-21:-1])`
- `obv` cumulative over the last 6 bars (each step adds `+v` if close went up, `-v` if down, `0` if flat)
- `obv_slope_5d = obv[-1] - obv[-6]`

`points` SHALL be `5` only when **all three** hold: (a) `close > high_20d_prior`, (b) `vol_today >= 1.4 * avg_vol_20d`, (c) `obv_slope_5d > 0`; otherwise `0`. `status` MUST be `"scored"` when `len(ctx.bars) >= 21`. `evidence` MUST include `breakout`, `volume_ratio`, `obv_slope_5d`, `conditions_passed`.

#### Scenario: Breakout with volume and rising OBV scores 5
- **GIVEN** `ctx.bars` length 21 where day -1 has the highest high, `close > prior 20-day high`, `volume == 1.5× 20-day avg`, OBV slope positive
- **WHEN** `volume_breakout_obv(ctx)` is called
- **THEN** `points == 5`, `status == "scored"`, `evidence["conditions_passed"] == 3`

#### Scenario: Breakout but low volume scores 0
- **GIVEN** `ctx.bars` length 21 where breakout occurs but `volume < 1.4× 20-day avg`
- **WHEN** `volume_breakout_obv(ctx)` is called
- **THEN** `points == 0`, `status == "scored"`, `evidence["volume_ratio"] < 1.4`

#### Scenario: Insufficient bars yields skipped
- **GIVEN** `ctx.bars` length 10
- **WHEN** `volume_breakout_obv(ctx)` is called
- **THEN** `points == 0`, `status == "skipped"`

### Requirement: foreign_5d_net_buy sub-scorer

The system SHALL register a sub-scorer named `foreign_5d_net_buy` in category `chip` with `max_points=5`. Given a `ScoringContext`, when `len(ctx.three_major) < 5` it SHALL return `status="skipped"`, `points=0`, `evidence={"reason": "insufficient_three_major_rows", "have": <int>, "need": 5}`. Otherwise it SHALL compute `net_5d = sum(row["foreign_net"] for row in ctx.three_major[-5:])` (lots) and award `points` per the band:

| `net_5d` (lots)             | points |
|-----------------------------|--------|
| `<= 0`                      | 0      |
| `1 .. 200`                  | 1      |
| `201 .. 500`                | 2      |
| `501 .. 1000`               | 3      |
| `>= 1001`                   | 5      |

`status` MUST be `"scored"` when `len(ctx.three_major) >= 5`. `evidence` MUST include `net_5d_lots` and `rows_used`.

#### Scenario: Heavy foreign buying scores 5
- **GIVEN** `ctx.three_major[-5:]` with `foreign_net` summing to 1500 lots
- **WHEN** `foreign_5d_net_buy(ctx)` is called
- **THEN** `points == 5`, `status == "scored"`, `evidence["net_5d_lots"] == 1500`

#### Scenario: Net selling scores 0
- **GIVEN** `ctx.three_major[-5:]` with `foreign_net` summing to -300 lots
- **WHEN** `foreign_5d_net_buy(ctx)` is called
- **THEN** `points == 0`, `status == "scored"`, `evidence["net_5d_lots"] == -300`

#### Scenario: Mid-tier band 201-500 scores 2
- **GIVEN** `ctx.three_major[-5:]` with `foreign_net` summing to 350 lots
- **WHEN** `foreign_5d_net_buy(ctx)` is called
- **THEN** `points == 2`

#### Scenario: Boundary at 200 lots scores 1
- **GIVEN** `ctx.three_major[-5:]` with `foreign_net` summing to exactly 200 lots
- **WHEN** `foreign_5d_net_buy(ctx)` is called
- **THEN** `points == 1`

#### Scenario: Insufficient rows yields skipped
- **GIVEN** `ctx.three_major` of length 3
- **WHEN** `foreign_5d_net_buy(ctx)` is called
- **THEN** `points == 0`, `status == "skipped"`, `evidence["have"] == 3`, `evidence["need"] == 5`

### Requirement: trust_5d_net_buy sub-scorer

The system SHALL register a sub-scorer named `trust_5d_net_buy` in category `chip` with `max_points=4`. Given a `ScoringContext`, when `len(ctx.three_major) < 5` it SHALL return `status="skipped"`, `points=0`. Otherwise it SHALL compute `net_5d = sum(row["invest_trust_net"] for row in ctx.three_major[-5:])` and award `points` per the band:

| `net_5d` (lots)             | points |
|-----------------------------|--------|
| `<= 0`                      | 0      |
| `1 .. 100`                  | 1      |
| `101 .. 300`                | 2      |
| `>= 301`                    | 4      |

`status` MUST be `"scored"` when `len(ctx.three_major) >= 5`. `evidence` MUST include `net_5d_lots`.

#### Scenario: Heavy trust buying scores 4
- **GIVEN** `ctx.three_major[-5:]` with `invest_trust_net` summing to 600 lots
- **WHEN** `trust_5d_net_buy(ctx)` is called
- **THEN** `points == 4`, `status == "scored"`

#### Scenario: Mid-tier 101-300 scores 2
- **GIVEN** `ctx.three_major[-5:]` with `invest_trust_net` summing to 250 lots
- **WHEN** `trust_5d_net_buy(ctx)` is called
- **THEN** `points == 2`

#### Scenario: Net selling scores 0
- **GIVEN** `ctx.three_major[-5:]` with `invest_trust_net` summing to -50 lots
- **WHEN** `trust_5d_net_buy(ctx)` is called
- **THEN** `points == 0`

#### Scenario: Insufficient rows yields skipped
- **GIVEN** `ctx.three_major` of length 0
- **WHEN** `trust_5d_net_buy(ctx)` is called
- **THEN** `points == 0`, `status == "skipped"`

### Requirement: End-to-end engine output with real sub-scorers

When `score_watchlist(asof_date, candidates)` runs with the real sub-scorers registered (and the placeholder removed), the returned envelope's `data.candidates[i].subscores` SHALL be a list of length 6 (one entry per registered real sub-scorer), in alphabetical order by `name` (matching `list_subscorers()` ordering). The `subscores` list SHALL NOT contain any entry with `name == "_always_zero_placeholder"`. The `final_score` for any candidate SHALL be at most `34` (the sum of all six max_points values: `10 + 5 + 5 + 5 + 5 + 4 = 34`).

#### Scenario: All six sub-scorers run with rich synthetic context
- **GIVEN** mocked `get_kline` returning ≥ 252 bars, `get_three_major_investors` returning ≥ 5 rows, `get_margin_short` returning ≥ 5 rows
- **WHEN** `score_watchlist("2026-04-30", ["2330"])` runs and the bars/rows are constructed to satisfy all 6 sub-scorers' "full points" conditions
- **THEN** `data.candidates[0].subscores` has length 6, `final_score == 34`, classification == `"red"` (since 34 < 50), and no entry has `name == "_always_zero_placeholder"`

#### Scenario: Insufficient data produces mixed statuses
- **GIVEN** mocked `get_kline` returning 30 bars and `get_three_major_investors` returning 5 rows summing foreign_net to 1500
- **WHEN** `score_watchlist("2026-04-30", ["2330"])` runs
- **THEN** `data.candidates[0].subscores` includes `trend_structure_ma` with `status="skipped"` and `foreign_5d_net_buy` with `status="scored", points=5`

## REMOVED Requirements

### Requirement: Always-zero placeholder sub-scorer is registered

**Reason**: Real sub-scorers ship in this change, replacing the placeholder. The placeholder existed solely as scaffolding to keep the engine end-to-end testable while the engine PR was in review. With six real sub-scorers registered, the placeholder is dead weight that pollutes every candidate's `subscores` list.

**Migration**: None required — the placeholder was an internal module (`src/ohmystock/scoring/_placeholder.py`) never exposed to callers and never referenced outside `ohmystock.scoring`. The file is deleted; its only consumer (`tests/test_scoring_placeholder.py`) is deleted alongside it. The previous end-to-end test (`tests/test_scoring_engine_e2e.py`) is replaced by `tests/test_scoring_engine_real_subscorers.py`, which exercises the full path with real sub-scorers instead of the placeholder.
