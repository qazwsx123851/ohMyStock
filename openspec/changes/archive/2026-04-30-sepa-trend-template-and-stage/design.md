## Context

The SEPA framework was adopted in `workflow-cheatsheet.md` v3.1 (2026-04-28, decision #16 in `docs/v3-decisions.md`). Two of its primitives — Trend Template (8 conditions) and Stage classification (1/2/3/4) — are referenced from at least four different downstream consumers:

1. Phase 1 weekly screener (`§2 第二層`).
2. Phase 2A intraday scan (Stage 2 confirmation, `§2 第三層`).
3. Phase 2B `pre_check` filter (`§0.4 Stage 4 hard reject`).
4. Phase 3 LLM Decider Swarm Input Assembler (the per-condition trace gets surfaced to the LLM).

If each consumer reimplements the math, MA200-slope window length and 52-week distance conventions will inevitably drift. This change centralises both primitives behind a stable signature.

`technical-indicators` (archive `2026-04-30-technical-indicators-skill`) already ships `sma`, `ema`, `atr`, etc., as pure functions over `list[BarRow]` / `list[float]` with `None` for warmup positions. This change reuses that convention (no NaN, length-preserving outputs).

## Goals / Non-Goals

**Goals:**

- Single owner for the §0.4 Stage 4 reject definition; `is_stage_4_reject(bars) -> bool` is the only function the Phase 2B pre-check filter needs.
- Single owner for the 8-condition Trend Template; per-condition trace is observable so the LLM Decider can cite which condition failed.
- Pure functions, deterministic, no I/O, fully unit-testable with synthetic bars.
- Strict input validation at the boundary: < 252 bars raises `InsufficientHistoryError` rather than silently producing wrong 52-week values.

**Non-Goals:**

- Computing RS Percentile (`rs-percentile-skill` next change).
- Detecting VCP / cup-and-handle / pivot breakout patterns (own change).
- Stage transition detection (Stage 1→2 watcher) — only point-in-time classification of the most recent bar.
- Weekly-chart Stage analysis. Daily bars only.
- A `get_stage(symbol)` tool wrapper. Composition happens at the Phase 2B pipeline layer, not here.

## Decisions

### D1. Module location: `src/ohmystock/sepa/`

Sibling of `indicators/`, `chip/`, `backtest/`. Not nested under `indicators/` because Stage and Trend Template are *strategy-framework-specific*, not generic indicators. A future Wyckoff or Weinstein-pure module would live under a different sibling for the same reason.

**Alternative considered:** Put everything under `src/ohmystock/strategies/sepa/`. Rejected — `strategies/` already exists for backtest strategies (`src/ohmystock/backtest/strategy/`), and these primitives are pre-strategy filters used by the screener too.

### D2. Output shape: dataclass with explicit per-condition trace

```python
@dataclass(frozen=True)
class TrendTemplateResult:
    passed: bool                              # all 8 conditions pass
    conditions: dict[str, ConditionOutcome]   # 8 entries: c1..c8
    rs_percentile: float | None               # echoed back for traceability

@dataclass(frozen=True)
class ConditionOutcome:
    name: str            # human-readable, e.g. "close > MA50"
    passed: bool | None  # None means "could not evaluate" (e.g. RS Percentile not provided)
    detail: str          # short reason, e.g. "close=125.5, MA50=118.2"
```

```python
@dataclass(frozen=True)
class StageResult:
    stage: Literal[1, 2, 3, 4]
    reason: str
```

Rationale: a plain `bool` would force the LLM Decider input assembler to recompute every condition just to explain *why* a stock failed. Returning the full trace once, frozen, is cheap.

**Alternative considered:** Return `bool` and require callers to call individual condition predicates. Rejected — every caller would need to call 8 predicates and assemble a dict, defeating the SSOT goal.

### D3. RS Percentile is an injected parameter, not computed here

Signature: `evaluate_trend_template(bars: list[BarRow], rs_percentile: float | None) -> TrendTemplateResult`.

When `rs_percentile is None`, condition (8) records `passed=None` and the overall `passed` is `False` (we never trend-template-pass without RS evidence).

Rationale: RS Percentile requires the *whole TWSE+OTC universe* on the same date — a cross-section, not a single-symbol time series. Conflating it into this function would couple a per-symbol primitive to universe-wide data fetching. The screener (downstream) computes RS Percentile once per universe-date and injects it.

**Alternative considered:** Auto-compute RS Percentile inside the function by accepting a `peers: dict[str, list[BarRow]]` param. Rejected — pollutes signature for the 90% of callers that already have the percentile cached.

### D4. MA200 slope-up = monotonic non-decreasing for last 20 sessions

Cheatsheet text: "MA200 過去 ≥ 20 個交易日 MA200 單調或非降". Implementation: `all(ma200[i] >= ma200[i-1] for i in range(t-19, t+1))` where `t` is the index of the most recent bar.

**Alternative considered:** Compare endpoints only (`ma200[t] >= ma200[t-20]`). Rejected — allows a sharp dip in the middle, which Minervini explicitly warns against.

### D5. 52-week window = exactly 252 trading days, not calendar days

The function looks at `bars[-252:]` for high/low. If `len(bars) < 252`, raise `InsufficientHistoryError`. Callers (the screener) must filter newly-listed names by listing-age before invoking.

Rationale: aligns with `technical-indicators`' length-preserving convention — never silently produce a half-window value.

### D6. Stage classification ladder is point-in-time on the *last* bar

The function evaluates Stage at `bars[-1]` only. It does not return per-bar Stage history. Callers needing historical Stage (e.g. Phase 5 review backfilling) must call this function per asof-date with the appropriate truncated `bars`.

Rationale: Stage history is rare; per-bar batch evaluation would dominate cost for the common single-symbol-today path.

### D7. Stage definitions

Following Stan Weinstein / Minervini convention as cited in the cheatsheet:

- **Stage 4** (overrides everything): `MA50 < MA150 < MA200` AND `close < MA50` AND MA200 has not risen over the last 20 sessions. *(§0.4 SSOT.)*
- **Stage 2**: `close > MA50 > MA150 > MA200` AND MA200 rising for ≥ 20 sessions. *(§2 第三層.)*
- **Stage 3**: passes Stage 2 mean-stack but the 30-day high-vs-low range exceeds 20% of price (high-volatility distribution). *(§2 第三層 footnote.)*
- **Stage 1**: everything else (basing / accumulation; not Stage 2/3/4).

The classifier returns the *first* matching Stage in the order: 4 → 2/3 → 1. Stage 4 wins ties because §0.4 is a hard reject.

### D8. Errors

- `InsufficientHistoryError` (subclass of `ValueError`) — raised when `len(bars) < 252`.
- All other inputs (e.g. `rs_percentile=-1`) silently return `passed=False` with a `detail` string explaining the issue. We do not raise on bad RS Percentile because the upstream RS skill is responsible for its own validation.

## Risks / Trade-offs

- [Risk] Cheatsheet text says "理想 ≥ 4–5 個月" for MA200 trend, but mandates only ≥ 20 trading days. We implement the *mandate* (20 sessions); the "ideal" 4-5-month version is a soft signal the LLM can layer on top via the conditions trace. → Mitigation: documented in `evaluate_trend_template` docstring + spec scenario.
- [Risk] Stage 3 boundary (`30-day high-low range > 20% of price`) is a soft heuristic, not in the SSOT cheatsheet body — it appears only in the Stage 2 confirmation parenthetical. Down the line a v3.2 cheatsheet refinement may sharpen this and force a delta change. → Mitigation: encapsulate the threshold as a module-level constant `STAGE_3_RANGE_THRESHOLD = 0.20`, reviewed at every cheatsheet bump.
- [Risk] Stage 4 reject is destructive (hard reject of any candidate). A bug here silently kills good entries. → Mitigation: golden-fixture tests must cover (a) flat-then-decline transition into Stage 4 and (b) Stage-2-with-pullback that *does not* qualify as Stage 4. The Phase 2B integration test will additionally log every reject with the `StageResult.reason` for human audit.
- [Trade-off] Returning `ConditionOutcome.passed: bool | None` makes the type a tri-state. Callers checking `if outcome.passed` would treat `None` as `False`, which matches our intended semantics. We accept the type-narrowing nuisance in exchange for keeping "RS not yet computed" distinguishable from "RS computed and failed".
