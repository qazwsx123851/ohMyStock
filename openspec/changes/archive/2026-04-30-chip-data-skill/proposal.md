## Why

Phase 1 路線圖明列「技術 / **籌碼面** Skills + 回測引擎」，目前技術指標與回測引擎已交付，但籌碼面是空的。Phase 2 的 screener、Phase 2B 的 candidate snapshot（評分權重 45%）、Phase 3 的 LLM Decider 都需要三大法人 / 融資融券資料才能跑得起來。先把最常用的兩個籌碼資料端點（三大法人、融資融券）以純函式 + 標準 envelope 落地，並沿用 `bars_daily` 同款 SQLite cache 模式；其餘籌碼端點（借券、分點、個股期 OI）留待後續 change。

## What Changes

- 新增 `ohmystock.chip` 套件，提供兩個純函式 skill 入口：
  - `get_three_major_investors(symbol, days=30, end_date=None)` — 外資 / 投信 / 自營商（避險＋自行合計）日淨買賣（張）
  - `get_margin_short(symbol, days=30, end_date=None)` — 融資餘額 / 融券餘額 / 券資比
- 兩個函式皆回標準 envelope `{ok, elapsed_ms, data, error}`，error code 與 `market_data_cache` 對齊（`INVALID_INPUT` / `DATA_UNAVAILABLE` / `RATE_LIMIT` / `UPSTREAM_ERROR` / `AUTH_FAILED`）。
- 新增 SQLite cache：`chip_three_major_daily`、`chip_margin_short_daily`，兩張表皆 `(symbol, date)` PK，cache-first / source fallback 流程同 `market_data.get_kline`。
- 擴充 `FinMindClient`，新增 `get_institutional_investors_buy_sell(symbol, start, end)` 與 `get_margin_purchase_short_sale(symbol, start, end)` 兩個 thin REST wrapper（dataset：`TaiwanStockInstitutionalInvestorsBuySell`、`TaiwanStockMarginPurchaseShortSale`）。
- 對齊 `docs/tools-contracts.md` §3 chip_data_tool 的 row schema；不一致以本 proposal 為準並回頭修正 docs。

範圍排除（留給後續 change）：`get_securities_lending`、`get_top_brokers`、`get_stock_futures_oi`、Tool 層註冊（`@register_tool`）、screener 整合。

## Capabilities

### New Capabilities
- `chip-data-skill`: 籌碼面（三大法人、融資融券）純函式 fetcher + SQLite cache + 標準 envelope。

### Modified Capabilities
（無；本 change 不改既有 capability 的 requirement。）

## Impact

- **新增**：`src/ohmystock/chip/{__init__.py,three_major.py,margin_short.py,cache.py}`、`tests/test_chip_*.py`。
- **修改**：`src/ohmystock/data/finmind_client.py`（新增兩個 wrapper method）。
- **依賴**：沿用既有 `httpx`、`sqlite3`；無新外部套件。
- **DB schema**：在現有 `ohmystock_db_path` 之 SQLite DB 新增兩張 cache 表，IF NOT EXISTS 安全。
- **預算**：FinMind 籌碼 API 屬贊助會員（NT$2,000/年，docs `design-zh-TW.md` §5.1 已列入）；本 change 不改變預算結構。
- **反向依賴**：禁止 `ohmystock.chip` import `ohmystock.api`（與 backtest 同樣的 reverse-import 防線）。
