# rs-percentile Specification

## Purpose
TBD - created by archiving change rs-percentile-skill. Update Purpose after archive.
## Requirements
### Requirement: RS Rating computed as cross-sectional percentile over weighted multi-period returns

The `compute_rs_rating(symbol, asof)` function SHALL return an integer in `[1, 99]` representing the cross-sectional percentile rank of the symbol's weighted multi-period return across the eligible universe on `asof`, where the weighted score is:

```
score = 0.25 * R63 + 0.25 * R126 + 0.25 * R189 + 0.25 * R252
```

with `Rn = close[asof] / close[asof - n trading days] - 1` (close-to-close, dividend-unadjusted to match FinMind defaults). The percentile rank SHALL be `floor(99 * (rank - 1) / N) + 1` (clamped to `[1, 99]`) where `rank` is 1-indexed from worst to best and `N` is the universe size on `asof`. Ties SHALL receive the lower rank (`method="min"`). This formula is chosen so that the best performer maps to 99, the median to 50, and tied symbols share the same percentile (the floor-and-`+1` shape with denominator `N` rather than the textbook `(rank-1)/(N-1)` keeps the top end at 99 instead of overflowing to 100 in finite universes).

Formula source: `docs/workflow-cheatsheet.md` §RS (4 quarterly returns, equal-weighted; threshold 65 vs IBD 70 because TW liquid universe is ~1500 names vs US ~18000).

#### Scenario: Best performer in universe of 1000 returns 99

- **GIVEN** an eligible universe of 1000 symbols on `asof = 2026-04-30`
- **AND** symbol `2330` has the highest weighted score
- **WHEN** `compute_rs_rating("2330", "2026-04-30")` is called
- **THEN** the result is `99`

#### Scenario: Median performer returns 50

- **GIVEN** an eligible universe of 999 symbols where `2454` is at rank 500 (1-indexed worst-to-best)
- **WHEN** `compute_rs_rating("2454", "2026-04-30")` is called
- **THEN** the result is `50`

#### Scenario: Tied scores receive the lower rank

- **GIVEN** symbols `A` and `B` both have identical weighted scores at rank 700/1000
- **WHEN** `compute_rs_rating` is called for both
- **THEN** both receive the same percentile derived from rank 700 (not 701)

### Requirement: Eligible universe defined by liquidity and listing rules

The eligible universe on `asof` SHALL be all TWSE-listed and OTC-listed common stocks (excluding ETFs, warrants, REITs, and preferred shares) satisfying ALL of:

- Listed (first trade date) on or before `asof - 252 trading days`
- 20-day average dollar volume `mean(close * volume)` over `[asof - 20, asof - 1]` ≥ NT$100,000,000
- Not flagged as 處置股 (disposition) or 全額交割 (full-cash settlement) on `asof`
- Has a valid close on `asof` (not suspended)

Universe membership SHALL be re-evaluated daily; a symbol that drops below NT$100M average dollar volume SHALL be excluded from the next day's calculation.

#### Scenario: Newly listed stock under 252 trading days is excluded

- **GIVEN** symbol `9999` first traded 200 trading days before `asof`
- **WHEN** universe is built for `asof`
- **THEN** `9999` is not in the universe
- **AND** `compute_rs_rating("9999", asof)` returns `None`

#### Scenario: Stock with 20d avg dollar volume below NT$100M is excluded

- **GIVEN** symbol `1234` has 20-day average dollar volume of NT$80,000,000 on `asof`
- **WHEN** universe is built
- **THEN** `1234` is not in the universe
- **AND** `compute_rs_rating("1234", asof)` returns `None`

#### Scenario: Disposition-flagged stock is excluded

- **GIVEN** symbol `5678` is on the TWSE 處置 list on `asof`
- **WHEN** universe is built
- **THEN** `5678` is not in the universe even if liquid

### Requirement: RS Rating returns None for ineligible or unknown symbols

`compute_rs_rating(symbol, asof)` SHALL return `None` (not raise) when the symbol is not in the eligible universe on `asof`, including when the symbol is unknown, suspended, or fails any membership rule. Callers (e.g., `evaluate_trend_template`) rely on `None` to drive the tri-state c8 path.

#### Scenario: Unknown symbol

- **WHEN** `compute_rs_rating("0000", "2026-04-30")` is called for an unknown ticker
- **THEN** the result is `None`
- **AND** no exception is raised

#### Scenario: Suspended on asof

- **GIVEN** symbol `2317` is suspended for the trading session on `2026-04-30`
- **WHEN** `compute_rs_rating("2317", "2026-04-30")` is called
- **THEN** the result is `None`

### Requirement: Mansfield RS line computed against TWII benchmark

The `compute_rs_line(symbol, asof, benchmark="^TWII", lookback=252)` function SHALL return an `RsLineResult` with:

