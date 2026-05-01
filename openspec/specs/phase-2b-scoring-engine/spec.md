# phase-2b-scoring-engine Specification

## Purpose
TBD - created by archiving change phase-2b-scoring-engine. Update Purpose after archive.
## Requirements
### Requirement: score_watchlist returns a standard envelope

The system SHALL expose a public function `score_watchlist(asof_date, candidates, *, risk_off_resolver, top_n, _conn, _today)` in `ohmystock.scoring` that returns a dict matching the standard envelope `{"ok": bool, "elapsed_ms": int, "data": <payload>|None, "error": {"code": str, "message": str, "retriable": bool}|None}`. No exception raised inside the function SHALL escape the boundary; unexpected exceptions MUST be caught and translated to an envelope with `error.code == "INTERNAL_ERROR"` and `error.retriable == True`.

#### Scenario: Successful scoring with placeholder sub-scorer
- **WHEN** `score_watchlist("2026-04-30", ["2330"])` is called and `get_kline` / `get_three_major_investors` / `get_margin_short` all return `ok=True` envelopes
- **THEN** the function returns `{"ok": True, "elapsed_ms": int, "data": {...}, "error": None}`
- **AND** `data["candidates"]` has exactly one entry with `symbol == "2330"` and a `subscores` list containing the `_always_zero_placeholder` entry with `status == "scored"`, `points == 0`, `max_points == 0`

#### Scenario: Unexpected exception is translated to INTERNAL_ERROR
- **WHEN** an internal helper raises an unexpected exception during scoring
- **THEN** the function returns `{"ok": False, "data": None, "error": {"code": "INTERNAL_ERROR", "message": <str>, "retriable": True}}`

### Requirement: Input validation produces INVALID_INPUT

The function SHALL validate inputs before any data fetch and return `error.code == "INVALID_INPUT"` with a descriptive message when validation fails. Validations MUST cover at minimum: `asof_date` matches `^\d{4}-\d{2}-\d{2}$` and is a parseable ISO date; `candidates` is a non-empty list of strings each matching `^\d{4,6}(KY)?$`; `top_n`, when not `None`, is an `int >= 1` (rejecting `bool`); `risk_off_resolver` is callable.

#### Scenario: asof_date wrong format
- **WHEN** `score_watchlist("2026/04/30", ["2330"])` is called
- **THEN** the result is `{"ok": False, "data": None, "error": {"code": "INVALID_INPUT", "message": <contains "asof_date">, "retriable": False}}`

#### Scenario: empty candidates list
- **WHEN** `score_watchlist("2026-04-30", [])` is called
- **THEN** the result is `{"ok": False, "data": None, "error": {"code": "INVALID_INPUT", "message": <contains "candidates">, "retriable": False}}`

#### Scenario: malformed candidate symbol
- **WHEN** `score_watchlist("2026-04-30", ["abc"])` is called
- **THEN** the result is `{"ok": False, "data": None, "error": {"code": "INVALID_INPUT", "message": <contains "symbol">, "retriable": False}}`

#### Scenario: top_n is bool
- **WHEN** `score_watchlist("2026-04-30", ["2330"], top_n=True)` is called
- **THEN** the result is `{"ok": False, "data": None, "error": {"code": "INVALID_INPUT", "message": <contains "top_n">, "retriable": False}}`

#### Scenario: risk_off_resolver not callable
- **WHEN** `score_watchlist("2026-04-30", ["2330"], risk_off_resolver=False)` is called
- **THEN** the result is `{"ok": False, "data": None, "error": {"code": "INVALID_INPUT", "message": <contains "risk_off_resolver">, "retriable": False}}`

### Requirement: Phase2BCandidate and SubScoreResult Pydantic contracts

