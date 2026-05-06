## Why

`rs-percentile-skill` shipped the formula, cache, and subscorer rewire, but
`compute_rs_rating` is **inert in production**: it raises `RuntimeError` until
`set_universe_closes_loader(...)` is called, and `_build_universe`'s
`disposition_set` parameter has no producer. Today every call from the scoring
engine returns `None`, so c8 of `evaluate_trend_template` never observes a real
RS Rating. This change wires the deferred §2.2 / §6.2 / §6.3 / §8.2 work: a
production loader sourced from existing `bars_daily` + `universe_daily` caches,
a TWSE/OTC disposition-list scraper with graceful degrade, a one-time backfill
script, and an E2E smoke test against `2330`.

## What Changes

- Add `src/ohmystock/sepa/rs_loader.py` exposing `build_universe_closes_loader(conn) -> Callable[[date], dict[str, list[float]]]` that:
  - Reads the symbol roster from `universe_daily` (already populated by the screener)
  - Reads ~260 trailing daily closes per symbol from `bars_daily` (the market-data-cache)
  - Returns `{symbol: closes[]}` shaped for `_compute_universe_ratings`
- Add `src/ohmystock/data/disposition.py` exposing `fetch_disposition_set(asof) -> set[str]` that:
  - Scrapes the TWSE 處置股 + OTC 全額交割 lists (HTTP + HTML/JSON parse, no new SDK)
  - Caches results in a new `disposition_list_cache(asof_date, symbol)` SQLite table
  - Degrades gracefully on scrape failure (warn + return last-known set, or empty if cold)
- Wire both at app startup in `src/ohmystock/api/app.py` lifespan: open a connection, build the loader, call `set_universe_closes_loader(...)`. CLI entrypoints (`scripts/backfill_rs_rating.py`) wire the same way.
- Add `scripts/backfill_rs_rating.py`: one-time backfill iterating the last 252 trading days, computing + caching each `asof`'s universe via `compute_rs_rating(any_symbol, asof)`. Idempotent (uses `INSERT OR REPLACE`).
- Add `tests/test_sepa_rs_loader.py`, `tests/test_disposition.py`, `tests/test_rs_percentile_e2e.py` (the smoke that closes out §8.2).

## Capabilities

### New Capabilities

(none — all work attaches to the existing `rs-percentile` capability)

### Modified Capabilities

- `rs-percentile`: add requirements covering (a) the production loader source-of-truth contract — symbol roster from `universe_daily`, closes from `bars_daily`, ≥ 253 bars per symbol; (b) disposition-list source — daily TWSE/OTC scrape with caching and graceful degrade on fetch failure; (c) backfill entrypoint behavior — idempotent, range-bounded, and emits a final row-count check.

## Impact

- New files: `src/ohmystock/sepa/rs_loader.py`, `src/ohmystock/data/disposition.py`, `scripts/backfill_rs_rating.py`, `tests/test_sepa_rs_loader.py`, `tests/test_disposition.py`, `tests/test_rs_percentile_e2e.py`
- New SQLite table: `disposition_list_cache(asof_date TEXT, symbol TEXT, fetched_at TEXT, PRIMARY KEY (asof_date, symbol))` (idempotent `init_schema` lives in `data/disposition.py`)
- Touches: `src/ohmystock/api/app.py` lifespan to wire the loader once at startup
- No spec change to `external-connectors` or `market-data-cache` — both already provide what we need; we are consumers, not producers
- Depends on: rs-percentile-skill (already archived 2026-05-06), market-data-cache (`bars_daily` table), screener-tw-universe (`universe_daily` table)
- First production warm-up: backfill script runs ~252 day-by-day computes; expect ~10–20 min cold + cache hits afterward
