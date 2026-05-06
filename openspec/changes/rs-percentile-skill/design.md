## Context

`sepa-trend-template` ships with c8 requiring `rs_percentile ≥ 65`, but no producer exists. The screener and Phase 2 entry pipeline are forced to pass `rs_percentile=None`, which always trips c8's tri-state path and makes the trend template useless in practice.

The project's SSOT for RS calculation lives in two docs:

- `docs/workflow-cheatsheet.md` §RS — defines the **63/126/189/252-day equal-weighted** formula and threshold 65
- `docs/design-zh-TW.md` §4.4.1 — defines the universe (TWSE+OTC, 20d avg dollar volume ≥ NT$100M) and references the future `market_data_tool.get_rs_percentile`

The user's `/opsx:propose` clarification picked the **IBD-style 0.4/0.2/0.2/0.2 weighting**, but per `CLAUDE.md` §5 the workflow-cheatsheet is the business-logic SSOT, so we follow the equal-weight formula. The IBD pick is captured here as alternative-considered. If the user later wants to switch, the change is one constant in `rs.py` plus a regenerated cache.

Constraints:

- Solo dev / personal project — avoid heavy abstractions (no plugin system, no factory pattern, no abstract universe builder)
- Cost: bulk historical bars fetched once per day for the whole universe (~1500 names × 252 bars first time, then daily incremental)
- Data sources: FinMind sponsored member is primary (we already pay), Shioaji as fallback (already used for paper broker)

## Goals / Non-Goals

**Goals:**

- Unblock `evaluate_trend_template` callers — c8 receives a real integer in 1..99 instead of `None`
- One canonical formula and one cache, accessed only via `market_data_tool.get_rs_percentile`
- Cache key = `(asof_date, symbol)` so historical queries (backtest replay) reuse compute
- Mansfield RS line available for SEPA Stage-2 confirmation later (consumed in a separate change)

**Non-Goals:**

- Not building a generic "ranking framework" — only RS Rating
- No IBD Composite Rating (combines RS with EPS/SMR/etc.) — out of scope
- No sector-relative RS — single benchmark TWII for now
- No incremental "update only changed symbols" optimization — daily full universe recompute is fast enough at ~1500 names
- No live intraday RS — `asof` is a calendar date, not a timestamp

## Decisions

### Decision 1: Equal-weight 25/25/25/25 over 63/126/189/252-day returns

**Choice:** `score = 0.25 * R63 + 0.25 * R126 + 0.25 * R189 + 0.25 * R252`

**Rationale:** Matches `docs/workflow-cheatsheet.md` §RS (the SSOT). Smoother than single 12-month return, avoids overweighting most-recent quarter the way IBD does.