The system SHALL provide two Pydantic v2 models in `ohmystock.scoring.models`. `SubScoreResult` MUST have fields `name: str`, `category: Literal["technical","chip","fundamental","sentiment"]`, `points: float`, `max_points: float`, `status: Literal["scored","skipped","error"]`, `evidence: dict[str, Any]` (default `{}`), `error_message: str | None` (default `None`). `Phase2BCandidate` MUST have fields `symbol: str`, `asof_date: str`, `final_score: float`, `tech_subtotal: float`, `chip_subtotal: float`, `fund_subtotal: float`, `sent_subtotal: float`, `classification: Literal["green","yellow","red"]`, `risk_off_applied: bool`, `subscores: list[SubScoreResult]`. Both models SHALL be importable as `from ohmystock.scoring import Phase2BCandidate, SubScoreResult`.

#### Scenario: SubScoreResult validates status enum
- **WHEN** `SubScoreResult(name="x", category="technical", points=0, max_points=5, status="bogus")` is constructed
- **THEN** Pydantic raises `ValidationError`

#### Scenario: SubScoreResult validates category enum
- **WHEN** `SubScoreResult(name="x", category="other", points=0, max_points=5, status="scored")` is constructed
- **THEN** Pydantic raises `ValidationError`

#### Scenario: Phase2BCandidate validates classification enum
- **WHEN** `Phase2BCandidate(..., classification="blue", ...)` is constructed
- **THEN** Pydantic raises `ValidationError`

#### Scenario: Models are re-exported from package root
- **WHEN** `from ohmystock.scoring import Phase2BCandidate, SubScoreResult` is executed
- **THEN** the import succeeds without `ImportError`

### Requirement: Sub-scorer registry contract

The system SHALL provide a `register_subscorer(category, name, max_points)` decorator and a `dispatch(name, ctx)` function in `ohmystock.scoring.registry`. `register_subscorer` MUST raise `ValueError` if `name` is already registered. `dispatch(name, ctx)` MUST call the registered function with the provided `ScoringContext`, then overwrite `result.name`, `result.category`, `result.max_points` from the registry metadata, and clamp `result.points` to `[0, max_points]`. `list_subscorers()` MUST return a list of `(name, category, max_points)` tuples sorted alphabetically by `name`. A test-only helper `_reset_registry()` SHALL be available for clearing registry state between tests.

#### Scenario: Decorator registers a sub-scorer
- **GIVEN** a freshly-reset registry
- **WHEN** `@register_subscorer("technical", "trend_template", 5)` decorates a function
- **THEN** `list_subscorers()` includes `("trend_template", "technical", 5)`

#### Scenario: Duplicate registration raises ValueError
- **GIVEN** `"trend_template"` is already registered
- **WHEN** another `@register_subscorer("technical", "trend_template", 5)` is applied
- **THEN** `ValueError` is raised with message containing `"already registered"`

#### Scenario: dispatch overwrites contract metadata
- **GIVEN** a sub-scorer registered as `("technical", "rs_pct", 7)` whose function returns `SubScoreResult(name="WRONG", category="chip", points=20, max_points=99, status="scored")`
- **WHEN** `dispatch("rs_pct", ctx)` is called
- **THEN** the returned `SubScoreResult` has `name == "rs_pct"`, `category == "technical"`, `max_points == 7`, and `points == 7` (clamped from 20)

#### Scenario: dispatch clamps negative points to zero
- **GIVEN** a sub-scorer registered as `("chip", "borrow", 2)` whose function returns `points=-5, status="scored"`
- **WHEN** `dispatch("borrow", ctx)` is called
- **THEN** the returned `SubScoreResult` has `points == 0`

#### Scenario: list_subscorers returns alphabetically sorted metadata
- **GIVEN** registrations in order `b_subscorer`, `a_subscorer`, `c_subscorer`
- **WHEN** `list_subscorers()` is called
- **THEN** the result is in alphabetical order by `name`: `[("a_subscorer",...), ("b_subscorer",...), ("c_subscorer",...)]`

