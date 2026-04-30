## ADDED Requirements

### Requirement: Public entrypoints return standard envelope

The system SHALL expose two pure functions in `ohmystock.chip`:

- `get_three_major_investors(symbol: str, days: int = 30, end_date: str | None = None) -> dict`
- `get_margin_short(symbol: str, days: int = 30, end_date: str | None = None) -> dict`

Both functions SHALL return the standard envelope `{"ok": bool, "elapsed_ms": int, "data": <payload> | None, "error": {"code": str, "message": str, "retriable": bool} | None}`. On success `error` SHALL be `None`; on failure `data` SHALL be `None` and `error.code` SHALL be one of `INVALID_INPUT`, `DATA_UNAVAILABLE`, `RATE_LIMIT`, `UPSTREAM_ERROR`, `AUTH_FAILED`. Neither function SHALL raise to the caller for any expected failure mode (bad input, empty data, upstream HTTP error, JSON parse error).

`end_date` defaults to today in TPE timezone (`Asia/Taipei`, UTC+08:00) when `None`. Both functions SHALL return data for the most recent `days` business days (Mon–Fri) ending at `end_date` inclusive, in ascending date order.

#### Scenario: get_three_major_investors success returns envelope with rows

- **WHEN** `get_three_major_investors("2330", days=5, end_date="2026-04-29")` is called against a cache pre-populated for 2330 covering the requested range
- **THEN** the return value SHALL satisfy `result["ok"] is True`, `result["error"] is None`, `isinstance(result["elapsed_ms"], int)`, `isinstance(result["data"]["rows"], list)`, and every row SHALL have keys `{date, foreign_net, invest_trust_net, prop_dealer_net}` with `date` matching `YYYY-MM-DD`

#### Scenario: get_margin_short success returns envelope with rows

- **WHEN** `get_margin_short("2330", days=5, end_date="2026-04-29")` is called against a cache pre-populated for 2330 covering the requested range
- **THEN** the return value SHALL satisfy `result["ok"] is True`, `result["error"] is None`, and every row SHALL have keys `{date, margin_balance, margin_change, short_balance, short_change, short_to_margin_ratio}`

#### Scenario: Upstream HTTPError is caught and surfaced

- **GIVEN** a FinMind client that raises `httpx.ConnectError("boom")` on call
- **WHEN** either chip function is called with a cache miss covering the full range
- **THEN** the return value SHALL satisfy `result["ok"] is False`, `result["data"] is None`, `result["error"]["code"] == "UPSTREAM_ERROR"`, `result["error"]["retriable"] is True`, and no exception SHALL escape the call

---

### Requirement: Input validation

Both chip functions SHALL validate inputs before any cache or network access. `symbol` MUST be a string of 4–6 ASCII digits. `days` MUST be a positive int with `1 <= days <= 5000`. `end_date` MUST be `None` or match `YYYY-MM-DD` and parse as a real calendar date. Validation failures SHALL produce `error.code == "INVALID_INPUT"` with `retriable=False`.

#### Scenario: Invalid symbol rejected

- **WHEN** `get_three_major_investors("AAPL", days=30)` is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

#### Scenario: Non-positive days rejected

- **WHEN** `get_margin_short("2330", days=0)` is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

#### Scenario: Malformed end_date rejected

- **WHEN** `get_three_major_investors("2330", days=30, end_date="2026/04/29")` is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "INVALID_INPUT"`

---

### Requirement: SQLite cache schema for three major investors

The system SHALL define a SQLite table `chip_three_major_daily` with columns `symbol TEXT NOT NULL`, `date TEXT NOT NULL` (`YYYY-MM-DD`), `foreign_net INTEGER NOT NULL`, `invest_trust_net INTEGER NOT NULL`, `prop_dealer_net INTEGER NOT NULL`, `source TEXT NOT NULL`, `fetched_at TEXT NOT NULL` (ISO-8601 with `+08:00` offset), and `PRIMARY KEY (symbol, date)`. The system SHALL provide `init_chip_schema(conn: sqlite3.Connection) -> None` that creates this table idempotently using `CREATE TABLE IF NOT EXISTS`. `prop_dealer_net` SHALL be the **sum** of dealer-hedge and dealer-self-trade legs reported by FinMind (avoid mixing units across rows).

Net values SHALL be stored in **shares**, not 張 — the public function SHALL convert to 張 (`shares // 1000`) at the response boundary so cache integrity does not depend on a unit assumption.

#### Scenario: Schema created on empty DB

- **WHEN** `init_chip_schema(conn)` is called on an empty SQLite connection
- **THEN** `conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()` SHALL contain `"chip_three_major_daily"`

#### Scenario: Repeat call is idempotent

- **WHEN** `init_chip_schema(conn)` is called twice in succession on the same connection
- **THEN** no exception SHALL be raised and the table count SHALL be unchanged

#### Scenario: Public function returns 張 not shares

