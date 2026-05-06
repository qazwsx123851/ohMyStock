## ADDED Requirements

### Requirement: Production universe-closes loader sources symbols from `universe_daily` and closes from `bars_daily`

The production wiring of `set_universe_closes_loader` SHALL build a callable
that, given an `asof: date`, returns `dict[str, list[float]]` where:

- The set of keys is the TWSE+OTC roster from `universe_daily` for `asof`
  (the table populated by the `screener-tw-universe` capability).
- Each `closes` list contains the trailing closing prices ending at `asof`
  for that symbol, read from `bars_daily` (the `market-data-cache`
  capability), in ascending date order.
- A symbol whose `bars_daily` history contains fewer than `253` rows ending
  at `asof` SHALL be omitted from the returned dict; `_weighted_score`'s
  insufficient-history check is the second line of defense.

The loader SHALL NOT call `FinMindClient` directly. All upstream fetches go
through the existing `bars_daily` lazy-fill path so the FinMind/twstock/yfinance
fallback chain is reused.

The loader SHALL be wired exactly once at FastAPI app startup
(`src/ohmystock/api/app.py` lifespan) and once per CLI script that needs
`compute_rs_rating` (e.g., `scripts/backfill_rs_rating.py`). Tests SHALL be
free to inject a stub loader via the same `set_universe_closes_loader`
entrypoint and reset with `reset_providers()` after.

#### Scenario: Liquid symbol with full history yields an int rating after wiring

- **GIVEN** the loader is wired at app startup against a populated
  `universe_daily` and `bars_daily`
- **AND** symbol `2330` has ≥ 253 daily closes ending at `2026-04-30` in
  `bars_daily`
- **AND** `2330` is present in `universe_daily` for `2026-04-30`
- **WHEN** `compute_rs_rating("2330", "2026-04-30")` is called
- **THEN** the result is an `int` in `[1, 99]`
- **AND** no `RuntimeError` is raised

#### Scenario: Symbol with insufficient bars in cache is omitted from the universe

- **GIVEN** symbol `9999` is present in `universe_daily` for `2026-04-30`
- **AND** `bars_daily` has only 100 closes for `9999` ending at `2026-04-30`
- **WHEN** the loader is invoked for `2026-04-30`
- **THEN** `9999` is not a key in the returned dict
- **AND** `compute_rs_rating("9999", "2026-04-30")` returns `None`

#### Scenario: Loader does not bypass the bars_daily cache

- **GIVEN** the loader is invoked for an `asof` whose closes are already
  cached in `bars_daily`
- **WHEN** the loader builds its return dict
- **THEN** no direct `FinMindClient`, `Shioaji`, or `yfinance` call is issued
  by the loader itself

### Requirement: Disposition list is fetched daily, cached, and degrades gracefully on scrape failure

`fetch_disposition_set(asof: date) -> set[str]` SHALL be the single producer
of the `disposition_set` argument to `_build_universe`. It SHALL:

- On a cache miss for `asof`, scrape the TWSE 處置股 list and OTC 全額交割
  list and merge them into a `set[str]` of symbols.
- Persist the result in `disposition_list_cache(asof_date TEXT, symbol TEXT, fetched_at TEXT, PRIMARY KEY (asof_date, symbol))`.
  `asof_date` uses ISO `YYYY-MM-DD`; `fetched_at` uses ISO 8601 UTC.
- On a cache hit, return the cached set without re-scraping.
- On scrape failure (network error, HTTP non-2xx, parse error), log a warning
  and return the most recent cached set whose `asof_date <= asof`, or
  `set()` if no prior cache entry exists. The function SHALL NOT raise on
  scrape failure; it returns a possibly-stale set instead.

A daily empty result (legitimately no disposition stocks today) SHALL still
write a sentinel row so the next call counts as a cache hit and does not
re-scrape; the chosen sentinel format is implementation-defined but MUST be
distinguishable from a cold-cache miss.

#### Scenario: First call on a day scrapes and caches

