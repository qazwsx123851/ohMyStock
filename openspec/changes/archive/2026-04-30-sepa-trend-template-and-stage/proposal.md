## Why

`workflow-cheatsheet.md` v3.1 §0.4 and §2 第二層 codify Mark Minervini's SEPA framework as the new SSOT for entry filtering — every Phase 1/2/3 screener, the Phase 2B scoring, and the LLM Decider all now branch on **Stage classification** (1/2/3/4) and the **8-condition Trend Template**. The hard-reject for Stage 4 is described as a *pre-check* that runs ahead of any score-based ranking. Until those two primitives exist as code, the next four Phase 2 changes (`rs-percentile-skill`, `vcp-pivot-pattern-skill`, `fundamental-data-fetch`, `screener-and-phase2b-assembler`) can't be wired together without each reinventing the same MA50/MA150/MA200 logic and disagreeing on the slope-of-MA200 / 52-week distance conventions.

This change builds the smallest pure-function skill that owns those two primitives so all downstream consumers share one definition.

## What Changes

- Add `src/ohmystock/sepa/` package with two pure functions:
  - `evaluate_trend_template(bars: list[BarRow], rs_percentile: float | None) -> TrendTemplateResult` — runs the 8 Minervini conditions per `workflow-cheatsheet.md` §2 第二層 table and returns the per-condition pass/fail map plus the overall boolean.
  - `classify_stage(bars: list[BarRow]) -> StageResult` — returns Stage `1`/`2`/`3`/`4` plus a short reason string. Stage 4 detection follows §0.4 exactly (MA50<MA150<MA200 **and** close<MA50 **and** MA200 has not risen over the past 20 trading days).
- Add a thin convenience wrapper `is_stage_4_reject(bars) -> bool` so the Phase 2B pre-check filter can call it without unpacking the full `StageResult`.
- RS Percentile is **NOT** computed here — it is an injected scalar (kept optional in the function signature; if `None`, condition (8) records `unknown` and `trend_template_pass` is `False`). The actual RS calculator ships in the next change `rs-percentile-skill`.
- 52-week high/low are computed from the input `bars` directly (last 252 trading days). The function requires at least 252 bars or it raises `InsufficientHistoryError`; callers (screener) must filter by listing-age before invoking.
- MA200 slope-up is checked as "MA200[t] ≥ MA200[t-20] across each of the last 20 trading days" — i.e., monotonic non-decreasing for 20 sessions, the cheatsheet's "≥ 20 個交易日 MA200 單調或非降".
- **Scope cuts (deliberate)**:
  - No RS Percentile calculation (next change).
  - No VCP / Pivot Breakout pattern detection (own change).
  - No Stage 1↔2 transition heuristic — only point-in-time classification of the *most recent* bar.
  - No multi-timeframe (weekly chart) Stage analysis. Daily bars only.
  - No tool-envelope wrapper — pure Python primitives only; the Phase 2B pipeline will compose these.
- No new third-party dependencies. Reuses `BarRow` from `ohmystock.data.sources.base` and `sma` from `ohmystock.indicators.core`.

## Capabilities

### New Capabilities

- `sepa-trend-template`: 8-condition Minervini Trend Template evaluator with explicit per-condition trace. Owns the local conventions (MA200 slope window = 20 sessions; 52-week window = 252 bars; RS Percentile threshold 65; close-vs-52W-low ≥ 30%).
- `sepa-stage-classification`: Point-in-time Stage 1/2/3/4 classifier on daily bars. Owns the §0.4 Stage 4 reject definition that is the SSOT for the Phase 2B `pre_check` filter.

### Modified Capabilities

(none — this is greenfield. `technical-indicators` is consumed unchanged.)

## Impact

- **New code**: `src/ohmystock/sepa/__init__.py`, `src/ohmystock/sepa/trend_template.py`, `src/ohmystock/sepa/stage.py`, `src/ohmystock/sepa/types.py` (TypedDict / dataclass for `TrendTemplateResult` and `StageResult`).
- **New tests**: `tests/test_sepa_trend_template.py`, `tests/test_sepa_stage.py` — golden bar fixtures (synthetic Stage-2 ramp, synthetic Stage-4 decline, flat Stage-1) plus per-condition truth tables.
- **Reused**: `BarRow` from `ohmystock.data.sources.base`; `sma` from `ohmystock.indicators.core`.
- **Schema**: none — pure functions, no DB, no env vars.
- **Dependencies**: none new.
- **Downstream unblocks**:
  - `rs-percentile-skill` — will inject its output into condition (8) of `evaluate_trend_template`.
  - `vcp-pivot-pattern-skill` — Stage 2 confirmation gate before VCP search.
  - `screener-and-phase2b-assembler` — `is_stage_4_reject` becomes the Phase 2B `pre_check` filter; `evaluate_trend_template` becomes the §2 第二層 entry condition.
  - LLM Decider (Phase 3) — `StageResult.reason` and `TrendTemplateResult.conditions` are surfaced in the Phase 2B Swarm Input Assembler payload so the LLM sees structured per-condition reasoning.
- **Out of scope / future**:
  - RS Percentile calculation (next change).
  - VCP / cup-and-handle / platform breakout / pivot breakout detectors.
  - Stage 1→2 transition watcher (a separate strategy outside v3.1 scope).
  - Weekly-chart Stage analysis.
