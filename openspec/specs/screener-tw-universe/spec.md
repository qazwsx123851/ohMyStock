# screener-tw-universe Specification

## Purpose
TBD - created by archiving change screener-tw-universe. Update Purpose after archive.

## Requirements

### Requirement: Public entrypoint returns standard envelope

The system SHALL expose a pure function `screen_universe(universe: str, custom_symbols: list[str] | None = None, filters: list[dict] | None = None, asof_date: str | None = None, *, _conn=None, _client=None) -> dict` in `ohmystock.screener`. It SHALL return the standard envelope `{"ok": bool, "elapsed_ms": int, "data": <payload> | None, "error": {"code": str, "message": str, "retriable": bool} | None}`. On success `error` SHALL be `None`; on failure `data` SHALL be `None` and `error.code` SHALL be one of `INVALID_INPUT`, `DATA_UNAVAILABLE`, `RATE_LIMIT`, `UPSTREAM_ERROR`, `AUTH_FAILED`. The function MUST NOT raise to its caller for any expected failure mode (bad input, empty universe, upstream HTTP error).

On success, `data` SHALL contain the keys `{asof_date_used: str (YYYY-MM-DD), candidates: list[{symbol: str, name: str, sector: str, market: str}]}`. `candidates` SHALL be sorted ascending by `symbol`.

#### Scenario: Success returns envelope with candidates

- **GIVEN** `universe_daily` is pre-populated with 3 rows for 2026-04-30 (TWSE: 2330, 2454; OTC: 6488)
- **WHEN** `screen_universe("TWSE+OTC", asof_date="2026-04-30")` is called
- **THEN** the return value SHALL satisfy `result["ok"] is True`, `result["error"] is None`, `result["data"]["asof_date_used"] == "2026-04-30"`, and `[c["symbol"] for c in result["data"]["candidates"]] == ["2330", "2454", "6488"]`

#### Scenario: Empty universe returns success with empty list

- **GIVEN** `universe_daily` has rows for 2026-04-30 but every TWSE row is filtered out
- **WHEN** `screen_universe("TWSE", filters=[{"kind": "negative_filter", "exclude": ["KY"]}], asof_date="2026-04-30")` is called and every row has `is_ky=1`
- **THEN** `result["ok"] is True` and `result["data"]["candidates"] == []`

#### Scenario: Upstream raises is caught

- **GIVEN** a FinMind client whose `get_taiwan_stock_info()` raises `httpx.ConnectError("boom")`
- **WHEN** `screen_universe("TWSE", asof_date="2026-04-30")` is called against an empty cache
- **THEN** `result["ok"] is False`, `result["data"] is None`, `result["error"]["code"] == "UPSTREAM_ERROR"`, `result["error"]["retriable"] is True`, and no exception SHALL escape

---

### Requirement: Input validation

`screen_universe` SHALL validate inputs before any cache or network access:

- `universe` MUST be one of `{"TWSE","OTC","TWSE+OTC","custom"}`.
- When `universe == "custom"`, `custom_symbols` MUST be a non-empty list of strings each matching `^\d{4,6}(KY)?$`.
- When `universe != "custom"`, `custom_symbols` MUST be `None` (or absent).
- `asof_date` MUST be `None` or match `YYYY-MM-DD` and parse as a real calendar date.
- `filters`, when present, MUST be a list whose elements are dicts with a `kind` key in `{"negative_filter","volume_filter"}`. Unknown `kind` SHALL be `INVALID_INPUT`.

Validation failures SHALL produce `error.code == "INVALID_INPUT"` with `retriable=False`.

#### Scenario: Unknown universe rejected

- **WHEN** `screen_universe("US")` is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

#### Scenario: Custom universe missing symbols rejected

- **WHEN** `screen_universe("custom", custom_symbols=None)` is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

#### Scenario: Custom universe with bad symbol rejected

- **WHEN** `screen_universe("custom", custom_symbols=["AAPL"])` is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

#### Scenario: Unknown filter kind rejected

