## 1. Universe-closes loader

- [x] 1.1 Add `src/ohmystock/sepa/rs_loader.py` with `build_universe_closes_loader(conn=None, *, disposition_fetcher=None, history_calendar_days=520)`. Closure: read symbols from `universe_daily` (`screener.cache.select_universe_rows`); per symbol read trailing closes from `bars_daily` (`data.cache.select_bars`) within `[asof-520d, asof]`; drop symbols with `< 253` closes; apply optional disposition filter. Read-only — no `FinMindClient` calls. Spec drift: signature accepts `conn=None` (opens via `api.db.get_connection` per call) so production wiring is no-arg; tests pass an in-memory conn for fast assertions.
- [x] 1.2 Resolved: `bars_daily` is **read-only via `select_bars`** — no lazy-fill. The canonical producer is `data.market_data.get_kline()` (cache-first; missing dates trigger FinMind/twstock/yfinance fallback + `insert_bars`). Loader stays read-only by design; cold cache → empty dict → backfill script (§4, Batch 2) warms via `get_kline(sym, bars=520)` per universe symbol. No loader-side fetch needed.
- [x] 1.3 Wired the loader in `src/ohmystock/api/app.py` via an `@asynccontextmanager`-decorated `_lifespan(app)`: calls `set_universe_closes_loader(build_universe_closes_loader())` at startup, `reset_providers()` in `finally` at shutdown. `FastAPI(...)` now receives `lifespan=_lifespan`. Loader closure manages its own per-call DB connection (Decision 4 of design.md), so the lifespan itself holds no conn.
- [x] 1.4 Unit tests `tests/test_sepa_rs_loader.py` — 6 tests covering: liquid symbol with 260 bars → ≥253-element list in result; 100-bar symbol omitted; empty `universe_daily` for asof → `{}`; disposition fetcher excludes flagged symbol; `FinMindClient.__init__` patched to raise — loader still succeeds (no FinMind call); provided conn not closed by the loader. Full pytest suite green: 903 passed (was 897 + 6 new).

## 2. Disposition-list interface (stub) — Path B

- [x] 2.1 Added `src/ohmystock/data/disposition.py` with idempotent `init_schema(conn)` creating `disposition_list_cache(asof_date TEXT, symbol TEXT, fetched_at TEXT, PRIMARY KEY (asof_date, symbol))` and `_read_cached_set(conn, asof_iso) -> set[str]` helper.
- [x] 2.2 ~~Read TWSE 處置股 page and OTC 全額交割 list with typed `DispositionScrapeError`~~ — **DEFERRED to follow-up `rs-percentile-disposition-scrape-impl`**. URL/HTML/JSON shapes need live verification that this session can't perform; spec explicitly permits a stub initial impl that does not scrape.
- [x] 2.3 Implemented `fetch_disposition_set(asof: date|str, *, conn=None) -> set[str]`: cache hit → cached set; cache miss → `set()` (stub). Never raises. Auto-init's the schema on first call, so callers don't need a setup step.
- [x] 2.4 ~~Graceful-degrade with `try/except (httpx.HTTPError, DispositionScrapeError)` plus last-known-set fallback~~ — **DEFERRED with §2.2**. The no-raise contract is preserved by the stub (always returns `set()` on miss); the follow-up wraps the real scrape in the same shape.
- [x] 2.5 `tests/test_disposition.py` — 6 tests: `init_schema` creates table with composite PK and 3 NOT NULL columns; idempotent re-init; cache hit returns cached set; cache miss returns `set()` (no raise); accepts `str` or `date` arg shape; auto-creates table when called on a virgin conn.

## 3. Wire disposition into the loader path

- [x] 3.1 Wired `fetch_disposition_set` into the `_lifespan` startup of `api/app.py`: `set_universe_closes_loader(build_universe_closes_loader(disposition_fetcher=fetch_disposition_set))`. `build_universe_closes_loader` (already shipped in 1.1) accepts the kwarg; default stays `None` so non-FastAPI callers / unit tests don't drag in `data.disposition`. Backfill script wires the same way via `wire_production_loader()`.
- [x] 3.2 Disposition exclusion verified by `tests/test_sepa_rs_loader.py::test_disposition_filter_excludes_flagged_symbol` (loader-level) and the E2E lifespan-wiring test in `tests/test_rs_percentile_e2e.py` (production wiring path).

## 4. Backfill script

- [x] 4.1 Added `scripts/backfill_rs_rating.py` with `argparse` `--days N` (default 252), `wire_production_loader()` helper (mirrors `api.app._lifespan`), `run_backfill(days, today, conn)` for testable invocation, and `main(argv)` entrypoint with non-positive-days rejection.
- [x] 4.2 `_walk_back_business_days(today, days)` walks Mon–Fri only (no holiday subtraction), oldest-to-newest. Holiday no-ops surface as empty universe rows, which the row-count floor accommodates.
- [x] 4.3 Inside single owned conn, loops asofs and calls `compute_rs_rating("2330", asof, conn=c)`. Prints `f"{asof.isoformat()} | {universe_size} | {elapsed_ms}ms"` per day; `universe_size` read back from `rs_rating_cache` count for that asof.
- [x] 4.4 After loop, `SELECT COUNT(*) FROM rs_rating_cache WHERE asof_date BETWEEN ? AND ?`; below `days * 100` floor → stderr `FAIL: ... expected >= N` + return code `1`. On success: stdout `OK: N rows in [first, last] (floor F)`.
- [x] 4.5 `tests/test_backfill_rs_rating.py` — 6 tests across `TestRunBackfill` (happy path 5 days × 150 symbols → 750 rows + zero exit + stdout shape; idempotent re-run keeps 750 rows; empty-loader floor failure → exit 1 + stderr shape), `TestWalkBackBusinessDays` (skips weekends; ascending order), `TestMainCli` (argparse rejects `--days 0` with exit 2). Spec scenario amended: idempotent re-run keeps row count (no `computed_at` rewrite — `compute_rs_rating` short-circuits on cache hit before reaching `_write_cache`).

## 5. End-to-end smoke + closeout

- [x] 5.1 `tests/test_rs_percentile_e2e.py` — 2 tests: (a) `TestClient(create_app())` lifespan installs `_universe_closes_loader` (was None → not None) and unwires it on exit; healthz route serves 200 inside the context; (b) inside the lifespan context, swapping in a 150-symbol stub loader yields `compute_rs_rating("2330", 2026-04-30) == int in [1, 99]` and 151 cached rows for the asof.
- [x] 5.2 `openspec validate rs-percentile-finmind-wiring --strict` — passes.
- [x] 5.3 Full `pytest` suite — 917 passed (was 903 + 6 disposition + 6 backfill + 2 E2E).
- [ ] 5.4 Run `python scripts/backfill_rs_rating.py --days 5` against the local DB once — **deferred to user**: requires live FinMind sponsored-member access + populated `bars_daily` cache that this implementation session cannot exercise. Spec's no-raise + floor-failure paths are unit-test-covered so a real run will surface real env state cleanly.
- [ ] 5.5 Add CLAUDE.md §5 SSOT row pointing at `openspec/specs/rs-percentile/spec.md（archive 後）+ src/ohmystock/sepa/rs.py + src/ohmystock/sepa/rs_loader.py + src/ohmystock/data/disposition.py + scripts/backfill_rs_rating.py` — done at archive time per established repo pattern.