### Requirement: Engine fetches per-candidate context once before dispatching

The engine SHALL build one `ScoringContext` per candidate by calling `get_kline(symbol, period="1d", bars=250, end_date=asof_date)`, `get_three_major_investors(symbol, days=30, end_date=asof_date)`, `get_margin_short(symbol, days=30, end_date=asof_date)`. When all three return `ok=True`, the engine SHALL pass the `ScoringContext` to every registered sub-scorer via `dispatch`. When one or more return `ok=False`, the engine SHALL still build a `ScoringContext` (with empty lists for the failed sources) and dispatch sub-scorers; sub-scorers that raise during dispatch produce a `SubScoreResult` with `status="error"` and `points=0`.

#### Scenario: All data sources succeed
- **GIVEN** mocked `get_kline`/`get_three_major_investors`/`get_margin_short` all returning `ok=True` envelopes with deterministic rows
- **WHEN** `score_watchlist("2026-04-30", ["2330"])` is called
- **THEN** each registered sub-scorer is invoked exactly once for `2330` with the merged `ScoringContext`

#### Scenario: Sub-scorer raises during dispatch
- **GIVEN** a sub-scorer whose function raises `RuntimeError("boom")`
- **WHEN** the engine dispatches it
- **THEN** the resulting `SubScoreResult` has `status == "error"`, `points == 0`, `error_message` containing `"boom"`, and is included in the candidate's `subscores` list

### Requirement: Final score aggregation with category caps and zero floor

The engine SHALL compute four category sub-totals as `subtotal = max(0, min(category_cap, sum_of_scored_points_in_category))` with caps `technical=40`, `chip=25`, `fundamental=25`, `sentiment=10`. Only `SubScoreResult` entries with `status == "scored"` SHALL be summed. The `final_score` SHALL be `min(100, tech_subtotal + chip_subtotal + fund_subtotal + sent_subtotal)`.

#### Scenario: Sum within caps
- **GIVEN** registered sub-scorers producing `scored` results with point totals `tech=30, chip=20, fund=15, sent=5`
- **WHEN** the engine aggregates
- **THEN** `final_score == 70` and the four sub-totals match the inputs

#### Scenario: Category cap clamps overflow
- **GIVEN** registered sub-scorers producing `scored` results with point totals `tech=50, chip=20, fund=15, sent=5`
- **WHEN** the engine aggregates
- **THEN** `tech_subtotal == 40` and `final_score == 80`

#### Scenario: Negative category sum floored to zero
- **GIVEN** chip sub-scorers producing `scored` points summing to `-3`
- **WHEN** the engine aggregates
- **THEN** `chip_subtotal == 0`

#### Scenario: Skipped and error results are not summed
- **GIVEN** sub-scorers producing `(scored, points=10)`, `(skipped, points=0)`, `(error, points=0)` all in `technical`
- **WHEN** the engine aggregates
- **THEN** `tech_subtotal == 10` and the `subscores` list contains all three results in the candidate's output

### Requirement: Risk-Off ceiling and classification

The engine SHALL invoke `risk_off_resolver()` exactly once per `score_watchlist` call before classification. When the resolver returns `True`, every candidate's `final_score` SHALL be replaced with `min(final_score, 50)` and `risk_off_applied` SHALL be `True`. Classification SHALL be: `"green"` when `final_score >= 65`; `"yellow"` when `50 <= final_score < 65`; `"red"` when `final_score < 50`.

#### Scenario: Risk-Off off, score 70 classifies green
- **GIVEN** `risk_off_resolver()` returns `False` and a candidate's pre-cap `final_score` is `70`
- **THEN** the candidate's `final_score == 70`, `risk_off_applied == False`, `classification == "green"`

#### Scenario: Risk-Off on, score 70 capped to 50, classifies yellow
- **GIVEN** `risk_off_resolver()` returns `True` and a candidate's pre-cap `final_score` is `70`
- **THEN** the candidate's `final_score == 50`, `risk_off_applied == True`, `classification == "yellow"`

