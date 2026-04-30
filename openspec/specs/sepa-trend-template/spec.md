# sepa-trend-template Specification

## Purpose
TBD - created by archiving change sepa-trend-template-and-stage. Update Purpose after archive.

## Requirements

### Requirement: Trend Template evaluator returns 8-condition trace

The `evaluate_trend_template(bars, rs_percentile)` function SHALL return a `TrendTemplateResult` containing one `ConditionOutcome` per Minervini condition (c1–c8), keyed by stable identifiers `c1` through `c8`, plus an overall `passed: bool` flag that is `True` if and only if every condition's `passed` is `True`.

The 8 conditions (per `docs/workflow-cheatsheet.md` v3.1 §2 第二層):

- **c1**: close > MA50
- **c2**: MA50 > MA150
- **c3**: MA150 > MA200
- **c4**: close > MA150
- **c5**: close > MA200
- **c6**: MA200 has risen monotonically (non-decreasing) over the last 20 trading sessions
- **c7**: close ≥ 52-week high × 0.75 (within 25% of 52-week high)
- **c8**: close ≥ 52-week low × 1.30 (≥ 30% above 52-week low) AND `rs_percentile ≥ 65`

#### Scenario: All eight conditions pass on a synthetic Stage-2 ramp

- **GIVEN** 252 daily bars where close rises from 100 to 200 monotonically and `rs_percentile = 80`
- **WHEN** `evaluate_trend_template(bars, rs_percentile=80)` is called
- **THEN** the result has `passed = True`
- **AND** every entry in `result.conditions` has `passed = True`
- **AND** the keys are exactly `{"c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"}`

#### Scenario: Condition c6 fails when MA200 dips mid-window

- **GIVEN** 252 bars where MA200 rises 19 sessions then dips 1 session before today
- **WHEN** the function is called
- **THEN** `result.conditions["c6"].passed` is `False`
- **AND** `result.conditions["c6"].detail` mentions which session broke monotonicity
- **AND** `result.passed` is `False`

#### Scenario: Condition c7 fails when close > 25% below 52-week high

- **GIVEN** 252 bars where 52-week high = 200 and last close = 140
- **WHEN** the function is called with all other conditions passing
- **THEN** `result.conditions["c7"].passed` is `False`
- **AND** `result.passed` is `False`

### Requirement: Missing RS Percentile yields tri-state c8 outcome

When `rs_percentile` is `None`, condition c8 SHALL record `passed = None` (not `False`) and the function SHALL still return a fully-formed result with `passed = False` overall.

#### Scenario: rs_percentile is None

- **GIVEN** 252 bars satisfying c1–c7
- **WHEN** `evaluate_trend_template(bars, rs_percentile=None)` is called
- **THEN** `result.conditions["c8"].passed` is `None`
- **AND** `result.conditions["c8"].detail` mentions "rs_percentile not provided"
- **AND** `result.passed` is `False`
- **AND** every other condition c1–c7 has its `passed` set to `True` or `False` (never `None`)

### Requirement: Insufficient history raises typed error

The function SHALL raise `InsufficientHistoryError` (a `ValueError` subclass) when `len(bars) < 252`, with a message naming the actual length.

#### Scenario: 251 bars provided

- **GIVEN** a list of 251 valid `BarRow` entries
- **WHEN** the function is called
- **THEN** `InsufficientHistoryError` is raised
- **AND** the message contains "251" and "252"

#### Scenario: Empty bars

- **GIVEN** an empty list `[]`
- **WHEN** the function is called
- **THEN** `InsufficientHistoryError` is raised

### Requirement: 52-week window uses exactly the last 252 bars

The 52-week high/low used by c7 and c8 SHALL be `max(b["h"] for b in bars[-252:])` and `min(b["l"] for b in bars[-252:])` respectively, regardless of the trading-day calendar.

#### Scenario: Bars contain a clear all-time high outside the 52-week window

- **GIVEN** 300 bars where the all-time high (`h=500`) occurs at index 10 (~289 days ago) and the highest high in `bars[-252:]` is 200
- **WHEN** the function is called
- **THEN** condition c7 evaluates against `52w_high = 200`, not 500

### Requirement: Output is immutable

`TrendTemplateResult` and `ConditionOutcome` SHALL be `frozen=True` dataclasses; mutation attempts raise `FrozenInstanceError`.

#### Scenario: Caller attempts to mutate

- **GIVEN** a returned `TrendTemplateResult`
- **WHEN** the caller assigns `result.passed = True`
- **THEN** `dataclasses.FrozenInstanceError` is raised