- **GIVEN** `disposition_list_cache` has no rows for `asof_date = 2026-04-30`
- **AND** the TWSE/OTC scrape returns symbols `{"5678", "1234"}`
- **WHEN** `fetch_disposition_set("2026-04-30")` is called
- **THEN** the returned set is `{"5678", "1234"}`
- **AND** rows for both symbols are present in `disposition_list_cache` with
  `asof_date = "2026-04-30"`

#### Scenario: Second call same day hits cache

- **GIVEN** `disposition_list_cache` has rows for `asof_date = 2026-04-30`
- **WHEN** `fetch_disposition_set("2026-04-30")` is called again
- **THEN** the cached set is returned
- **AND** no HTTP request is made to TWSE/OTC

#### Scenario: Scrape failure with prior cache returns last-known set

- **GIVEN** the TWSE/OTC scrape raises a network error for `2026-04-30`
- **AND** `disposition_list_cache` has `{"5678"}` cached for `2026-04-29`
- **WHEN** `fetch_disposition_set("2026-04-30")` is called
- **THEN** the result is `{"5678"}`
- **AND** a warning is logged
- **AND** no exception propagates to the caller

#### Scenario: Scrape failure with cold cache returns empty set

- **GIVEN** the TWSE/OTC scrape raises a network error for `2026-04-30`
- **AND** `disposition_list_cache` has zero rows for any `asof_date`
- **WHEN** `fetch_disposition_set("2026-04-30")` is called
- **THEN** the result is `set()`
- **AND** a warning is logged

### Requirement: Backfill entrypoint is range-bounded, idempotent, and verifies row count

`scripts/backfill_rs_rating.py` SHALL provide a CLI entrypoint that:

- Accepts a `--days N` argument (default 252) bounding the asof range to the
  last N trading days from today (TPE timezone).
- Wires the production loader (same call as the FastAPI lifespan).
- Iterates the asof range oldest-to-newest, calling
  `compute_rs_rating(<any_eligible_symbol>, asof)` to trigger a full-universe
  compute and cache write per asof. The chosen trigger symbol is
  implementation-defined but MUST be a symbol stable enough to remain in the
  universe across the full range (e.g., `2330`).
- Prints one line per asof with `asof | universe_size | elapsed_ms` to stdout.
- After the loop, runs `SELECT COUNT(*) FROM rs_rating_cache WHERE asof_date BETWEEN ? AND ?`
  and asserts the count is `>= N * 100` (sanity floor — real value is closer
  to `N * ~1500`). On assertion failure, exits non-zero with the actual count.
- Re-runs over the same range SHALL leave row counts unchanged and update
  only `computed_at` (driven by `INSERT OR REPLACE` semantics already in
  `_write_cache`).

#### Scenario: Backfill populates cache for the requested range

- **GIVEN** `rs_rating_cache` is empty
- **AND** today is `2026-05-06`
- **WHEN** `python scripts/backfill_rs_rating.py --days 5` is run
- **THEN** rows exist in `rs_rating_cache` for the 5 most recent trading days
  ending on or before `2026-05-06`
- **AND** stdout shows 5 lines with `asof | universe_size | elapsed_ms`
- **AND** the final row-count check passes (count `>= 500`)
- **AND** the process exit code is `0`

#### Scenario: Re-running backfill is idempotent

- **GIVEN** `rs_rating_cache` already contains rows for the requested range
  from a prior run
- **WHEN** the same backfill command is re-run
- **THEN** the row count for that range is unchanged
- **AND** the `computed_at` column for those rows is updated to a later UTC
  timestamp
- **AND** the process exit code is `0`

#### Scenario: Backfill fails loudly when row-count floor is not met

- **GIVEN** the loader returns an empty dict for every asof (e.g., due to a
  cold `bars_daily` cache and a misconfigured fallback chain)
- **WHEN** `python scripts/backfill_rs_rating.py --days 252` is run
- **THEN** the row-count assertion fails
- **AND** the process exit code is non-zero
- **AND** stderr names the actual count and the expected floor
