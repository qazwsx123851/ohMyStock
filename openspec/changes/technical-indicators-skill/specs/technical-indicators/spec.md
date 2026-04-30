## ADDED Requirements

### Requirement: Pure-function indicator API in `ohmystock.indicators`

The system SHALL expose six pure functions in `ohmystock.indicators` (re-exported from `ohmystock.indicators.core`): `sma`, `ema`, `rsi`, `macd`, `atr`, `bollinger_bands`. Each function MUST be stateless (same input → same output, no side effects, no mutation of inputs) and MUST NOT raise on empty inputs (returns `[]` instead).

#### Scenario: All six indicators importable from package root

- **WHEN** `from ohmystock.indicators import sma, ema, rsi, macd, atr, bollinger_bands` is executed
- **THEN** all six names SHALL resolve to callables, and `from ohmystock.indicators.core import sma` SHALL import the same object

#### Scenario: Empty input returns empty output

- **WHEN** any of the six indicators is called with an empty list (`sma([], 5)`, `atr([], 14)`, etc.)
- **THEN** the call SHALL return an empty list (or tuple of empty lists for multi-output indicators) and SHALL NOT raise

---

### Requirement: Output length matches input length with `None` warmup

Every indicator SHALL return outputs of exactly the same length as its input series. Positions where the indicator is mathematically undefined (warmup window) SHALL be `None`, NOT `float('nan')`. For multi-output indicators (`macd`, `bollinger_bands`), each component output SHALL independently obey this length rule.

#### Scenario: SMA(period=3) over 5 closes returns 5 values with first 2 None

- **WHEN** `sma([10.0, 11.0, 12.0, 13.0, 14.0], 3)` is called
- **THEN** the result SHALL be `[None, None, 11.0, 12.0, 13.0]` (length 5, first `period - 1` positions are `None`, remaining are simple averages)

#### Scenario: Warmup positions are None not NaN

- **WHEN** any indicator's warmup positions are inspected via `value is None`
- **THEN** the check SHALL return `True`; `math.isnan(value)` SHALL NOT be applicable (`value` is `None`, not a float)

---

### Requirement: SMA — simple moving average

`sma(closes: list[float], period: int) -> list[float | None]` SHALL compute the arithmetic mean of the trailing `period` closes at each position. `period` MUST be a positive integer; `period = 0` or negative SHALL raise `ValueError`.

#### Scenario: SMA(period=1) is identity

- **WHEN** `sma([1.5, 2.5, 3.5], 1)` is called
- **THEN** the result SHALL equal `[1.5, 2.5, 3.5]`

#### Scenario: SMA(period=4) on linear ramp

- **WHEN** `sma([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], 4)` is called
- **THEN** the result SHALL equal `[None, None, None, 2.5, 3.5, 4.5]`

---

### Requirement: EMA — exponential moving average

`ema(closes: list[float], period: int) -> list[float | None]` SHALL compute the EMA with smoothing factor `α = 2 / (period + 1)`. The first defined value (at index `period - 1`) SHALL be the SMA of the first `period` closes (standard seeding convention); subsequent values SHALL use `ema_t = α * close_t + (1 - α) * ema_{t-1}`.

#### Scenario: EMA(period=3) seeded by SMA then recursive

- **WHEN** `ema([2.0, 4.0, 6.0, 8.0, 10.0], 3)` is called (α = 0.5)
- **THEN** position 2 SHALL equal `4.0` (SMA of first 3); position 3 SHALL equal `0.5 * 8.0 + 0.5 * 4.0 = 6.0`; position 4 SHALL equal `0.5 * 10.0 + 0.5 * 6.0 = 8.0`; positions 0, 1 SHALL be `None`

---

### Requirement: RSI — Wilder's relative strength index

`rsi(closes: list[float], period: int = 14) -> list[float | None]` SHALL compute Wilder's RSI: gains and losses averaged via Wilder smoothing (`avg_t = ((period - 1) * avg_{t-1} + current_t) / period`), with the first defined position at index `period`. When the average loss is zero, RSI SHALL be `100.0`. When the input is constant for the whole window, RSI SHALL be `50.0` (by convention, since both avg-gain and avg-loss are zero).

#### Scenario: Constant input yields RSI 50

- **WHEN** `rsi([10.0] * 30, 14)` is called
- **THEN** every defined position (index ≥ 14) SHALL equal `50.0`; positions 0..13 SHALL be `None`

#### Scenario: Strictly rising input yields RSI 100

- **WHEN** `rsi([float(i) for i in range(1, 31)], 14)` is called
- **THEN** every defined position (index ≥ 14) SHALL equal `100.0`

---

### Requirement: MACD — moving average convergence divergence

`macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[list[float | None], list[float | None], list[float | None]]` SHALL return `(macd_line, signal_line, histogram)` where `macd_line = ema(closes, fast) - ema(closes, slow)`, `signal_line = ema(macd_line_defined_only, signal)` re-aligned to original length with `None` warmup, and `histogram = macd_line - signal_line`.

#### Scenario: All three outputs same length as input

- **WHEN** `macd([float(i) for i in range(1, 51)])` is called with default parameters
- **THEN** all three returned lists SHALL have length 50; the first defined position of `macd_line` SHALL be at index `slow - 1 = 25`; the first defined position of `signal_line` SHALL be at index `slow - 1 + signal - 1 = 33`

---

### Requirement: ATR — Wilder's average true range

`atr(bars: list[BarRow], period: int = 14) -> list[float | None]` SHALL compute true-range `tr_t = max(h_t - l_t, |h_t - c_{t-1}|, |l_t - c_{t-1}|)` for each bar (with `tr_0 = h_0 - l_0`, since no prior close exists), then apply Wilder smoothing with seed = SMA of first `period` true-range values. First defined position SHALL be at index `period`.

#### Scenario: ATR over flat bars equals high-minus-low

- **WHEN** `atr([{"ts": f"2026-04-{d:02d}", "o": 100.0, "h": 110.0, "l": 90.0, "c": 100.0, "v": 0, "amount": 0} for d in range(1, 21)], 14)` is called
- **THEN** every defined position (index ≥ 14) SHALL equal `20.0` (every TR is `110 - 90 = 20`)

---

### Requirement: Bollinger Bands

`bollinger_bands(closes: list[float], period: int = 20, k: float = 2.0) -> tuple[list[float | None], list[float | None], list[float | None]]` SHALL return `(upper, middle, lower)` where `middle = sma(closes, period)`, `upper = middle + k * rolling_std(closes, period)`, `lower = middle - k * rolling_std(closes, period)`. Standard deviation SHALL be the population std (denominator `period`, not `period - 1`) to match the canonical John Bollinger definition.

#### Scenario: Constant input yields zero-width band

- **WHEN** `bollinger_bands([5.0] * 25, period=20, k=2.0)` is called
- **THEN** for every defined position (index ≥ 19), `upper == middle == lower == 5.0` (rolling std is 0)
