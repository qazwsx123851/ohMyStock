## ADDED Requirements

### Requirement: Standard envelope from `get_kline`

The system SHALL expose `ohmystock.data.market_data.get_kline(symbol: str, period: str = "1d", bars: int = 250, end_date: str | None = None)` that returns a dict matching the standard tool envelope: `{"ok": bool, "elapsed_ms": int, "data": <payload> | None, "error": {"code": str, "message": str, "retriable": bool} | None}`. On success `error` SHALL be `None`; on failure `data` SHALL be `None` and `error.code` SHALL be one of `INVALID_INPUT`, `DATA_UNAVAILABLE`, `RATE_LIMIT`, `UPSTREAM_ERROR`, `AUTH_FAILED`. The function MUST NOT raise to its caller for any provider/network failure.

#### Scenario: Success returns envelope with bars

- **WHEN** `get_kline("2330", period="1d", bars=5, end_date="2026-04-28")` is called and the FinMind adapter is available
- **THEN** the return value SHALL satisfy `result["ok"] is True`, `result["error"] is None`, `isinstance(result["elapsed_ms"], int)`, `len(result["data"]["bars"]) > 0`, and each bar SHALL contain keys `ts, o, h, l, c, v, amount`

#### Scenario: All adapters fail returns envelope with error

- **WHEN** `get_kline("2330")` is called and every adapter raises (mocked)
- **THEN** the return value SHALL satisfy `result["ok"] is False`, `result["data"] is None`, `result["error"]["code"] in {"DATA_UNAVAILABLE", "UPSTREAM_ERROR"}`, and no exception SHALL escape the call

### Requirement: Period restricted to daily for this change

The system SHALL accept only `period="1d"` in this change. Any other value SHALL result in `error.code == "INVALID_INPUT"` with `retriable=False`.

#### Scenario: Intraday period rejected

- **WHEN** `get_kline("2330", period="5m")` is called
- **THEN** the return value SHALL satisfy `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

### Requirement: Input validation

The system SHALL validate inputs before any I/O. `symbol` MUST be a non-empty string of digits 4–6 long (TW spec). `bars` MUST be a positive int ≤ 5000. `end_date` if provided MUST match `YYYY-MM-DD`. Validation failures SHALL produce `error.code == "INVALID_INPUT"`.

#### Scenario: Empty symbol rejected

- **WHEN** `get_kline("", period="1d")` is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

#### Scenario: Malformed end_date rejected

- **WHEN** `get_kline("2330", end_date="2026/04/28")` is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

### Requirement: SQLite cache table `bars_daily`

The system SHALL provide `init_market_data_schema(conn: sqlite3.Connection) -> None` that creates table `bars_daily` with columns `symbol TEXT NOT NULL`, `date TEXT NOT NULL` (ISO-8601 `YYYY-MM-DD`), `o REAL NOT NULL`, `h REAL NOT NULL`, `l REAL NOT NULL`, `c REAL NOT NULL`, `v INTEGER NOT NULL`, `amount INTEGER NOT NULL`, `source TEXT NOT NULL`, `fetched_at TEXT NOT NULL` (ISO-8601 with timezone), PRIMARY KEY `(symbol, date)`. The DDL SHALL use `CREATE TABLE IF NOT EXISTS` and the function SHALL be idempotent (running it twice MUST NOT raise).

#### Scenario: Schema init is idempotent

- **WHEN** `init_market_data_schema(conn)` is called twice on the same in-memory SQLite connection
- **THEN** no exception SHALL be raised, and `SELECT name FROM sqlite_master WHERE type='table' AND name='bars_daily'` SHALL return exactly one row

#### Scenario: Primary key prevents duplicates

- **WHEN** the same `(symbol, date)` row is inserted twice via the cache helper
- **THEN** the second insert SHALL be silently ignored (`INSERT OR IGNORE`) and `SELECT COUNT(*) FROM bars_daily WHERE symbol=? AND date=?` SHALL return `1`

### Requirement: Cache-first read with gap-fill

The system SHALL on every `get_kline` call query `bars_daily` first for the requested `(symbol, date-range)`, identify missing dates, and only fetch the missing range from upstream adapters. Successful upstream rows SHALL be written to `bars_daily` before the function returns.

#### Scenario: Second call hits cache only

- **WHEN** `get_kline("2330", bars=5, end_date="2026-04-28")` is called twice consecutively against an adapter spy
- **THEN** the upstream adapter SHALL be invoked at most once, and both calls SHALL return `result["ok"] is True` with the same `bars`

#### Scenario: Partial cache triggers gap-fetch only

- **GIVEN** `bars_daily` already contains rows for symbol `"2330"` covering `2026-04-21` through `2026-04-25`
- **WHEN** `get_kline("2330", bars=5, end_date="2026-04-28")` is called (which needs `2026-04-21..2026-04-28`, i.e. 5 trading days)
- **THEN** the upstream adapter SHALL be asked for a range whose end is `2026-04-28` and whose start is no earlier than `2026-04-26`, and the final returned `bars` SHALL include data sourced from cache plus the freshly-fetched tail

### Requirement: Fallback chain FinMind → twstock → yfinance

The system SHALL try adapters in fixed order `finmind`, `twstock`, `yfinance`. If an adapter raises or returns an empty list for the requested range, the next adapter SHALL be tried. The first adapter that returns a non-empty result wins; rows written to cache SHALL record `source = <adapter name>`. If all three fail with non-rate-limit errors, the envelope SHALL be `error.code == "DATA_UNAVAILABLE"`.

#### Scenario: FinMind fails, twstock succeeds

- **GIVEN** the FinMind adapter raises `FinMindConnectionError` and the twstock adapter returns 5 rows
- **WHEN** `get_kline("2330", bars=5, end_date="2026-04-28")` is called
- **THEN** `result["ok"] is True`, the cached rows SHALL have `source == "twstock"`, and the yfinance adapter SHALL NOT be called

#### Scenario: All adapters fail with empty results

- **GIVEN** every adapter returns an empty list (no data for the symbol/date)
- **WHEN** `get_kline("9999", bars=5)` is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "DATA_UNAVAILABLE"`