- **WHEN** `screen_universe("TWSE", filters=[{"kind": "trend_template_filter"}])` is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

#### Scenario: Malformed asof_date rejected

- **WHEN** `screen_universe("TWSE", asof_date="2026/04/30")` is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

---

### Requirement: SQLite cache schema for universe snapshot

The system SHALL define a SQLite table `universe_daily` with columns `asof_date TEXT NOT NULL` (`YYYY-MM-DD`), `symbol TEXT NOT NULL`, `market TEXT NOT NULL` (`'TWSE'` or `'OTC'`), `name TEXT NOT NULL`, `industry TEXT NOT NULL DEFAULT ''`, `is_warning INTEGER NOT NULL DEFAULT 0`, `is_disposal INTEGER NOT NULL DEFAULT 0`, `is_fully_paid INTEGER NOT NULL DEFAULT 0`, `is_ky INTEGER NOT NULL DEFAULT 0`, `source TEXT NOT NULL`, `fetched_at TEXT NOT NULL` (ISO-8601 with `+08:00` offset), and `PRIMARY KEY (asof_date, symbol)`.

The system SHALL provide `init_universe_schema(conn: sqlite3.Connection) -> None` that creates the table idempotently using `CREATE TABLE IF NOT EXISTS`.

In this change, `is_warning`, `is_disposal`, and `is_fully_paid` SHALL always be written as `0` because no data source is wired yet. `is_ky` SHALL be `1` when `symbol` ends with `"KY"` (case-sensitive), else `0`.

#### Scenario: Schema created on empty DB

- **WHEN** `init_universe_schema(conn)` is called on an empty SQLite connection
- **THEN** `conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()` SHALL contain `"universe_daily"`

#### Scenario: Schema is idempotent

- **WHEN** `init_universe_schema(conn)` is called twice in succession
- **THEN** no exception SHALL be raised and the table count SHALL be unchanged

#### Scenario: KY flag derived from symbol suffix

- **GIVEN** raw FinMind row `{"stock_id": "9105KY", "stock_name": "泰金寶-DR", "industry_category": "Other Electronic", "type": "twse"}`
- **WHEN** the row is normalised by `aggregate_universe_rows([row], asof_date="2026-04-30")`
- **THEN** the resulting row SHALL have `is_ky == 1`

#### Scenario: Non-KY row has is_ky=0

- **GIVEN** raw FinMind row `{"stock_id": "2330", "stock_name": "台積電", "industry_category": "Semiconductor", "type": "twse"}`
- **WHEN** the row is normalised
- **THEN** the resulting row SHALL have `is_ky == 0`

---

### Requirement: Cache-first universe resolution with asof_date fallback

`screen_universe` SHALL resolve `asof_date` as follows:

1. If caller provides `asof_date`, use it as-is.
2. If `asof_date is None`, default to today in `Asia/Taipei` (UTC+08:00).
3. If `universe_daily` has no row matching the resolved `asof_date`, fall back to the most recent `asof_date` strictly less than the requested one (within 30 calendar days).
4. If no row is found within the 30-day window, AND no FinMind client is available (or it returns empty), return `error.code == "DATA_UNAVAILABLE"`.
5. If no row is found and the FinMind client is available, fetch via `get_taiwan_stock_info()` for the resolved date and write through the cache before continuing.

The resolved date SHALL be returned as `data.asof_date_used`.

#### Scenario: Exact-day cache hit uses requested date

- **GIVEN** `universe_daily` has rows for 2026-04-30 (TPE business day)
- **WHEN** `screen_universe("TWSE", asof_date="2026-04-30")` is called
- **THEN** `result["data"]["asof_date_used"] == "2026-04-30"` and no FinMind call SHALL be made

#### Scenario: Weekend fallback to most recent cache day

- **GIVEN** `universe_daily` has rows for 2026-04-30 (Thursday) but none for 2026-05-02 (Saturday)
- **WHEN** `screen_universe("TWSE", asof_date="2026-05-02")` is called
- **THEN** `result["ok"] is True`, `result["data"]["asof_date_used"] == "2026-04-30"`, and no FinMind call SHALL be made

