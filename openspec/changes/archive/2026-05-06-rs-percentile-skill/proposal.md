## Why

`sepa-trend-template` already takes `rs_percentile` as input (condition c8 requires `rs_percentile ≥ 65`), but **nothing in the codebase produces it yet**. The screener / SEPA trend-template are blocked: every call must pass `None`, which forces c8 into tri-state `None` and the whole template to `passed=False`. We need a deterministic, cached calculator that returns both the cross-sectional RS Rating (1–99) used by c8 and the Mansfield RS line used by SEPA Stage-2 confirmation, computed over the TWSE+OTC liquid universe.

## What Changes

- Add new skill `rs_percentile_calc` exposing two callables:
  - `compute_rs_rating(symbol, asof) -> int | None` — cross-sectional 1–99 percentile across the eligible universe
  - `compute_rs_line(symbol, asof, benchmark="^TWII") -> RsLineResult` — Mansfield RS line series + slope + new-high flag
- Define eligible universe: TWSE+OTC stocks with 20-day average dollar volume ≥ NT$100M, listed for ≥ 252 trading days, not in disposition/full-cash settlement
- Cache RS Rating per `(asof_date)` in SQLite (one row per symbol per date) to avoid recomputing the universe on every screener call
- Wire the existing `evaluate_trend_template` callers to fetch `rs_percentile` by calling `compute_rs_rating` directly instead of passing `None`

**Descoped (deferred):** the `market_data_tool.get_rs_percentile` tool-registry wrapper referenced in `docs/design-zh-TW.md` §4.4.1. No tool registry exists in `src/ohmystock` yet, and standing one up just for this single consumer is pre-emptive abstraction (CLAUDE.md §2). Callers import `compute_rs_rating` directly. When a second tool needs registering, propose `tool-registry-v0` and migrate both at once.

## Capabilities

### New Capabilities

- `rs-percentile`: Cross-sectional RS Rating (1–99) and Mansfield RS line over the TWSE+OTC liquid universe, with daily caching and explicit universe-membership rules

### Modified Capabilities

(none — `sepa-trend-template` already accepts `rs_percentile` as input; no behavioral change to that spec is needed)

## Impact

- New module: `src/ohmystock/sepa/rs.py` (or `src/ohmystock/skills/rs_percentile_calc.py` per skills layout)
- New SQLite table: `rs_rating_cache(asof_date, symbol, rs_rating, universe_size, computed_at)`
- New connector dependency: bulk historical bars for the full TWSE+OTC universe (FinMind primary, Shioaji fallback) — first warm-up will be slow; daily incremental after that
- Touches: `src/ohmystock/sepa/trend_template.py` callers (screener / Phase 2 entry pipeline) — they switch from passing `None` to importing `compute_rs_rating` directly
- No spec change to `sepa-trend-template`; c8 behavior is unchanged
