## 1. FinMind client extension

- [x] 1.1 Add `get_institutional_investors_buy_sell(symbol, start, end)` to `FinMindClient` (dataset `TaiwanStockInstitutionalInvestorsBuySell`)
- [x] 1.2 Add `get_margin_purchase_short_sale(symbol, start, end)` to `FinMindClient` (dataset `TaiwanStockMarginPurchaseShortSale`)
- [x] 1.3 Write `tests/test_finmind_client_chip.py` covering: dataset param correctness, HTTP 500 → `FinMindConnectionError`, missing `data` list → `FinMindConnectionError`, optional token forwarding

## 2. Chip cache schema

- [x] 2.1 Create `src/ohmystock/chip/__init__.py` (empty)
- [x] 2.2 Create `src/ohmystock/chip/cache.py` with `init_chip_schema(conn)`, both DDL constants, idempotent migration in single transaction
- [x] 2.3 Add `aggregate_three_major(raw_rows: list[dict]) -> list[dict]` in `src/ohmystock/chip/cache.py` (pure function, sorted by date asc)
- [x] 2.4 Add `insert_three_major_rows(conn, normalised_rows, source, fetched_at)` and `select_three_major_rows(conn, symbol, start, end)`
- [x] 2.5 Add `insert_margin_short_rows(conn, raw_rows, source, fetched_at)` (computes `short_to_margin_ratio` at write) and `select_margin_short_rows(conn, symbol, start, end)`
- [x] 2.6 Write `tests/test_chip_cache.py` — schema idempotency, aggregator coverage (multiple legs / missing leg / multiple dates), ratio formula incl. zero-margin guard, INSERT OR IGNORE behaviour

## 3. Public skill — three major investors

- [x] 3.1 Create `src/ohmystock/chip/three_major.py` with `get_three_major_investors(symbol, days=30, end_date=None, *, _conn=None, _client=None)`
- [x] 3.2 Implement input validation matching spec (symbol regex `^\d{4,6}$`, days `1..5000`, end_date `YYYY-MM-DD` or None)
- [x] 3.3 Implement business-day range computation (Mon–Fri, walking back from `end_date`)
- [x] 3.4 Implement cache-first / fetch-missing flow + classify FinMind exceptions (reuse pattern from `market_data._classify_exception`)
- [x] 3.5 Implement shares→張 conversion at response boundary (`shares // 1000`)
- [x] 3.6 Write `tests/test_chip_three_major.py` — cache full hit (no client call), partial miss (narrow fetch range), full miss empty upstream → `DATA_UNAVAILABLE`, INVALID_INPUT cases, RATE_LIMIT/AUTH_FAILED/UPSTREAM_ERROR classification, shares→張 boundary conversion

## 4. Public skill — margin / short

- [x] 4.1 Create `src/ohmystock/chip/margin_short.py` with `get_margin_short(symbol, days=30, end_date=None, *, _conn=None, _client=None)`
- [x] 4.2 Implement same validation + business-day range as three_major (extract shared helpers if cleaner)
- [x] 4.3 Implement cache-first / fetch-missing flow; raw FinMind rows pass through `insert_margin_short_rows` (no aggregation needed — one row per symbol per date)
- [x] 4.4 Write `tests/test_chip_margin_short.py` — full hit, partial miss, full miss empty upstream, INVALID_INPUT, error classification, ratio surfaced unchanged from cache

## 5. Reverse-import guard

- [x] 5.1 Write `tests/test_chip_reverse_import.py` — subprocess imports `ohmystock.chip` (and submodules) and asserts `fastapi`, `uvicorn`, `starlette` not in `sys.modules`

## 6. Validation

- [x] 6.1 Run `pytest tests/test_chip_*.py tests/test_finmind_client_chip.py -v` — all pass
- [x] 6.2 Run `pytest` (full suite) — no regressions in existing tests
- [x] 6.3 Run `openspec validate chip-data-skill --strict` — clean
