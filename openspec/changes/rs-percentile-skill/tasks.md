## 1. Schema & types

- [x] 1.1 Add idempotent `init_schema(conn)` in `src/ohmystock/sepa/rs.py` creating `rs_rating_cache(asof_date TEXT, symbol TEXT, rs_rating INTEGER, universe_size INTEGER, computed_at TEXT, PRIMARY KEY (asof_date, symbol))` plus `idx_rs_rating_asof` (mirrors `journal/schema.py` pattern, `CREATE TABLE IF NOT EXISTS`)
- [x] 1.2 Define dataclasses in `src/ohmystock/sepa/rs.py`: `RsLineResult(series, slope_20d, at_52w_high, benchmark_used)` (frozen) and reuse existing `InsufficientHistoryError` from `sepa.types`

## 2. Universe builder

- [x] 2.1 Implement `_build_universe(asof: date) -> list[str]` filtering TWSE+OTC common stocks by listing-age >= 252 trading days, 20d avg dollar volume >= NT$100M, not on disposition/full-cash list, valid close on asof (signature takes pre-fetched `info_rows / bars_by_symbol / disposition_set` for unit-testability; production wiring lives above this layer in 2.2)
- [x] 2.2 ~~Add disposition-list fetcher with graceful degrade~~ — **DEFERRED to follow-up `rs-percentile-finmind-wiring`**: needs FinMind/TWSE-OTC scrape connector that doesn't exist yet. `_build_universe` accepts `disposition_set: set[str]` so wiring lands cleanly above when it ships.
- [x] 2.3 Unit tests: newly-listed excluded, illiquid excluded, disposition-flagged excluded, suspended excluded (`tests/test_sepa_rs.py::TestBuildUniverse`)

## 3. RS Rating calculator

- [x] 3.1 Implement `_weighted_score(close_series, asof) -> float` returning `0.25*R63 + 0.25*R126 + 0.25*R189 + 0.25*R252`
- [x] 3.2 Implement `_compute_universe_ratings(asof) -> dict[str, int]` computing scores for the whole universe and rank-percentile to 1..99 with `method="min"` ties
- [x] 3.3 Implement public `compute_rs_rating(symbol, asof) -> int | None` with cache read -> batch compute on miss -> cache write
- [x] 3.4 Unit tests: best=99, median=50, ties get lower rank, unknown symbol returns None, suspended returns None (`tests/test_sepa_rs.py::TestComputeRsRating` + `TestRankMin` + `TestPercentileFromRank`)

## 4. Mansfield RS line

- [x] 4.1 Implement `compute_rs_line(symbol, asof, benchmark="^TWII", lookback=252) -> RsLineResult` with SMA52w warmup check raising `InsufficientHistoryError`
- [x] 4.2 Unit tests: monotonic outperformance -> `at_52w_high=True` and `slope_20d > 0`; 300-bar history raises with message naming 300 and 504 (`tests/test_sepa_rs.py::TestComputeRsLine`)

## 5. Public API exposure (tool wrapper deferred)

- [x] 5.1 ~~Register `market_data_tool.get_rs_percentile`~~ — **DEFERRED** until a tool registry exists. `compute_rs_rating` is the public entrypoint instead.
- [x] 5.2 ~~Update `docs/tools-contracts.md`~~ — **DEFERRED** with 5.1.
- [x] 5.3 ~~Tool integration test~~ — **DEFERRED** with 5.1. Coverage moves into 3.4 (calling `compute_rs_rating` directly).

## 6. Wire callers + backfill

- [x] 6.1 Update screener / Phase 2 entry pipeline call sites that currently pass `rs_percentile=None` to call `compute_rs_rating(symbol, asof)` directly — grep confirms no production callsite of `evaluate_trend_template(...)` exists; the rs_percentile flow runs through the consolidated subscorer (`scoring/subscorers/rs_percentile.py` → `compute_rs_rating`) and out via `_engine._build_sepa_fields` (`src/ohmystock/scoring/_engine.py:251-258`)
- [x] 6.2 ~~Write one-time backfill script `scripts/backfill_rs_rating.py` populating cache for the last 252 trading days~~ — **DEFERRED to `rs-percentile-finmind-wiring`** (depends on §2.2 + a FinMind universe-closes loader that wires `set_universe_closes_loader`)
- [x] 6.3 ~~Run backfill against local FinMind sponsored member; verify row count is approximately 1500 * 252~~ — **DEFERRED with §6.2**

## 7. Consolidate existing subscorer onto this skill (Decision 6)

- [x] 7.1 Refactor `src/ohmystock/scoring/subscorers/rs_percentile.py` to call `sepa.rs.compute_rs_rating(ctx.symbol, ctx.asof_date)` and map the returned `int | None` to 0/3/5/7 pts at thresholds 65/80/90 (skip when `None`); drop the IBD-weighted `_weighted_return` and the universe-loader call
- [x] 7.2 Delete `src/ohmystock/scoring/_rs_universe.py` (no longer needed; `sepa.rs._build_universe` is the single producer)
- [x] 7.3 Rewrite `tests/test_subscorer_rs_percentile.py` to monkeypatch `sepa.rs.compute_rs_rating` (or its cache) instead of `set_rs_universe_loader`; keep the 65/80/90 → 3/5/7 threshold-band assertions
- [x] 7.4 Grep for any remaining imports of `scoring._rs_universe` — only matches were in archived openspec docs and self-references in this change; engine-test helpers (`tests/test_scoring_engine_real_subscorers.py`, `tests/test_scoring_engine_sepa_fields.py`) updated to `unittest.mock.patch` the new `compute_rs_rating` delegate

## 8. Validation

- [x] 8.1 Run `openspec validate rs-percentile-skill --strict` and resolve any issues — passes
- [x] 8.2 ~~End-to-end smoke: call `evaluate_trend_template(bars, rs_percentile=compute_rs_rating("2330", today))` on a known Stage-2 ramp and confirm `passed=True`~~ — **DEFERRED to `rs-percentile-finmind-wiring`** (needs a configured `set_universe_closes_loader` to return a real `int`)
- [x] 8.3 Update `docs/workflow-cheatsheet.md` §17 doc-relations to point c8's RS source at `sepa/rs.py` (added bullet naming `compute_rs_rating` + `rs_rating_cache`)
- [x] 8.4 Run full `pytest` suite and confirm green — 897 passed, 0 failed (after engine-test helpers updated to mock `compute_rs_rating`)
