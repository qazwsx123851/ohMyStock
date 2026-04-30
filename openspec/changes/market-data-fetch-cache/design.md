## Context

`FinMindClient` from `external-connectors-and-cost` is a thin wrapper that calls one FinMind endpoint and returns its raw payload — no caching, no fallback, no envelope. Phase 1 needs to start writing technical-indicator skills, the screener, and the backtest engine, all of which loop over the same symbols' daily K many times. Without a layer in front of FinMind we will (a) burn FinMind's quota replaying the same dates during development, (b) be one upstream outage away from a stuck pipeline, and (c) leak provider-specific error types into every caller.

This change builds that layer. The contract target is `market_data_tool.get_kline(...)` from `docs/tools-contracts.md` §1, scoped tightly to **daily** OHLCV.

## Goals / Non-Goals

**Goals:**
- Single function `get_kline(symbol, period="1d", bars=250, end_date=None)` returning the `{ok, elapsed_ms, data, error}` envelope from `tools-contracts.md` §0.1.
- Cache hit on second call for the same `(symbol, date)` range — no upstream traffic.
- Provider failure is recoverable without code changes by callers — fallback chain is internal.
- Error envelope only; no upstream exception types (`httpx.HTTPError`, `yfinance` exceptions, etc.) leak out.
- Idempotent schema init that coexists with `journal_entries` / `llm_costs` from the previous change.
- Test coverage that exercises cache-hit, gap-fill, every fallback tier, and every error code.

**Non-Goals:**
- Intraday bars (`1m/5m/15m/60m`) — `INVALID_INPUT` for now; deferred to a later change once a real intraday consumer exists.
- Real-time `get_quote` — Shioaji path already exists for that and is real-time, not cacheable.
- Computed metrics (`get_index`, `get_rs_percentile`, `get_stage`, `get_trend_template`, `get_post_exit_returns`) — these belong in their own skill changes that consume `get_kline`, not here.
- Parquet partitioning — premature at single-user scale.
- `universe` table / handling 處置股 / 警示股 / KY 股 metadata — separate change.
- MOPS scraper, TWSE OpenAPI — `tools-contracts.md` mentions a longer fallback chain; we keep the chain at three providers for MVP.
- Async API surface — `get_kline` is sync. Async wrappers can be added later if a caller actually needs them.

## Decisions

### D1. SQLite single table over Parquet partitioning

Use one SQLite table `bars_daily` with PK `(symbol, date)` instead of monthly Parquet partitions.

**Why:** Solo dev, single user, single machine. SQLite already hosts `journal_entries`, `llm_costs`, and `memory`. One file, one connection pool, one backup target. Parquet is the right call when scans go to billions of rows or when you fan out to a dataframe engine; we are nowhere near that. `docs/design-zh-TW.md` §5.3 mentions Parquet but that's aspirational — we deferred it explicitly in `proposal.md` Impact / Out of scope.

**Alternative considered:** Per-month Parquet files under `data/cache/bars/{symbol}/{YYYY-MM}.parquet`. Rejected: forces a parquet reader dep into every consumer (or another translation layer), and the SQLite table on a single user's daily K through 10 years × 2000 symbols is < 200 MB — fine.

### D2. Fallback chain order: FinMind → twstock → yfinance

**Why this order:**
- **FinMind first** — primary paid source, has the deepest TW history, has the chip-flow data Phase 1 籌碼面 will need next, and we already pay for the sponsor tier. Most calls should hit and stop here.
- **twstock second** — scrapes TWSE/OTC directly, no auth needed, TW-native (correct symbol semantics, correct trading calendar). Best fallback when FinMind is rate-limited or down.
- **yfinance last** — global, but TW symbol mapping requires `.TW` / `.TWO` suffixes and the data is delayed/wrong-corp-action edge cases are real. Use only when the first two have both failed.