- `series: list[float]` — daily Mansfield RS values over the lookback window, defined as `RS_t = (close_symbol_t / close_benchmark_t) / SMA52w(close_symbol / close_benchmark) - 1` where `SMA52w` is the 252-day simple moving average of the price ratio
- `slope_20d: float` — least-squares slope of `series[-20:]` (units: RS-per-day)
- `at_52w_high: bool` — `True` iff `series[-1] >= max(series)` (today's RS line at a 52-week high within the lookback window)
- `benchmark_used: str` — the actual benchmark symbol used (e.g., `"^TWII"`)

The function SHALL raise `InsufficientHistoryError` when the symbol or benchmark has fewer than `lookback + 252` bars available (need 252 extra for the SMA warmup).

#### Scenario: RS line at new 52-week high

- **GIVEN** 504 bars where symbol outperforms TWII monotonically over the last year
- **WHEN** `compute_rs_line(symbol, asof)` is called
- **THEN** `result.at_52w_high` is `True`
- **AND** `result.slope_20d > 0`

#### Scenario: Insufficient history raises typed error

- **GIVEN** symbol `9999` with only 300 bars of history
- **WHEN** `compute_rs_line("9999", asof, lookback=252)` is called
- **THEN** `InsufficientHistoryError` is raised
- **AND** the message names the actual bar count (300) and required count (504)

### Requirement: RS Rating cached daily in SQLite

Each call to `compute_rs_rating` SHALL first read from a SQLite table `rs_rating_cache` keyed by `(asof_date, symbol)`. On cache miss for a given `asof_date`, the implementation SHALL compute the entire universe in one batch and persist all rows transactionally. Subsequent calls for the same `asof_date` SHALL be served from cache.

The cache schema SHALL be:

```sql
CREATE TABLE rs_rating_cache (
  asof_date TEXT NOT NULL,        -- ISO YYYY-MM-DD
  symbol TEXT NOT NULL,
  rs_rating INTEGER NOT NULL,     -- 1..99
  universe_size INTEGER NOT NULL,
  computed_at TEXT NOT NULL,      -- ISO 8601 UTC
  PRIMARY KEY (asof_date, symbol)
);
CREATE INDEX idx_rs_rating_asof ON rs_rating_cache(asof_date);
```

#### Scenario: First call for an asof_date triggers full universe compute

- **GIVEN** the `rs_rating_cache` has no rows for `asof_date = 2026-04-30`
- **WHEN** `compute_rs_rating("2330", "2026-04-30")` is called
- **THEN** the universe is computed and all rows for `2026-04-30` are inserted in one transaction
- **AND** the result for `2330` is returned

#### Scenario: Second call for same asof_date hits cache

- **GIVEN** `rs_rating_cache` has rows for `asof_date = 2026-04-30`
- **WHEN** `compute_rs_rating("2454", "2026-04-30")` is called
- **THEN** the value is read from cache without recomputing the universe
- **AND** no FinMind/Shioaji bulk fetch is issued

### Requirement: Public function exposes RS Rating to callers

`compute_rs_rating(symbol: str, asof: str | date) -> int | None` SHALL be the canonical public entrypoint for all callers (screener, LLM Decider, `evaluate_trend_template` consumers, and the 7-pt sub-scorer in `scoring.subscorers.rs_percentile`). All callers SHALL share the same SQLite cache by going through this function — no parallel formula or cache.

A tool-registry wrapper (e.g. `market_data_tool.get_rs_percentile`) is **deferred** until a tool registry exists in `src/ohmystock`; standing one up just for this single consumer is pre-emptive abstraction.

#### Scenario: compute_rs_rating returns int for eligible symbol

- **GIVEN** symbol `2330` is in the eligible universe on `2026-04-30`
- **WHEN** `compute_rs_rating("2330", "2026-04-30")` is called
- **THEN** the result is an `int` in `[1, 99]`

#### Scenario: compute_rs_rating returns None for ineligible symbol

- **GIVEN** symbol `9999` is not in the eligible universe
- **WHEN** `compute_rs_rating("9999", "2026-04-30")` is called
- **THEN** the result is `None`

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

### Requirement: Disposition list interface and cache table ship; live TWSE/OTC scrape is deferred

`fetch_disposition_set(asof: date) -> set[str]` SHALL be the single producer
of the `disposition_set` argument used by the universe-closes loader. The
`disposition_list_cache(asof_date TEXT, symbol TEXT, fetched_at TEXT, PRIMARY KEY (asof_date, symbol))`
table SHALL exist with `asof_date` ISO `YYYY-MM-DD` and `fetched_at` ISO 8601 UTC.

`fetch_disposition_set` SHALL:

- On a cache hit for `asof`, return the cached set without further work.
- On a cache miss, return `set()` and SHALL NOT raise. **In this change**, no
  upstream scrape is attempted — the function is a stub that exists so the
  rest of the wiring (loader filter, lifespan default, backfill) can be built
  against a stable interface. A follow-up change `rs-percentile-disposition-scrape-impl`
  SHALL replace the stub with TWSE 處置股 + OTC 全額交割 scraping plus
  graceful-degrade-to-last-known-set; that follow-up MUST preserve the
  no-raise contract documented here.

The function SHALL NOT raise under any condition reachable in this change.

#### Scenario: Cache hit returns cached set

- **GIVEN** `disposition_list_cache` has rows `{"5678", "1234"}` for
  `asof_date = "2026-04-30"`
- **WHEN** `fetch_disposition_set("2026-04-30")` is called
- **THEN** the result is `{"5678", "1234"}`

#### Scenario: Cache miss returns empty set without raising

- **GIVEN** `disposition_list_cache` has no rows for `asof_date = "2026-04-30"`
- **WHEN** `fetch_disposition_set("2026-04-30")` is called
- **THEN** the result is `set()`
- **AND** no exception propagates to the caller

#### Scenario: Cache table exists with documented schema

- **WHEN** `init_schema(conn)` is called on a fresh SQLite connection
- **THEN** the `disposition_list_cache` table exists
- **AND** its primary key is `(asof_date, symbol)`

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
- Re-runs over the same range SHALL leave the row count unchanged
  (`compute_rs_rating` short-circuits on cache hit before any write).

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
- **AND** the process exit code is `0`

#### Scenario: Backfill fails loudly when row-count floor is not met

- **GIVEN** the loader returns an empty dict for every asof (e.g., due to a
  cold `bars_daily` cache and a misconfigured fallback chain)
- **WHEN** `python scripts/backfill_rs_rating.py --days 252` is run
- **THEN** the row-count assertion fails
- **AND** the process exit code is non-zero
- **AND** stderr names the actual count and the expected floor