#### Scenario: Risk-Off on, score 30 unchanged, classifies red
- **GIVEN** `risk_off_resolver()` returns `True` and a candidate's pre-cap `final_score` is `30`
- **THEN** the candidate's `final_score == 30`, `risk_off_applied == True`, `classification == "red"`

#### Scenario: Resolver called once per batch, not per candidate
- **GIVEN** a `risk_off_resolver` mock and 5 candidates
- **WHEN** `score_watchlist` is called once
- **THEN** the resolver is invoked exactly once

### Requirement: Deterministic sort and top_n truncation

The engine SHALL sort `data.candidates` by `final_score` descending then `symbol` ascending (lexicographic). When `top_n` is provided and not `None`, the engine SHALL truncate the sorted list to the first `top_n` entries. Same inputs SHALL produce the same output across runs.

#### Scenario: Tie-break by symbol
- **GIVEN** candidates `["2330", "2317"]` both scoring `final_score == 60`
- **THEN** the sorted output places `"2317"` before `"2330"`

#### Scenario: top_n truncates after sort
- **GIVEN** five candidates with distinct `final_score` values and `top_n=2`
- **THEN** `data.candidates` has exactly the two highest-scoring candidates

#### Scenario: top_n=None returns all
- **GIVEN** five candidates and `top_n=None`
- **THEN** `data.candidates` contains all five entries

### Requirement: Sub-scorer file layout under `subscorers/` package

The package `ohmystock.scoring` SHALL contain a sub-package `ohmystock.scoring.subscorers` with one Python module per registered sub-scorer. Each module SHALL define exactly one function decorated with `@register_subscorer(...)`. The package's `__init__.py` SHALL explicitly import each sub-scorer module so that registration happens at package import time. Deferred-stub sub-scorers SHALL live in a nested sub-package `ohmystock.scoring.subscorers.deferred` with the same one-file-per-sub-scorer rule, and `subscorers/__init__.py` SHALL import the `deferred` sub-package (`from . import deferred  # noqa: F401`). The top-level `ohmystock/scoring/__init__.py` SHALL import `ohmystock.scoring.subscorers` (replacing the prior `_placeholder` import). Sub-scorer modules — including those under `deferred/` — MUST NOT import `fastapi`, `uvicorn`, `starlette`, or any I/O-performing module beyond `ohmystock.indicators`, `ohmystock.scoring.context`, `ohmystock.scoring.models`, and `ohmystock.scoring.registry`. The deferred sub-package SHALL contain exactly **14** stub modules (down from 16; `rs_percentile` and `kline_patterns` were promoted to real sub-scorers under `subscorers/` — the latter renamed to `vcp_pivot.py`).

#### Scenario: Subscorers package is importable
- **WHEN** `import ohmystock.scoring.subscorers` runs
- **THEN** the import succeeds without `ImportError` and `list_subscorers()` includes every sub-scorer registered in this change

#### Scenario: Sub-scorer modules are pure
- **WHEN** any module under `ohmystock/scoring/subscorers/*.py` or `ohmystock/scoring/subscorers/deferred/*.py` is imported
- **THEN** it does not pull `fastapi`, `uvicorn`, or `starlette` into `sys.modules`

#### Scenario: Deferred sub-package is importable and auto-loaded
- **WHEN** `import ohmystock.scoring` runs from a fresh interpreter
- **THEN** `ohmystock.scoring.subscorers.deferred` is in `sys.modules` and `list_subscorers()` includes the names of all **14** deferred stubs registered after this change

#### Scenario: One file per deferred stub
- **WHEN** the directory `src/ohmystock/scoring/subscorers/deferred/` is enumerated
- **THEN** every `.py` file other than `__init__.py` corresponds 1-to-1 with a sub-scorer name registered from the `deferred` sub-package (file `<name>.py` ↔ registered name `<name>`)

