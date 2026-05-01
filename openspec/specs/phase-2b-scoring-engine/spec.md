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

### Requirement: Always-zero placeholder sub-scorer is registered

The package `ohmystock.scoring` SHALL register one sub-scorer named `_always_zero_placeholder` in category `technical` with `max_points=0` at import time, returning `SubScoreResult(status="scored", points=0, evidence={"placeholder": True})`. This sub-scorer exists solely to keep the engine end-to-end testable until real sub-scorers ship in `phase-2b-shipped-subscorers`.

#### Scenario: Placeholder is in registry after package import
- **WHEN** `import ohmystock.scoring` runs
- **THEN** `list_subscorers()` contains an entry with `name == "_always_zero_placeholder"`, `category == "technical"`, `max_points == 0`

#### Scenario: Placeholder appears in every candidate's subscores
- **WHEN** `score_watchlist("2026-04-30", ["2330"])` returns `ok=True`
- **THEN** `data.candidates[0].subscores` contains an entry with `name == "_always_zero_placeholder"`, `points == 0`, `status == "scored"`, `evidence["placeholder"] == True`

### Requirement: Reverse-import isolation

Importing `ohmystock.scoring` (or any of its public submodules: `models`, `context`, `registry`) SHALL NOT pull `fastapi`, `uvicorn`, or `starlette` into `sys.modules`.

#### Scenario: Subprocess import does not load FastAPI
- **WHEN** a fresh subprocess runs `python -c "import sys; import ohmystock.scoring; assert 'fastapi' not in sys.modules and 'uvicorn' not in sys.modules and 'starlette' not in sys.modules"`
- **THEN** the subprocess exits with code 0