- **GIVEN** a cache row with `foreign_net = 12_400_000` (shares)
- **WHEN** `get_three_major_investors("2330", days=1, end_date=<row date>)` is called
- **THEN** the response row SHALL have `foreign_net == 12400` (張)

---

### Requirement: SQLite cache schema for margin/short

The system SHALL define a SQLite table `chip_margin_short_daily` with columns `symbol TEXT NOT NULL`, `date TEXT NOT NULL` (`YYYY-MM-DD`), `margin_balance INTEGER NOT NULL`, `margin_change INTEGER NOT NULL`, `short_balance INTEGER NOT NULL`, `short_change INTEGER NOT NULL`, `short_to_margin_ratio REAL NOT NULL`, `source TEXT NOT NULL`, `fetched_at TEXT NOT NULL`, and `PRIMARY KEY (symbol, date)`. `init_chip_schema(conn)` SHALL create this table in the same call as the three-major table, in a single transaction.

`short_to_margin_ratio` SHALL equal `short_balance / margin_balance * 100.0` when `margin_balance > 0`, else `0.0`. The ratio SHALL be computed at write time and stored, not recomputed on read.

`margin_balance`, `margin_change`, `short_balance`, `short_change` SHALL be stored in **張** (FinMind's native unit for `TaiwanStockMarginPurchaseShortSale`); no unit conversion is required at the response boundary for this table.

#### Scenario: Schema created on empty DB

- **WHEN** `init_chip_schema(conn)` is called on an empty SQLite connection
- **THEN** `sqlite_master` SHALL contain both `"chip_three_major_daily"` and `"chip_margin_short_daily"`

#### Scenario: short_to_margin_ratio computed at write time

- **GIVEN** a row to insert with `margin_balance = 100_000`, `short_balance = 4_200`
- **WHEN** the row is inserted via the cache helper
- **THEN** the stored `short_to_margin_ratio` SHALL equal `4.2`

#### Scenario: short_to_margin_ratio safe when margin_balance is zero

- **GIVEN** a row with `margin_balance = 0`, `short_balance = 100`
- **WHEN** the row is inserted via the cache helper
- **THEN** the stored `short_to_margin_ratio` SHALL equal `0.0` (no `ZeroDivisionError`)

---

### Requirement: Cache-first fetch with FinMind fallback

Each chip function SHALL follow this sequence: (1) compute the requested business-day range from `end_date` and `days`; (2) read existing rows from the cache for `symbol` within that range; (3) compute the missing date set; (4) if missing is non-empty, call the corresponding `FinMindClient` method for `[missing[0], missing[-1]]`, insert returned rows into the cache (`INSERT OR IGNORE`) tagged `source="finmind"` and `fetched_at=<now TPE iso>`; (5) re-read the cache and return all rows in ascending date order. Bars present in cache SHALL NOT trigger a network call.

If FinMind returns an empty list and no cached row covers the range, the function SHALL return `error.code == "DATA_UNAVAILABLE"` with `retriable=False`.

#### Scenario: Full cache hit avoids network

- **GIVEN** a cache pre-populated for 2330 covering all 5 requested business days
- **WHEN** `get_three_major_investors("2330", days=5, end_date="2026-04-29")` is called with an injected FinMind client whose method raises if invoked
- **THEN** `result["ok"] is True`, `result["data"]["rows"]` has length 5, and the FinMind client SHALL NOT have been invoked

#### Scenario: Partial cache miss triggers narrow fetch

- **GIVEN** a cache holding rows for the first 3 of 5 requested business days
- **WHEN** `get_margin_short(...)` is called with an injected FinMind client returning the missing 2 days
- **THEN** the FinMind client SHALL have been called exactly once with `start = <day 4>` and `end = <day 5>`, and the final response SHALL contain all 5 rows in ascending date order

#### Scenario: Empty upstream + empty cache yields DATA_UNAVAILABLE

- **GIVEN** no cached rows for the requested range and a FinMind client returning `[]`
- **WHEN** either chip function is called
- **THEN** `result["ok"] is False` and `result["error"]["code"] == "DATA_UNAVAILABLE"` with `retriable=False`

---

### Requirement: HTTP error classification

When the underlying `FinMindClient` raises an exception, the chip function SHALL classify the error into the standard envelope codes by inspecting the lowercased exception message:

- Contains `"429"`, `"quota"`, or `"rate limit"` → `RATE_LIMIT`, `retriable=True`
- Contains `"401"`, `"403"`, `"unauthorized"`, or `"forbidden"` → `AUTH_FAILED`, `retriable=False`
- Anything else → `UPSTREAM_ERROR`, `retriable=True`

This classifier SHALL be reused (or re-implemented identically) from `ohmystock.data.market_data._classify_exception` to keep behaviour consistent across data fetchers.

#### Scenario: 429 mapped to RATE_LIMIT

- **GIVEN** a FinMind client raising `RuntimeError("FinMind returned HTTP 429 Too Many Requests")`
- **WHEN** either chip function is called with a full cache miss
- **THEN** `result["error"]["code"] == "RATE_LIMIT"` and `result["error"]["retriable"] is True`

#### Scenario: 401 mapped to AUTH_FAILED

- **GIVEN** a FinMind client raising `RuntimeError("FinMind returned HTTP 401 unauthorized")`
- **WHEN** either chip function is called with a full cache miss
- **THEN** `result["error"]["code"] == "AUTH_FAILED"` and `result["error"]["retriable"] is False`

---

### Requirement: FinMind client adds two dataset wrappers

The system SHALL extend `ohmystock.data.finmind_client.FinMindClient` with two methods that mirror the existing `get_taiwan_stock_price` shape:

- `get_institutional_investors_buy_sell(symbol: str, start: str, end: str) -> list[dict[str, Any]]` — calls FinMind dataset `TaiwanStockInstitutionalInvestorsBuySell`
- `get_margin_purchase_short_sale(symbol: str, start: str, end: str) -> list[dict[str, Any]]` — calls FinMind dataset `TaiwanStockMarginPurchaseShortSale`

Both methods SHALL raise `FinMindConnectionError` on connection failure, non-2xx HTTP status, JSON parse failure, or missing `data` list — same contract as `get_taiwan_stock_price`. Both methods SHALL pass `Settings().finmind_token` when present.

#### Scenario: institutional method hits expected dataset

- **WHEN** `FinMindClient().get_institutional_investors_buy_sell("2330", "2026-04-01", "2026-04-29")` is called against a stubbed `httpx.Client`
- **THEN** the issued GET request SHALL have query param `dataset=TaiwanStockInstitutionalInvestorsBuySell`, `data_id=2330`, `start_date=2026-04-01`, `end_date=2026-04-29`

#### Scenario: margin method hits expected dataset

- **WHEN** `FinMindClient().get_margin_purchase_short_sale("2330", "2026-04-01", "2026-04-29")` is called against a stubbed `httpx.Client`
- **THEN** the issued GET request SHALL have query param `dataset=TaiwanStockMarginPurchaseShortSale`

#### Scenario: HTTP 500 raises FinMindConnectionError

- **GIVEN** a stubbed `httpx.Client` returning HTTP 500
- **WHEN** either new method is called
- **THEN** `FinMindConnectionError` SHALL be raised with the status code in the message

---

### Requirement: Three-major investor row normalisation

The chip cache writer for `chip_three_major_daily` SHALL accept a raw FinMind row (one record per `data_id` per `name` per `date`) and SHALL aggregate by `(symbol, date)` such that:

- `foreign_net` = sum of rows whose `name` starts with `Foreign_Investor` (covers `Foreign_Investor` and `Foreign_Dealer_Self`) — the **`buy - sell`** net in shares
- `invest_trust_net` = row whose `name == "Investment_Trust"` net (shares)
- `prop_dealer_net` = sum of rows whose `name` starts with `Dealer_` (covers `Dealer_self` and `Dealer_Hedging`) net (shares)

Missing legs SHALL contribute zero rather than raising. The aggregator SHALL be a pure function `aggregate_three_major(raw_rows: list[dict]) -> list[dict]` taking FinMind rows and returning one normalised row per `(symbol, date)` keyed by `{symbol, date, foreign_net, invest_trust_net, prop_dealer_net}`.

#### Scenario: Multiple legs aggregated into one row

- **GIVEN** raw FinMind rows for 2330 on 2026-04-29 with `Foreign_Investor buy=10_000_000 sell=2_000_000`, `Dealer_self buy=500_000 sell=300_000`, `Dealer_Hedging buy=100_000 sell=50_000`, `Investment_Trust buy=1_500_000 sell=300_000`
- **WHEN** `aggregate_three_major(raw_rows)` is called
- **THEN** the result SHALL contain exactly one row with `foreign_net == 8_000_000`, `invest_trust_net == 1_200_000`, `prop_dealer_net == 250_000`

#### Scenario: Missing leg contributes zero

- **GIVEN** raw FinMind rows for 2330 on 2026-04-29 containing only `Foreign_Investor` legs
- **WHEN** `aggregate_three_major(raw_rows)` is called
- **THEN** the result row SHALL have `invest_trust_net == 0` and `prop_dealer_net == 0`

---

### Requirement: No FastAPI / API-layer reverse import

The `ohmystock.chip` package SHALL NOT import anything from `ohmystock.api`. Importing the chip layer alone SHALL NOT pull in FastAPI / Starlette / Uvicorn.

#### Scenario: Chip modules import without FastAPI

- **WHEN** a fresh subprocess runs `python -c "import ohmystock.chip, ohmystock.chip.three_major, ohmystock.chip.margin_short, ohmystock.chip.cache"`
- **THEN** the process SHALL exit 0 and `sys.modules` SHALL NOT contain any of `fastapi`, `uvicorn`, `starlette`
