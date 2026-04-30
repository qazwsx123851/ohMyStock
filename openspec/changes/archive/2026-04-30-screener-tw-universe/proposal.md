## Why

Phase 2 路線圖第一張票：要把 Phase 1 已落地的 K 線 / 籌碼 / 指標 primitives 串起來成 candidate funnel，得先有「**台股可交易股池**」的權威來源 + 兩道結構性過濾（排除警示 / 流動性門檻）。沒有 universe，後續 Trend Template、Stage、chip、scoring 都沒有迭代對象。本 change 只先把「universe 來源 + 持久化 + 兩道結構性過濾」做成純函式，留 SEPA 漏斗其他層給後續 change（避免一張票塞太大）。

## What Changes

- 新增 `ohmystock.screener` 套件，提供純函式入口：
  - `screen_universe(universe, custom_symbols=None, filters=None, asof_date=None)` — 回標準 envelope，candidates 按 `symbol` 升冪
  - `universe` ∈ `{"TWSE","OTC","TWSE+OTC","custom"}`（不含 `top200` — 需要流動性歷史排名，留待後續 change）
- 新增兩個 filter kind（與 `tools-contracts.md` §4 對齊，scope 只做這兩個）：
  - `negative_filter`：排除全額交割股 / 警示股 / 處置股 / 下市 / KY 股（`exclude` 旗標來自 universe 表欄位）
  - `volume_filter`：依 `min_avg_dollar_volume_5d` 過濾 NT$ ADV，沿用 `bars_daily` cache，不重新抓 K 線
- 標準 envelope `{ok, elapsed_ms, data, error}`，error code 與 `market-data-cache` / `chip-data-skill` 對齊（`INVALID_INPUT` / `DATA_UNAVAILABLE` / `UPSTREAM_ERROR` / `RATE_LIMIT` / `AUTH_FAILED`）。
- 新增 SQLite cache 表 `universe_daily`：每日全市場 snapshot（PK `(asof_date, symbol)`），記 `market`（TWSE / OTC）、`name`、`industry`、四個排除旗標（`is_warning`、`is_disposal`、`is_fully_paid`、`is_ky`）。
- 擴充 `FinMindClient`：新增 `get_taiwan_stock_info()` thin wrapper（dataset `TaiwanStockInfo`），無 symbol / 日期參數，全市場一次拉。

範圍排除（留給後續 change）：
- `trend_template_filter` / `stage_filter` / `chip_filter` / `technical_filter`（需 RS percentile / Stage 邏輯 / 形態偵測）
- `top200` universe + 流動性排名快取
- 評分（`sort_by != "symbol_asc"`）
- `tools-contracts.md` §4 的 `match_layer` / `scores` 欄（本 change 只回 `symbol, name, sector, market`）
- Tool 層註冊（`@register_tool`）
- 警示 / 處置 / 全額交割旗標的 FinMind 端點對接（`TaiwanStockInfo` 沒有；本 change 先預留欄位+寫死 `False`，補資料源是後續 change）

## Capabilities

### New Capabilities
- `screener-tw-universe`: 台股 universe 持久化 + 兩道結構性過濾（純函式 + SQLite cache + 標準 envelope）。

### Modified Capabilities
（無；本 change 不改既有 capability 的 requirement。）

## Impact

- **新增**：`src/ohmystock/screener/{__init__.py,universe.py,cache.py,filters.py}`、`tests/test_screener_*.py`。
- **修改**：`src/ohmystock/data/finmind_client.py`（新增 `get_taiwan_stock_info`）。
- **依賴**：沿用既有 `httpx`、`sqlite3`；無新外部套件。
- **DB schema**：在現有 `ohmystock_db_path` SQLite DB 新增 `universe_daily` 一張表，IF NOT EXISTS 安全。
- **預算**：FinMind `TaiwanStockInfo` 屬基本免費端點，每日全量 1 次呼叫；本 change 不改變預算結構。
- **反向依賴**：禁止 `ohmystock.screener` import `ohmystock.api`（與 chip / backtest 同樣 reverse-import 防線）。
- **Docs SSOT**：本 change 的 envelope 形狀與 `tools-contracts.md` §4 子集對齊；不一致以本 proposal 為準並回頭修正 docs。
