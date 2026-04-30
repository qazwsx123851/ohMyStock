## ADDED Requirements

### Requirement: classify_stage returns one of {1, 2, 3, 4} with reason

The `classify_stage(bars)` function SHALL return a `StageResult` whose `stage` is exactly one of `1`, `2`, `3`, `4` and whose `reason` is a non-empty short string explaining which clause matched.

Stage definitions (per `docs/workflow-cheatsheet.md` v3.1 §0.4 and §2 第三層):

- **Stage 4** — `MA50 < MA150 < MA200` AND `close < MA50` AND MA200 has not risen over the last 20 trading sessions.
- **Stage 2** — `close > MA50 > MA150 > MA200` AND MA200 monotonically non-decreasing for the last 20 trading sessions, AND the 30-day high-vs-low range ≤ 20% of the last close.
- **Stage 3** — same mean-stack as Stage 2 (`close > MA50 > MA150 > MA200` AND MA200 rising) BUT the 30-day high-vs-low range > 20% of the last close.
- **Stage 1** — anything else.

Evaluation order: Stage 4 first; if not Stage 4, then Stage 2/3; otherwise Stage 1.

#### Scenario: Synthetic Stage-2 monotonic ramp

- **GIVEN** 252 daily bars where close rises 100 → 200 with low daily range (≤ 1% per bar)
- **WHEN** `classify_stage(bars)` is called
- **THEN** `result.stage == 2`
- **AND** `result.reason` contains "Stage 2"

#### Scenario: Synthetic Stage-4 decline

- **GIVEN** 252 bars where close falls 200 → 100 such that `MA50 < MA150 < MA200` at the last bar AND MA200 declining over the last 20 sessions
- **WHEN** `classify_stage(bars)` is called
- **THEN** `result.stage == 4`
- **AND** `result.reason` mentions all three Stage-4 clauses (mean order, close vs MA50, MA200 not rising)

#### Scenario: Stage-2 mean-stack but volatile range qualifies as Stage 3

- **GIVEN** 252 bars where mean-stack is `close > MA50 > MA150 > MA200` and MA200 rising, but the last 30 bars span a high-low range = 25% of the last close
- **WHEN** `classify_stage(bars)` is called
- **THEN** `result.stage == 3`

#### Scenario: Flat sideways closes Stage 1

- **GIVEN** 252 bars where close hovers at 100 ± 2 with no clear trend
- **WHEN** `classify_stage(bars)` is called
- **THEN** `result.stage == 1`

### Requirement: is_stage_4_reject is true exactly when stage is 4

The `is_stage_4_reject(bars)` convenience wrapper SHALL return `True` if and only if `classify_stage(bars).stage == 4`. It MUST NOT return `True` for Stage 1, 2, or 3.

#### Scenario: Stage 4 returns True

- **GIVEN** Stage-4 fixture bars
- **WHEN** `is_stage_4_reject(bars)` is called
- **THEN** the return is `True`

#### Scenario: Stage 1 returns False

- **GIVEN** flat-range Stage-1 fixture bars
- **WHEN** `is_stage_4_reject(bars)` is called
- **THEN** the return is `False`

#### Scenario: Stage 2 returns False

- **GIVEN** Stage-2 fixture bars
- **WHEN** `is_stage_4_reject(bars)` is called
- **THEN** the return is `False`

### Requirement: Stage 4 evaluation requires all three clauses

A bar with `MA50 < MA150 < MA200` and `close < MA50` but with MA200 *rising* over the last 20 sessions SHALL NOT be classified as Stage 4 (it is a deep pullback in an uptrend, not Weinstein Stage 4).

#### Scenario: Mean-stack inverted but MA200 rising

- **GIVEN** 252 bars where MA50 < MA150 < MA200 and close < MA50 at the last bar, BUT MA200 increased monotonically over the last 20 sessions
- **WHEN** `classify_stage(bars)` is called
- **THEN** `result.stage != 4`
- **AND** `is_stage_4_reject(bars)` returns `False`

### Requirement: Insufficient history raises typed error

`classify_stage(bars)` and `is_stage_4_reject(bars)` SHALL raise `InsufficientHistoryError` (a `ValueError` subclass) when `len(bars) < 252`.

#### Scenario: 251 bars provided

- **GIVEN** a list of 251 valid `BarRow` entries
- **WHEN** either function is called
- **THEN** `InsufficientHistoryError` is raised

### Requirement: StageResult is immutable

`StageResult` SHALL be a `frozen=True` dataclass; mutation attempts raise `FrozenInstanceError`.

#### Scenario: Caller attempts to mutate stage

- **GIVEN** a returned `StageResult`
- **WHEN** the caller assigns `result.stage = 1`
- **THEN** `dataclasses.FrozenInstanceError` is raised