#### Scenario: rs_percentile and vcp_pivot live outside deferred/
- **WHEN** the directories `src/ohmystock/scoring/subscorers/` and `src/ohmystock/scoring/subscorers/deferred/` are enumerated
- **THEN** `rs_percentile.py` and `vcp_pivot.py` exist directly under `subscorers/` (NOT under `deferred/`)
- **AND** neither `subscorers/deferred/rs_percentile.py` nor `subscorers/deferred/kline_patterns.py` exists

---

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

### Requirement: Reverse-import isolation

Importing `ohmystock.scoring` (or any of its public submodules: `models`, `context`, `registry`) SHALL NOT pull `fastapi`, `uvicorn`, or `starlette` into `sys.modules`.

#### Scenario: Subprocess import does not load FastAPI
- **WHEN** a fresh subprocess runs `python -c "import sys; import ohmystock.scoring; assert 'fastapi' not in sys.modules and 'uvicorn' not in sys.modules and 'starlette' not in sys.modules"`
- **THEN** the subprocess exits with code 0

### Requirement: Deferred-stub sub-scorers register with `status="skipped"`

The system SHALL register 16 deferred-stub sub-scorers under `ohmystock.scoring.subscorers.deferred`, each as a pure `(ScoringContext) -> SubScoreResult` function decorated with `@register_subscorer(category, name, max_points)`. Every deferred stub SHALL return a `SubScoreResult` with `status="skipped"`, `points=0`, `evidence={"reason": <non-empty str>}`, and `error_message=None`. The 16 stubs and their `(category, name, max_points)` registrations SHALL be exactly:

- **technical:** `kline_patterns` (8), `rs_percentile` (7).
- **chip:** `broker_concentration` (7), `futures_oi` (3), `margin_tightening` (2), `tdcc_concentration` (2), `borrow_change` (2).
- **fundamental:** `eps_yoy` (8), `eps_qoq` (5), `monthly_revenue_yoy` (6), `quarterly_revenue_yoy` (3), `institutional_30d_holding` (3).
- **sentiment:** `analyst_target_upgrades` (3), `sue` (3), `important_announcements` (2), `search_heat` (2).

Stubs MUST NOT raise, MUST NOT perform I/O, and MUST NOT inspect `ScoringContext` fields beyond what is necessary to construct the return value (which is none). The `evidence["reason"]` value SHALL be `"data source not implemented"` for stubs whose data source is simply absent, and SHALL include the substring `"negative-band scoring requires registry contract change"` for `borrow_change` and `search_heat` (whose documented bands extend below zero — `borrow_change`: `-3..+2`; `search_heat`: `-2..+2` — and whose registered `max_points=2` only covers the positive-band ceiling).

#### Scenario: All 16 deferred stubs are registered
- **WHEN** `import ohmystock.scoring` runs from a fresh interpreter and `list_subscorers()` is called
- **THEN** the result contains exactly these 16 deferred names with the listed `(name, category, max_points)` tuples: `("kline_patterns", "technical", 8)`, `("rs_percentile", "technical", 7)`, `("broker_concentration", "chip", 7)`, `("futures_oi", "chip", 3)`, `("margin_tightening", "chip", 2)`, `("tdcc_concentration", "chip", 2)`, `("borrow_change", "chip", 2)`, `("eps_yoy", "fundamental", 8)`, `("eps_qoq", "fundamental", 5)`, `("monthly_revenue_yoy", "fundamental", 6)`, `("quarterly_revenue_yoy", "fundamental", 3)`, `("institutional_30d_holding", "fundamental", 3)`, `("analyst_target_upgrades", "sentiment", 3)`, `("sue", "sentiment", 3)`, `("important_announcements", "sentiment", 2)`, `("search_heat", "sentiment", 2)`

