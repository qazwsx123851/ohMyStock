## 1. FinMind client wrapper

- [x] 1.1 Add `get_taiwan_stock_info() -> list[dict]` to `FinMindClient` (dataset `TaiwanStockInfo`, no symbol/date filter; reuse `_fetch_dataset` style — adjust if `_fetch_dataset` signature requires symbol)
- [x] 1.2 Write `tests/test_finmind_client_universe.py` covering: dataset param correctness, HTTP 500 → `FinMindConnectionError`, missing `data` key → `FinMindConnectionError`, optional token forwarding

## 2. SQLite cache layer

- [x] 2.1 Create `src/ohmystock/screener/__init__.py` (empty) and `src/ohmystock/screener/cache.py`
- [x] 2.2 Add `init_universe_schema(conn)` with `CREATE TABLE IF NOT EXISTS universe_daily (...)` per spec — full DDL (PK `(asof_date, symbol)`, market/name/industry/4 flags/source/fetched_at)
- [x] 2.3 Add `aggregate_universe_rows(raw_rows: list[dict], asof_date: str) -> list[dict]` (pure function: maps `type` `twse`/`tpex` → `market` `'TWSE'`/`'OTC'`; derives `is_ky` from `stock_id` ending in `"KY"`; flags `is_warning`/`is_disposal`/`is_fully_paid` always 0; sorts by symbol asc)
- [x] 2.4 Add `insert_universe_rows(conn, normalised_rows, source, fetched_at)` (batched insert with `INSERT OR IGNORE`)
- [x] 2.5 Add `select_universe_rows(conn, asof_date, market_filter)` (returns rows ordered by symbol)
- [x] 2.6 Add `latest_asof_within(conn, target_date, lookback_days=30)` returning the most recent `asof_date` ≤ `target_date` with rows, else `None`
- [x] 2.7 Write `tests/test_screener_cache.py` — schema idempotency, aggregator coverage (TWSE / OTC mapping, KY suffix true/false, multi-row sort), `INSERT OR IGNORE` behaviour, `latest_asof_within` exact / fallback / no-row-in-window cases

## 3. Filter module

- [x] 3.1 Create `src/ohmystock/screener/filters.py`
- [x] 3.2 Add `apply_negative_filter(rows: list[dict], exclude: list[str]) -> list[dict]` — translate `"warning"`/`"disposal"`/`"fully_paid"`/`"KY"` to flag columns, drop rows whose flag is `1`; raise `ValueError` on unknown flag (caught by `screen_universe` and surfaced as `INVALID_INPUT`)
- [x] 3.3 Add `apply_volume_filter(rows, conn, min_avg, asof_date_used, error_policy="skip_missing") -> list[dict]` — for each row, query `bars_daily` for the 5 most recent rows with `date <= asof_date_used`; if fewer than 5, apply `error_policy`; else compute avg `amount`, drop if `< min_avg`; raise `ValueError("data unavailable")` on `fail_fast` with insufficient bars
- [x] 3.4 Write `tests/test_screener_filters.py` — KY drop, unknown-flag rejection (raises), volume filter below/above threshold, missing-bars `skip_missing` drops symbol, missing-bars `fail_fast` raises, spy assertion that `apply_volume_filter` does NOT call `get_kline`

## 4. Public entrypoint

- [x] 4.1 Create `src/ohmystock/screener/universe.py` with `screen_universe(universe, custom_symbols=None, filters=None, asof_date=None, *, _conn=None, _client=None) -> dict`
- [x] 4.2 Implement input validation per spec (`universe` whitelist, `custom_symbols` regex `^\d{4,6}(KY)?$` + non-empty, `asof_date` `YYYY-MM-DD` parseable, `filters` list of dicts with whitelisted `kind`)
- [x] 4.3 Implement asof_date resolution: caller value → today TPE → `latest_asof_within` 30-day fallback → cache miss + client fetch + write-through → `DATA_UNAVAILABLE`
- [x] 4.4 Implement universe selector (TWSE / OTC / TWSE+OTC / custom intersection)
- [x] 4.5 Apply filters in declaration order; map `ValueError` from filter helpers to `INVALID_INPUT` / `DATA_UNAVAILABLE` per filter contract
- [x] 4.6 Build envelope: `data = {"asof_date_used": <str>, "candidates": [{symbol, name, sector, market}, ...]}` sorted by symbol asc; `elapsed_ms` measured with `time.perf_counter()`
- [x] 4.7 Reuse FinMind exception classifier (mirror pattern from `chip.three_major._classify_exception` — extract to a shared helper in `screener/universe.py` or duplicate inline; do NOT cross-import `chip` internals)
- [x] 4.8 Write `tests/test_screener_universe.py` — exact-day cache hit, weekend fallback, cache-miss-with-client write-through, cache-miss-without-client `DATA_UNAVAILABLE`, custom universe intersection, KY exclusion, all `INVALID_INPUT` cases, upstream `httpx.ConnectError` → `UPSTREAM_ERROR` envelope (no exception escapes)

## 5. Reverse-import guard

- [x] 5.1 Write `tests/test_screener_reverse_import.py` — subprocess imports `ohmystock.screener` (and submodules `cache`, `filters`, `universe`) and asserts `fastapi`, `uvicorn`, `starlette` not in `sys.modules`

## 6. Validation

- [x] 6.1 Run `pytest tests/test_screener_*.py tests/test_finmind_client_universe.py -v` — all pass
- [x] 6.2 Run `pytest` (full suite) — no regressions in existing 179 tests
- [x] 6.3 Run `openspec validate change screener-tw-universe --strict` — clean