**Alternative considered:** IBD-style `0.4*R63 + 0.2*(R126+R189+R252)` (the user's clarification pick). Rejected because the SSOT cheatsheet specifies equal weights. Switching is a one-line constant change if we later disagree.

**Alternative considered:** Mansfield RS slope as the percentile basis. Rejected — the slope is useful as an additional signal (kept in `compute_rs_line`) but it's noisier than multi-period returns for cross-sectional ranking.

### Decision 2: Tri-state output via `None`, not exception

**Choice:** `compute_rs_rating` returns `None` for any ineligible/unknown/suspended symbol; never raises for "expected" misses.

**Rationale:** `evaluate_trend_template` already encodes a tri-state c8 path on `rs_percentile is None`. Raising would force every caller to wrap in try/except and the screener processes thousands of symbols a day.

`InsufficientHistoryError` is reserved for `compute_rs_line` because that path is called per-symbol in the entry pipeline, where a missing history is a real bug worth surfacing.

### Decision 3: Single SQLite table, batch-on-miss

**Choice:** `rs_rating_cache(asof_date, symbol, rs_rating, universe_size, computed_at)`. First call for a new `asof_date` computes the entire universe and inserts all rows in one transaction; subsequent calls hit the cache.

**Rationale:** Simpler than per-symbol caching with TTL. Universe-wide compute is the natural unit because every rank depends on every other symbol's score. ~1500 rows per day × ~250 trading days/year = ~375K rows/year — tiny for SQLite.

**Alternative considered:** Recompute on every call. Rejected — even with cached bars, the rank step is O(N log N) and screener calls `compute_rs_rating` for ~1500 symbols.

**Alternative considered:** Redis. Rejected — adds a service for no benefit on a localhost solo project.

### Decision 4: Universe membership computed inside the same skill, not a separate service

**Choice:** Universe build (liquidity filter + listing-age filter + disposition exclusion) lives in `_build_universe(asof)` in the same `rs.py` module.

**Rationale:** Universe rules are tightly coupled to the RS formula (the formula only makes sense over the eligible set). Extracting them invites drift. If a second feature needs the same universe later, refactor then — not pre-emptively.

### Decision 5: FinMind primary, Shioaji fallback for bulk bars; disposition list from TWSE/OTC daily HTTP

**Choice:** Bulk historical bars from FinMind (`TaiwanStockPrice` + universe list); disposition flags from TWSE/OTC daily disclosure pages (already used elsewhere in the project per `docs/design-zh-TW.md`).

**Rationale:** Reuse existing connectors. The Shioaji fallback only kicks in if FinMind quota is exhausted that day.

### Decision 6: Consolidate the existing `subscorers/rs_percentile.py` onto this skill (no parallel formula)

**Choice:** `sepa/rs.py` is the **single producer** of RS Rating. The existing `scoring/subscorers/rs_percentile.py` (shipped via archived `phase-2b-sepa-subscorers`) refactors to call `compute_rs_rating(ctx.symbol, ctx.asof_date)` and just maps the returned 1..99 to the 3/5/7-point band at thresholds 65/80/90. The seed `scoring/_rs_universe.py` loader is deleted — the real `_build_universe(asof)` in `sepa/rs.py` replaces it.

**Rationale:** Two RS formulas in one repo is the SSOT trap CLAUDE.md §2 warns against. The shipped subscorer currently uses IBD weights `0.4/0.2/0.2/0.2`; this skill (per `workflow-cheatsheet.md` §RS) uses equal weights `0.25/0.25/0.25/0.25`. Without consolidation they'd silently disagree. Folding them onto one producer means c8 (trend-template tri-state) and the 7-pt sub-score share the same number.

**Alternative considered:** Keep both — IBD-weight subscorer for scoring, equal-weight skill for c8. Rejected; documented divergence still rots in practice.

**Alternative considered:** Update the spec to IBD weights to match the shipped code. Rejected; the cheatsheet SSOT is equal-weight and changing the SSOT requires a separate proposal.

### Decision 7: Inline `init_schema(conn)` instead of a `migrations/` directory

**Choice:** The `rs_rating_cache` table is created by an idempotent `init_schema(conn)` helper co-located in `src/ohmystock/sepa/rs.py` (or `sepa/rs_schema.py`), invoked once on first cache access — same pattern as `journal/schema.py`.

**Rationale:** No `migrations/` directory exists in this repo. The existing pattern (`init_schema(conn)` with `CREATE TABLE IF NOT EXISTS`) is what the project uses for `journal_entries`, `journal_entries_fts`, and `llm_costs`. Following the convention is simpler than introducing a migration runner.

## Risks / Trade-offs

- **First warm-up is slow** (~1500 symbols × 504 bars ≈ 750K rows from FinMind) → Mitigation: run as a one-time backfill script during Phase 1, not lazily on first user call. Subsequent days only need the latest bar appended.

- **Disposition list scraping is brittle** (TWSE/OTC HTML format) → Mitigation: graceful degrade — if scrape fails, skip the disposition filter for that day and emit a warning event. The liquidity filter alone catches ~95% of names we'd want excluded.

- **Threshold 65 vs IBD 70 is a calibration guess** → Mitigation: the threshold lives in `sepa-trend-template` spec (already), not in this skill. If WFA shows we're letting in too much noise, we tune c8's threshold without touching the RS calculation.

- **Equal-weight vs IBD-weight formula will produce different ranks** → Mitigation: documented in Decision 1; the user's preferred formula is one constant away if they disagree with the SSOT.

- **Cache invalidation when a symbol gets retroactively delisted** → Mitigation: not handled — historical RS Rating reflects the universe as it was on `asof_date`. Acceptable for backtest replay (which is the only consumer of historical rows).

## Migration Plan

This is a greenfield capability — no migration. Deployment steps:

1. Land schema migration `rs_rating_cache` table
2. Land `compute_rs_rating` + `compute_rs_line` + `_build_universe`
3. Land tool registration `market_data_tool.get_rs_percentile`
4. Run one-time backfill script for the last 252 trading days (so backtest has historical RS available)
5. Update screener / `evaluate_trend_template` callers to use the new tool

Rollback: drop the table + revert the registration. `evaluate_trend_template` callers fall back to passing `None` (current behavior).

## Open Questions

- (none blocking) Whether to expose the Mansfield RS line via a separate tool `market_data_tool.get_rs_line` or fold into `get_rs_percentile`. Defer until the SEPA Stage-2 change consumes it.
