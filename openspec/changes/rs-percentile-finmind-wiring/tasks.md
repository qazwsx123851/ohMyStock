## 1. Universe-closes loader

- [x] 1.1 Add `src/ohmystock/sepa/rs_loader.py` with `build_universe_closes_loader(conn=None, *, disposition_fetcher=None, history_calendar_days=520)`. Closure: read symbols from `universe_daily` (`screener.cache.select_universe_rows`); per symbol read trailing closes from `bars_daily` (`data.cache.select_bars`) within `[asof-520d, asof]`; drop symbols with `< 253` closes; apply optional disposition filter. Read-only — no `FinMindClient` calls. Spec drift: signature accepts `conn=None` (opens via `api.db.get_connection` per call) so production wiring is no-arg; tests pass an in-memory conn for fast assertions.
- [x] 1.2 Resolved: `bars_daily` is **read-only via `select_bars`** — no lazy-fill. The canonical producer is `data.market_data.get_kline()` (cache-first; missing dates trigger FinMind/twstock/yfinance fallback + `insert_bars`). Loader stays read-only by design; cold cache → empty dict → backfill script (§4, Batch 2) warms via `get_kline(sym, bars=520)` per universe symbol. No loader-side fetch needed.
- [x] 1.3 Wired the loader in `src/ohmystock/api/app.py` via an `@asynccontextmanager`-decorated `_lifespan(app)`: calls `set_universe_closes_loader(build_universe_closes_loader())` at startup, `reset_providers()` in `finally` at shutdown. `FastAPI(...)` now receives `lifespan=_lifespan`. Loader closure manages its own per-call DB connection (Decision 4 of design.md), so the lifespan itself holds no conn.
- [x] 1.4 Unit tests `tests/test_sepa_rs_loader.py` — 6 tests covering: liquid symbol with 260 bars → ≥253-element list in result; 100-bar symbol omitted; empty `universe_daily` for asof → `{}`; disposition fetcher excludes flagged symbol; `FinMindClient.__init__` patched to raise — loader still succeeds (no FinMind call); provided conn not closed by the loader. Full pytest suite green: 903 passed (was 897 + 6 new).

## 2. Disposition-list scraper

- [ ] 2.1 Add `src/ohmystock/data/disposition.py` with idempotent `init_schema(conn)` creating `disposition_list_cache(asof_date TEXT, symbol TEXT, fetched_at TEXT, PRIMARY KEY (asof_date, symbol))` (mirrors `sepa.rs.init_schema` pattern with `CREATE TABLE IF NOT EXISTS`).
- [ ] 2.2 Read TWSE 處置股 page (HTML table or JSON endpoint — investigate live URL during implementation, document chosen URL in the module docstring) and OTC 全額交割 list. Add a typed `DispositionScrapeError` for parse failures. Keep parsing minimal — extract symbol codes only.
- [ ] 2.3 Implement `fetch_disposition_set(asof: date, *, conn=None) -> set[str]`: cache hit → return; cache miss → scrape both lists, merge, persist (with a sentinel row for the empty-day case to make `set()` distinguishable from cold cache), return.
- [ ] 2.4 Implement graceful degrade: wrap the scrape in try/except `(httpx.HTTPError, DispositionScrapeError)`; on failure, query the most recent `asof_date <= requested` from `disposition_list_cache` and return that set, or `set()` if none. Log warning with the underlying exception.
- [ ] 2.5 Unit tests `tests/test_disposition.py`: (a) cache hit returns cached set without HTTP; (b) cache miss with successful scrape persists rows; (c) cache miss with empty scrape persists sentinel row and a second call hits cache; (d) scrape failure with prior cache returns last-known set; (e) scrape failure with cold cache returns `set()` and logs warning. Use `pytest`'s `respx` or `httpx.MockTransport` for HTTP stubbing.

## 3. Wire disposition into the loader path

- [ ] 3.1 Update the `build_universe_closes_loader` closure (task 1.1) to accept the disposition source as a closure-captured argument: `build_universe_closes_loader(conn, *, disposition_fetcher=fetch_disposition_set)`. The closure calls `disposition_fetcher(asof)` per asof and uses the result to filter the symbol roster before reading bars. (Note: `_build_universe` itself stays pure; the loader does the disposition filter, since the loader is what shapes the dict that `_compute_universe_ratings` sees.)
- [ ] 3.2 Verify spec scenario "Liquid symbol with full history yields an int rating after wiring" passes end-to-end with a fixture that stubs both `universe_daily` and `bars_daily` and a non-empty `disposition_set` that excludes a known symbol; the excluded symbol's `compute_rs_rating` returns `None`.

## 4. Backfill script

- [ ] 4.1 Add `scripts/backfill_rs_rating.py` with `argparse` parsing `--days N` (default 252). Wire the loader same as `app.py` lifespan (extract a shared `wire_rs_loader(conn)` helper if it keeps the duplication tidy; otherwise inline both call sites — duplication of 3 lines is fine per CLAUDE.md §2).
- [ ] 4.2 Compute the asof range: starting from today (TPE timezone), walk backwards N trading days. Use a simple business-day step (Mon–Fri) and accept that holidays will land on a closed market — the loader returns an empty dict for those days, which the row-count floor accounts for.
- [ ] 4.3 Loop oldest-to-newest, calling `compute_rs_rating("2330", asof)` per asof inside a single connection. Print `f"{asof} | {universe_size} | {elapsed_ms}ms"` after each.
- [ ] 4.4 After the loop, `SELECT COUNT(*) FROM rs_rating_cache WHERE asof_date BETWEEN ? AND ?`; if `< N * 100`, write the actual count + expected floor to stderr and exit non-zero.
- [ ] 4.5 Unit test (or simulator-style integration test) `tests/test_backfill_rs_rating.py`: (a) `--days 5` with a stub loader populates cache and exits 0; (b) re-run with same args is idempotent — same row count, later `computed_at`; (c) loader returning empty dict per asof triggers the floor failure and exits non-zero.

## 5. End-to-end smoke + closeout

- [ ] 5.1 Add `tests/test_rs_percentile_e2e.py`: spin up the FastAPI app via `TestClient`, populate fixture rows in `universe_daily` and `bars_daily` for `2330` over 260 trading days, call `compute_rs_rating("2330", fixture_asof)` after the lifespan has run, assert the result is an `int` in `[1, 99]` and no `RuntimeError`. Resets state with `reset_providers()` in teardown.
- [ ] 5.2 Run `openspec validate rs-percentile-finmind-wiring --strict` — must pass.
- [ ] 5.3 Run full `pytest` suite — must stay green (currently 897 passing).
- [ ] 5.4 Run `python scripts/backfill_rs_rating.py --days 5` against the local DB once to smoke-test the script end-to-end (will warm 5 days of cache); record `universe_size` per day in the PR/commit message for a sanity check.
- [ ] 5.5 Add a row to CLAUDE.md §5 SSOT table for `rs-percentile` pointing at `openspec/specs/rs-percentile/spec.md（archive 後）+ src/ohmystock/sepa/rs.py + src/ohmystock/sepa/rs_loader.py + src/ohmystock/data/disposition.py` once this change archives.
