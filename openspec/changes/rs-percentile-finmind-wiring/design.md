## Context

`rs-percentile-skill` (archived 2026-05-06) shipped the formula, schema, and
subscorer rewire but explicitly deferred all production wiring. Today
`compute_rs_rating` raises `RuntimeError` until `set_universe_closes_loader(...)`
is called, and `_build_universe`'s `disposition_set` parameter has no
producer. The scoring engine therefore receives `None` for every symbol, and
c8 of `evaluate_trend_template` silently degrades.

We already own two of the three data sources we need:

- **`universe_daily`** (`screener-tw-universe` capability, `screener/cache.py`)
  — daily-populated TWSE+OTC roster from FinMind `TaiwanStockInfo`. Has
  symbol, market, industry. Already populated by every screener run.
- **`bars_daily`** (`market-data-cache` capability) — daily OHLCV per symbol,
  populated on-demand by FinMind/Shioaji/twstock fallback chain. We need ~260
  trailing closes per symbol per `asof`.
- **disposition list** — *no source exists*. TWSE publishes 處置股 at
  `https://www.twse.com.tw/announcement/notice` and OTC publishes 全額交割
  at `https://www.tpex.org.tw/...`. We need a thin scrape + cache layer.

CLAUDE.md §2 says: avoid pre-emptive abstraction, single-source-of-truth, no
team-scale design. This change keeps the loader and scraper as plain modules
under `sepa/` and `data/`, no DI container, no plugin registry.

## Goals / Non-Goals

**Goals:**

- `compute_rs_rating(symbol, asof)` returns a real `int` in `[1, 99]` for
  liquid TWSE/OTC names on a recent trading day, end-to-end (FastAPI startup
  → loader wired → universe computed → cache hit on second call).
- Disposition-flagged symbols are excluded from the universe, even on cold
  cache, with graceful degrade if the scrape fails.
- Backfill the last 252 trading days into `rs_rating_cache` in one idempotent
  CLI run, so the first production screener call hits cache for any recent
  `asof`.
- E2E smoke test pins the contract: real loader, `2330` on a known date,
  result is an `int`, no `RuntimeError`.

**Non-Goals:**

- No new external connector. We consume `bars_daily` and `universe_daily` as
  they are; if a symbol isn't in `bars_daily` for a given `asof`, that symbol
  drops out of the universe on that day (existing `_build_universe`
  semantics). Bulk pre-fetch of missing bars is out of scope — Phase 1
  `data_pipeline_skill` already runs this for screener and we ride on it.
- No tool-registry wrapper (deferred again per `rs-percentile-skill` proposal).
- No live trading hookup — this still feeds Paper Trading.
- No retry/backoff layer for the disposition scrape. One try, fall back to
  last-known cached set on failure.

## Decisions

### Decision 1 — Loader reads from existing caches, not from FinMind directly

**What:** `build_universe_closes_loader(conn)` queries `universe_daily` for the
roster on `asof` and `bars_daily` for trailing closes per symbol. It does not
call `FinMindClient` itself.

**Why:** The screener already runs daily and populates `universe_daily`. The
market-data cache (`bars_daily`) already populates lazily during screener
runs. Going to FinMind directly would duplicate the fallback chain
(FinMind → twstock → yfinance) that lives in `data/market_data.py`, and
would force a 1500-symbol fan-out that the cache already amortizes.

**Alternative considered:** Have the loader call `FinMindClient.get_taiwan_stock_price` directly per symbol. Rejected — duplicates fallback logic and triples API quota usage.

### Decision 2 — Disposition scraper is a single function, no abstraction layer

**What:** `data/disposition.py::fetch_disposition_set(asof) -> set[str]` does
the scrape + cache + degrade in one function. No `DispositionSource` ABC, no
provider registry.

**Why:** CLAUDE.md §2 — single user, no team, no hypothetical second source.
TWSE and OTC are the only producers and they're stable government endpoints.
If a second source ever appears, we add a fallback inline, same way
`data/market_data.py` does.

**Alternative considered:** Mirror the `data/sources/finmind.py` adapter pattern with a `DispositionSource` protocol. Rejected — premature; one consumer, two stable upstreams.