#### Scenario: Cache miss with client triggers fetch and write-through

- **GIVEN** `universe_daily` is empty and a FinMind client returning 3 stocks for 2026-04-30 is provided via `_client`
- **WHEN** `screen_universe("TWSE+OTC", asof_date="2026-04-30")` is called
- **THEN** `result["ok"] is True`, `result["data"]["asof_date_used"] == "2026-04-30"`, and `universe_daily` SHALL contain 3 rows for 2026-04-30 after the call

#### Scenario: Cache miss without client returns DATA_UNAVAILABLE

- **GIVEN** `universe_daily` is empty and no FinMind client is wired
- **WHEN** `screen_universe("TWSE", asof_date="2026-04-30")` is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "DATA_UNAVAILABLE"`

---

### Requirement: Universe selectors

The system SHALL support four `universe` selector values, each filtering `universe_daily` rows for the resolved `asof_date_used` as follows:

- `"TWSE"` SHALL return rows where `market == 'TWSE'`.
- `"OTC"` SHALL return rows where `market == 'OTC'`.
- `"TWSE+OTC"` SHALL return all rows (both markets).
- `"custom"` SHALL filter rows to symbols in `custom_symbols` (intersection); symbols in `custom_symbols` not present in the snapshot SHALL be silently dropped.

#### Scenario: TWSE selector excludes OTC

- **GIVEN** `universe_daily` has 2330 (TWSE) and 6488 (OTC) for 2026-04-30
- **WHEN** `screen_universe("TWSE", asof_date="2026-04-30")` is called
- **THEN** `[c["symbol"] for c in result["data"]["candidates"]] == ["2330"]`

#### Scenario: Custom universe filters to provided symbols

- **GIVEN** `universe_daily` has 2330, 2454, 6488 for 2026-04-30
- **WHEN** `screen_universe("custom", custom_symbols=["2330", "9999"], asof_date="2026-04-30")` is called
- **THEN** `[c["symbol"] for c in result["data"]["candidates"]] == ["2330"]`

---

### Requirement: Negative filter excludes flagged rows

When a filter dict `{"kind": "negative_filter", "exclude": [<flag>...]}` is applied, the system SHALL drop rows whose corresponding flag column is `1`. Recognised flag values: `"warning"` → `is_warning`, `"disposal"` → `is_disposal`, `"fully_paid"` → `is_fully_paid`, `"KY"` → `is_ky`. Unknown flag values SHALL produce `INVALID_INPUT`.

In this change `is_warning`, `is_disposal`, `is_fully_paid` are always `0`; only `"KY"` exclusion has observable effect.

#### Scenario: KY exclusion drops KY symbols

- **GIVEN** `universe_daily` has rows for 2330 (`is_ky=0`) and 9105KY (`is_ky=1`) on 2026-04-30
- **WHEN** `screen_universe("TWSE+OTC", filters=[{"kind": "negative_filter", "exclude": ["KY"]}], asof_date="2026-04-30")` is called
- **THEN** `[c["symbol"] for c in result["data"]["candidates"]] == ["2330"]`

#### Scenario: Unknown exclude flag rejected

- **WHEN** `screen_universe("TWSE", filters=[{"kind": "negative_filter", "exclude": ["foo"]}])` is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

---

### Requirement: Volume filter uses bars_daily, never fetches

When a filter dict `{"kind": "volume_filter", "min_avg_dollar_volume_5d": <int>}` is applied, the system SHALL compute each candidate's 5-business-day average of `bars_daily.amount` (NT$) ending at `asof_date_used` (inclusive), and drop rows whose average is strictly less than `min_avg_dollar_volume_5d`.

The system SHALL NOT call `get_kline()` or any FinMind endpoint to backfill missing bars while applying this filter. Behaviour on insufficient bars (fewer than 5 rows in `bars_daily` for the symbol within the window) SHALL be controlled by an optional `error_policy` filter key:

- `"skip_missing"` (default): drop the symbol from candidates.
- `"fail_fast"`: abort the whole call with `error.code == "DATA_UNAVAILABLE"`.

#### Scenario: Below threshold dropped

- **GIVEN** `bars_daily` has 5 rows for 2330 with `amount` summing to 4 × 10⁸ over the 5 days (avg 8 × 10⁷) ending 2026-04-30
- **WHEN** `screen_universe("TWSE", filters=[{"kind": "volume_filter", "min_avg_dollar_volume_5d": 100_000_000}], asof_date="2026-04-30")` is called
- **THEN** `2330` SHALL NOT appear in `result["data"]["candidates"]`

#### Scenario: Above threshold kept

- **GIVEN** `bars_daily` has 5 rows for 2330 with `amount` summing to 6 × 10⁸ over the 5 days (avg 1.2 × 10⁸) ending 2026-04-30
- **WHEN** the same call as above is made
- **THEN** `2330` SHALL appear in `result["data"]["candidates"]`

#### Scenario: Missing bars with default policy skips symbol

- **GIVEN** `bars_daily` has only 2 rows for 2330 in the window ending 2026-04-30
- **WHEN** `screen_universe("TWSE", filters=[{"kind": "volume_filter", "min_avg_dollar_volume_5d": 100_000_000}], asof_date="2026-04-30")` is called (no `error_policy` key)
- **THEN** `2330` SHALL NOT appear in `result["data"]["candidates"]` and `result["ok"] is True`

#### Scenario: Missing bars with fail_fast aborts

- **GIVEN** `bars_daily` has only 2 rows for 2330 in the window
- **WHEN** the same call adds `"error_policy": "fail_fast"` to the filter dict
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "DATA_UNAVAILABLE"`