#### Scenario: dispatch on any deferred stub returns skipped + zero points
- **GIVEN** a fresh registry with the deferred sub-package imported and any constructed `ScoringContext`
- **WHEN** `dispatch(<deferred_name>, ctx)` is called for any of the 16 deferred names
- **THEN** the returned `SubScoreResult` has `status == "skipped"`, `points == 0`, `max_points` equal to the registered cap, `evidence["reason"]` is a non-empty string, and `error_message is None`

#### Scenario: Negative-band stubs annotate the registry-contract gap
- **WHEN** `dispatch("borrow_change", ctx)` or `dispatch("search_heat", ctx)` is called
- **THEN** the returned `SubScoreResult.evidence["reason"]` contains the substring `"negative-band scoring requires registry contract change"`

#### Scenario: Deferred stubs do not raise
- **WHEN** any deferred stub is dispatched with a `ScoringContext` whose `bars`, `three_major`, and `margin_short` are all empty lists
- **THEN** dispatch completes without raising and the result has `status == "skipped"` (NOT `"error"`)

#### Scenario: Engine envelope includes deferred stubs in subscores
- **WHEN** `score_watchlist("2026-04-30", ["2330"])` is called and all data fetchers return `ok=True`
- **THEN** the returned envelope's `data["candidates"][0]["subscores"]` contains exactly 22 entries (6 real + 16 deferred); the 16 deferred entries have `status == "skipped"` and contribute 0 to all category subtotals

#### Scenario: Deferred stubs respect category-cap aggregation
- **WHEN** the engine aggregates final score and the 16 deferred stubs are present alongside the 6 real sub-scorers
- **THEN** the four category subtotals are computed only from `status == "scored"` entries; the deferred stubs (all `status == "skipped"`) MUST NOT contribute even their 0 points to any subtotal sum, and `final_score` equals the sum of real sub-scorer points (capped per category)

### Requirement: Phase 2B candidates are consumable by the swarm input assembler

The system SHALL expose Phase 2B candidate rows (those with `final_score >= 65`) via a stable Python iterator/repository surface that the swarm input assembler can consume without parsing CLI output. Specifically, `ohmystock.scoring` SHALL provide a public function `iter_qualified_candidates(asof_date: str, *, threshold: float = 65.0) -> Iterable[Phase2BCandidate]` that yields `Phase2BCandidate` instances whose `final_score >= threshold`, ordered by `final_score` descending then `symbol` ascending. The function MUST return an empty iterable (not raise) when no candidates qualify.

#### Scenario: Returns qualified candidates ordered by score then symbol
- **WHEN** the scoring run for `2026-04-30` has produced candidates `[("2330", 78), ("2454", 72), ("3008", 72), ("1234", 60)]`
- **THEN** `list(iter_qualified_candidates("2026-04-30"))` returns three `Phase2BCandidate` instances in the order `[2330, 2454, 3008]`
- **AND** the candidate with `final_score == 60` is excluded

#### Scenario: Empty iterable when no qualifying candidates
- **WHEN** every candidate for `2026-04-30` has `final_score < 65`
- **THEN** `list(iter_qualified_candidates("2026-04-30"))` returns `[]`
- **AND** no exception is raised

### Requirement: Phase2BCandidate carries SEPA fields required by v3.1 input schema

`Phase2BCandidate` SHALL include SEPA fields `stage: int`, `rs_percentile: int`, `trend_template_passed: int`, `vcp_quality: Literal["none","forming","textbook","breakout"]`, and `pivot_price: float | None`, populated by the SEPA-aligned sub-scorers, so that the swarm input assembler can mirror them into `CandidateSnapshot` without further computation. These fields MUST be present (non-`None` for `stage`/`rs_percentile`/`trend_template_passed`/`vcp_quality`) on every candidate yielded by `iter_qualified_candidates`. `pivot_price` MAY be `None` only when `vcp_quality in {"none", "forming"}`.