### Requirement: Error code mapping

The system SHALL map adapter exceptions and HTTP states to envelope error codes per the table in design.md §D4.

#### Scenario: FinMind 429 maps to RATE_LIMIT

- **GIVEN** the FinMind adapter raises an exception whose message contains `429` or `quota`
- **AND** twstock and yfinance also fail
- **WHEN** `get_kline("2330")` is called
- **THEN** `result["error"]["code"] == "RATE_LIMIT"` and `result["error"]["retriable"] is True`

#### Scenario: FinMind 401 maps to AUTH_FAILED

- **GIVEN** the FinMind adapter raises an exception whose message contains `401`
- **AND** subsequent adapters raise generic upstream errors
- **WHEN** `get_kline("2330")` is called
- **THEN** `result["error"]["code"]` SHALL be `"AUTH_FAILED"` (FinMind's classification wins) with `retriable=False`

#### Scenario: Generic 5xx maps to UPSTREAM_ERROR

- **GIVEN** every adapter raises an exception classified as 5xx / timeout
- **WHEN** `get_kline("2330")` is called
- **THEN** `result["error"]["code"] == "UPSTREAM_ERROR"` and `result["error"]["retriable"] is True`

### Requirement: `DataSource` protocol

The system SHALL define `class DataSource(Protocol)` in `ohmystock.data.sources.base` with attribute `name: str` and method `fetch_daily(self, symbol: str, start: str, end: str) -> list[BarRow]`, where `BarRow` is a `TypedDict` with keys `ts, o, h, l, c, v, amount`. Concrete adapters SHALL be importable as `ohmystock.data.sources.{finmind,twstock,yfinance}` and each MUST be constructable with no required arguments other than what `Settings()` provides.

#### Scenario: Each adapter implements the protocol structurally

- **WHEN** `from ohmystock.data.sources.finmind import FinMindSource; from ohmystock.data.sources.twstock import TwstockSource; from ohmystock.data.sources.yfinance import YFinanceSource` are imported
- **THEN** each class SHALL expose `name: str` and `fetch_daily(symbol, start, end) -> list[BarRow]` with matching signatures, and constructing each with no arguments SHALL succeed

### Requirement: No reverse-import into FastAPI layer

The data-fetching modules SHALL NOT import anything from `ohmystock.api`, and importing the data layer alone SHALL NOT pull in FastAPI / Starlette / Uvicorn.

#### Scenario: Data modules import without FastAPI

- **WHEN** a fresh subprocess runs `python -c "import ohmystock.data.market_data, ohmystock.data.cache, ohmystock.data.sources.finmind, ohmystock.data.sources.twstock, ohmystock.data.sources.yfinance"`
- **THEN** the process SHALL exit 0 and `sys.modules` SHALL NOT contain any of `fastapi`, `uvicorn`, `starlette`