#### Scenario: volume_filter does not call get_kline

- **GIVEN** a spy wrapping `ohmystock.data.market_data.get_kline`
- **WHEN** any `screen_universe(...)` invocation is made with a `volume_filter`
- **THEN** the spy SHALL record zero calls

---

### Requirement: FinMind client wrapper for TaiwanStockInfo

`FinMindClient` SHALL expose `get_taiwan_stock_info() -> list[dict]` that calls the `TaiwanStockInfo` dataset with no symbol or date filter. On HTTP non-2xx, missing `data` key, or non-list `data`, the wrapper SHALL raise `FinMindConnectionError` (matching existing wrapper semantics).

Each row returned SHALL contain at minimum the keys `{stock_id: str, stock_name: str, industry_category: str, type: str}` where `type ∈ {"twse","tpex"}` (mapped to `market` `'TWSE'`/`'OTC'` at the cache boundary).

#### Scenario: Wrapper invokes correct dataset

- **WHEN** `FinMindClient().get_taiwan_stock_info()` is called against a stub that asserts the dataset parameter
- **THEN** the captured `params["dataset"]` SHALL equal `"TaiwanStockInfo"`

#### Scenario: HTTP 500 raises FinMindConnectionError

- **GIVEN** a transport returning HTTP 500
- **WHEN** `FinMindClient().get_taiwan_stock_info()` is called
- **THEN** the call SHALL raise `FinMindConnectionError`

#### Scenario: Missing data key raises

- **GIVEN** a transport returning `{"status": 200, "msg": "ok"}` (no `data`)
- **WHEN** the wrapper is called
- **THEN** the call SHALL raise `FinMindConnectionError`

---

### Requirement: Reverse-import isolation

The `ohmystock.screener` package and its submodules SHALL NOT import `ohmystock.api`, `fastapi`, `uvicorn`, or `starlette` at module load time.

#### Scenario: Subprocess import does not load FastAPI

- **WHEN** a subprocess runs `python -c "import ohmystock.screener; import sys; assert 'fastapi' not in sys.modules and 'uvicorn' not in sys.modules and 'starlette' not in sys.modules"`
- **THEN** the subprocess SHALL exit with code 0