#### Scenario: Qualified candidate has SEPA fields populated
- **WHEN** `iter_qualified_candidates("2026-04-30")` yields a candidate
- **THEN** the candidate's `stage`, `rs_percentile`, `trend_template_passed`, `vcp_quality` are all non-`None`
- **AND** if `vcp_quality in {"textbook", "breakout"}` then `pivot_price > 0`
- **AND** if `vcp_quality in {"none", "forming"}` then `pivot_price is None`

### Requirement: rs_percentile sub-scorer (real implementation)

The system SHALL register a sub-scorer named `rs_percentile` in category `technical` with `max_points=7` under `src/ohmystock/scoring/subscorers/rs_percentile.py` (NOT under the `deferred/` sub-package). Given a `ScoringContext`, when `len(ctx.bars) < 252` the sub-scorer SHALL return `SubScoreResult(status="skipped", points=0, evidence={"reason": "insufficient_bars", "have": <int>, "need": 252})`. Otherwise it SHALL compute the candidate's IBD-style weighted return as `0.4 * pct_change(closes, 63) + 0.2 * pct_change(closes, 126) + 0.2 * pct_change(closes, 189) + 0.2 * pct_change(closes, 252)`, then compute `rs_percentile = round(percentile_rank(candidate_return, [universe_return ...]) * 99)` where the universe is supplied by a swappable loader (`set_rs_universe_loader`), defaulting to a 5-symbol TWSE seed list. `evidence` MUST include `rs_percentile: int` (in `[0, 99]`), `weighted_return: float`, and `universe_size: int`. Scoring SHALL be `points=7` if `rs_percentile >= 90`, `points=5` if `rs_percentile >= 80`, `points=3` if `rs_percentile >= 65`, else `points=0`. `status` MUST be `"scored"` when `len(ctx.bars) >= 252`.

#### Scenario: Insufficient bars yields skipped
- **GIVEN** `ctx.bars` of length 100
- **WHEN** the `rs_percentile` sub-scorer runs
- **THEN** the result has `status == "skipped"`, `points == 0`, `evidence["reason"] == "insufficient_bars"`, `evidence["have"] == 100`, `evidence["need"] == 252`

#### Scenario: Top-decile candidate scores 7 points
- **GIVEN** a candidate whose 63/126/189/252-day weighted return exceeds every symbol in the universe
- **WHEN** `rs_percentile` runs
- **THEN** `evidence["rs_percentile"] >= 90` and `points == 7`

#### Scenario: Threshold tiers map to point bands
- **GIVEN** an artificially-constructed universe placing the candidate at exactly the 65th, 80th, and 90th percentile across three runs
- **WHEN** `rs_percentile` runs in each
- **THEN** `points` is `3`, `5`, `7` respectively

#### Scenario: rs_percentile is in valid range
- **WHEN** `rs_percentile` runs against any universe
- **THEN** `evidence["rs_percentile"]` is an `int` in `[0, 99]`

#### Scenario: Custom universe loader is honoured
- **GIVEN** `set_rs_universe_loader(lambda: [("FAKE", [10.0, 11.0, ...])])` is called
- **WHEN** `rs_percentile` runs
- **THEN** `evidence["universe_size"] == 1`

### Requirement: vcp_pivot sub-scorer (real implementation)

The system SHALL register a sub-scorer named `vcp_pivot` in category `technical` with `max_points=8` under `src/ohmystock/scoring/subscorers/vcp_pivot.py` (NOT under `deferred/`). Given a `ScoringContext`, when `len(ctx.bars) < 60` the sub-scorer SHALL return `status="skipped"`, `points=0`, `evidence={"reason": "insufficient_bars", "have": <int>, "need": 60}`. Otherwise it SHALL classify the chart pattern from the last 60 bars and emit:
- `evidence["vcp_quality"] ∈ {"none", "forming", "textbook", "breakout"}`,
- `evidence["pivot_price"]: float | None` — `None` when `vcp_quality ∈ {"none", "forming"}`, a positive float otherwise.

