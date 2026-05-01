## ADDED Requirements

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

## MODIFIED Requirements

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