### Decision 3 — Graceful-degrade contract: last-known set, then empty

**What:** On scrape failure, `fetch_disposition_set(asof)`:

1. Tries to read the most recent row in `disposition_list_cache` for any
   `asof_date <= requested` (last-known set).
2. If no rows exist (cold cache), returns `set()` with a warning log.

The universe builder accepts `set()` and proceeds — equivalent to "no
disposition filter applied today." This is a **conservative widening** (we
might let one or two flagged stocks score), preferable to crashing the
entire screener.

**Alternative considered:** Crash the screener on scrape failure. Rejected —
disposition affects ~10–30 names out of ~1500; a one-day stale list is
acceptable, a screener outage is not.

### Decision 4 — Loader wired in FastAPI lifespan, not at module import

**What:** `src/ohmystock/api/app.py` lifespan opens a connection, builds the
loader closure, calls `set_universe_closes_loader(loader)`, and `yield`s.
Tests inject their own loader via `set_universe_closes_loader(...)` directly
(or use `reset_providers()` after).

**Why:** Module-import wiring would force a DB connection at every
`from ohmystock.sepa.rs import ...`, breaking unit tests and CLI scripts that
don't have a DB ready. Lifespan wiring matches the existing pattern for the
EventBus subscriber and the journal connection.

**Alternative considered:** Auto-wire on first call inside `compute_rs_rating`. Rejected — implicit, hides startup ordering, and `_open_cache_conn` already exists for the cache write path; mixing two implicit-DB layers is fragile.

### Decision 5 — Backfill script is range-bounded and idempotent

**What:** `scripts/backfill_rs_rating.py --days 252` iterates the last 252
trading days from today and calls `compute_rs_rating("2330", asof)` for each
(any-symbol-triggers-full-compute pattern). Uses `INSERT OR REPLACE` so
re-runs are safe.

**Why:** The cache primary key is `(asof_date, symbol)`. Re-computing a day
just overwrites. Range-bounded prevents accidental "all of history" runs
that would burn the FinMind quota.

**Output:** prints `asof | universe_size | elapsed_ms` per day, then a final
row-count assertion (`SELECT COUNT(*) FROM rs_rating_cache` ~ `1500 * 252`
order of magnitude).

## Risks / Trade-offs

- **Risk:** `bars_daily` is sparse for thinly-traded names → loader returns
  fewer than 253 closes for some symbols → `_weighted_score` returns `None` →
  symbol drops out of cached set. **Mitigation:** This is the correct
  behavior — illiquid names shouldn't get an RS Rating anyway. Document in
  spec that "loader-side bar shortage maps to None at the cache level."
- **Risk:** TWSE/OTC scrape endpoints change HTML format → scraper breaks
  silently. **Mitigation:** scraper raises `DispositionScrapeError` on parse
  failure; graceful-degrade catches it and warns; a daily backfill run
  surfaces persistent breakage in the log.
- **Risk:** First backfill blows past FinMind quota. **Mitigation:** loader
  reads from `bars_daily` cache, not FinMind. Cache fills lazily through
  normal screener runs; if cold, backfill triggers `bars_daily` lazy fills
  one symbol at a time with the existing fallback chain. Worst case: ~3–5
  hours, not unbounded.
- **Trade-off:** Disposition graceful-degrade can let a flagged stock score
  for one day. Accepted — disposition is a soft signal (TWSE itself allows
  the stock to trade with restrictions); a one-day window is within tolerance.

## Migration Plan

1. Land this change → wire the loader → backfill runs once → cache populated.
2. Next screener run reads RS Rating from cache instead of `None`.
3. No rollback path needed: if the loader misbehaves, `set_universe_closes_loader(None)` (or removing the lifespan wiring) returns to the prior `RuntimeError` state, which the scoring engine already tolerates (subscorer maps `None` to 0 pts and continues).

## Open Questions

- None blocking. Disposition scrape URLs and HTML structure will be
  finalized in task §2 by reading the actual TWSE/OTC pages; if either
  endpoint requires JS rendering we fall back to the JSON API the same
  pages expose.