Classification rules SHALL be:
- **breakout** when today's close > prior-19-bar high AND today's volume ≥ 1.4 × the 20-DMA volume → `pivot_price = max(prior 19 highs)`, `points=8`.
- **textbook** when the 20-bar base `range_pct = (max(highs[-20:]) - min(lows[-20:])) / min(lows[-20:])` < 0.10 AND ≥ 2 lower-high contractions are visible across the last 60 bars → `pivot_price = max(highs[-20:])`, `points=6`.
- **forming** when 20-bar `range_pct` < 0.15 AND not breakout → `pivot_price = None`, `points=3`.
- **none** otherwise → `pivot_price = None`, `points=0`.

`evidence` MUST also include `range_pct: float`, `volume_ratio: float | None`, and `contractions: int`.

#### Scenario: Insufficient bars yields skipped
- **GIVEN** `ctx.bars` of length 30
- **WHEN** the `vcp_pivot` sub-scorer runs
- **THEN** the result has `status == "skipped"`, `points == 0`, `evidence["reason"] == "insufficient_bars"`, `evidence["have"] == 30`, `evidence["need"] == 60`

#### Scenario: Breakout day awards 8 points
- **GIVEN** a `ScoringContext` whose last bar's close exceeds every prior-19-bar high and volume is `≥ 1.4 ×` the 20-bar moving average
- **WHEN** `vcp_pivot` runs
- **THEN** `evidence["vcp_quality"] == "breakout"`, `evidence["pivot_price"]` is a positive float equal to `max(highs[-20:-1])`, `points == 8`

#### Scenario: Tight base with 2 contractions is textbook
- **GIVEN** a 60-bar series with `range_pct < 0.10` over the last 20 bars and exactly 2 lower-high contractions in the prior 40 bars
- **WHEN** `vcp_pivot` runs
- **THEN** `evidence["vcp_quality"] == "textbook"`, `evidence["pivot_price"]` equals `max(highs[-20:])`, `points == 6`

#### Scenario: Loose base is forming
- **GIVEN** a 60-bar series with `range_pct` between 0.10 and 0.15 over the last 20 bars and no breakout
- **WHEN** `vcp_pivot` runs
- **THEN** `evidence["vcp_quality"] == "forming"`, `evidence["pivot_price"] is None`, `points == 3`

#### Scenario: Wide-range chop is none
- **GIVEN** a 60-bar series with `range_pct >= 0.15`
- **WHEN** `vcp_pivot` runs
- **THEN** `evidence["vcp_quality"] == "none"`, `evidence["pivot_price"] is None`, `points == 0`

### Requirement: SEPA fields populated end-to-end through score_watchlist

When `score_watchlist` runs against bars sufficient for both `rs_percentile` (≥ 252 bars) and `vcp_pivot` (≥ 60 bars) AND `stage_2_confirmed` AND `trend_template_8` all to score successfully, every resulting `Phase2BCandidate` SHALL have all five SEPA fields populated (non-`None` for `stage`, `rs_percentile`, `trend_template_passed`, `vcp_quality`; `pivot_price` non-`None` iff `vcp_quality ∈ {"textbook", "breakout"}`). This makes `build_entry_decision_input` succeed without raising `AssemblerInputError("missing SEPA field(s)")`.

#### Scenario: Sufficient bars produce non-None SEPA fields
- **GIVEN** `score_watchlist("2026-04-30", ["2330"])` called with stub kline / chip / margin envelopes that supply 252+ bars and a clean uptrend
- **WHEN** the call returns `ok=True`
- **THEN** the resulting candidate has `stage`, `rs_percentile`, `trend_template_passed`, `vcp_quality` all non-`None`
- **AND** the candidate dict can be passed through `build_entry_decision_input` without raising `AssemblerInputError`