**Alternative considered:** TWSE OpenAPI in front of twstock. Rejected for MVP: another adapter to write/maintain, and twstock already wraps TWSE under the hood. Add later if twstock proves flaky.

### D3. Cache-first with gap-fill, not full-range replace

On a request for `(symbol, last 250 trading days ending end_date)`:
1. Compute the requested business-day range using the TW trading calendar (twstock provides one; otherwise approximate by skipping weekends — covered in tasks).
2. Query `bars_daily` for that `(symbol, date)` range; collect the missing dates.
3. If missing dates form a contiguous tail or gap, ask the first available adapter for that gap only.
4. Insert with `INSERT OR IGNORE` and re-query.

**Why:** Avoids re-fetching the same history on every call during indicator/backtest development. The expensive case (cold-start full year on a new symbol) happens once per symbol.

**Trade-off:** A buggy or wrong row in the cache is sticky. Mitigation: `source` column records which adapter wrote it; a one-line `DELETE FROM bars_daily WHERE source=?` is the rollback.

### D4. Error envelope translation, no exception leak

`get_kline` ALWAYS returns `{ok, elapsed_ms, data, error}`. Internal exceptions are caught at the boundary and translated:

| Exception | Code | Retriable |
|---|---|---|
| Pydantic validation on inputs | `INVALID_INPUT` | false |
| Empty result from all adapters | `DATA_UNAVAILABLE` | false |
| FinMind 429 / explicit quota text | `RATE_LIMIT` | true |
| Any adapter HTTP 5xx / timeout | `UPSTREAM_ERROR` | true |
| FinMind 401/403 | `AUTH_FAILED` | false |

Adapters themselves still raise typed exceptions (e.g. existing `FinMindConnectionError`); the boundary in `market_data.py` is the only place that catches and translates.

### D5. `DataSource` Protocol, not ABC

```python
class DataSource(Protocol):
    name: str  # "finmind" | "twstock" | "yfinance"
    def fetch_daily(self, symbol: str, start: str, end: str) -> list[BarRow]: ...
```

**Why Protocol over ABC:** Existing `FinMindClient` already exists with its own constructor — we don't want to force inheritance. Protocol lets us write thin adapter modules that wrap each provider's idiomatic API without coupling them.

### D6. Schema init lives next to journal schema

`init_market_data_schema(conn)` in `src/ohmystock/data/cache.py`, called the same way `init_schema` is called in journal. Both are idempotent (`CREATE TABLE IF NOT EXISTS`). No migration framework — solo dev, schema changes are commits.

## Risks / Trade-offs

- **[Risk] FinMind sponsor token leaking into yfinance/twstock paths** → Mitigation: each adapter is its own module with its own dependencies; only the FinMind adapter touches `Settings().finmind_token`.
- **[Risk] yfinance silently returns wrong data for TW symbols (e.g. `2330` not suffixed)** → Mitigation: yfinance adapter prepends `.TW` for TWSE / `.TWO` for OTC based on a lookup; if neither yields data the adapter raises and the chain returns `DATA_UNAVAILABLE`. Test covers a representative TWSE and OTC symbol.
- **[Risk] Cache returns stale data after a corporate action (split / dividend)** → Mitigation: out of scope for MVP — flagged in spec scenarios and tracked as follow-up. Manual `DELETE FROM bars_daily WHERE symbol=?` is the workaround.
- **[Risk] Trading calendar drift causes us to ask for a non-trading day and treat it as a gap forever** → Mitigation: only treat a date as "missing" if upstream succeeded and returned no row for it; record an explicit "no-trade" sentinel via excluded set in the in-memory request, not the DB.
- **[Trade-off] Sync API** → If a future consumer needs concurrent fetches, we wrap with `asyncio.to_thread`. Cheaper than committing to async now and rewriting if assumptions change.
- **[Trade-off] No request coalescing** → Two simultaneous calls for the same `(symbol, range)` will both hit upstream the first time. Acceptable at single-user scale.
