## 1. 依賴與套件設定

- [x] 1.1 在 `pyproject.toml` 的 `[project.dependencies]` 新增 `twstock>=1.3` 與 `yfinance>=0.2`
- [x] 1.2 跑 `uv sync` 更新 `uv.lock`，確認兩個 wheel 在當前 Windows 環境可安裝
- [x] 1.3 跑 `uv run python -c "import twstock, yfinance"` 確認 import 不報錯

## 2. SQLite cache schema (`bars_daily`)

- [x] 2.1 建立 `src/ohmystock/data/cache.py`，實作 `init_market_data_schema(conn)`：建 `bars_daily` 表（10 欄，PK `(symbol, date)`，全 DDL `CREATE TABLE IF NOT EXISTS`，單一 transaction commit）
- [x] 2.2 在同檔加 `insert_bars(conn, rows)` helper，使用 `INSERT OR IGNORE` 批次寫入；`source` / `fetched_at` 由呼叫方填入
- [x] 2.3 在同檔加 `select_bars(conn, symbol, start, end) -> list[BarRow]` 助手，依 `(symbol, date)` 範圍查詢，回傳依日期升序排序的 `BarRow` list
- [x] 2.4 撰寫 `tests/test_market_data_cache.py`：3 個測試（`init` 兩次冪等、PK 防重、`select_bars` 範圍查詢正確）
- [x] 2.5 跑 `uv run pytest tests/test_market_data_cache.py -v` 確認全綠

## 3. `DataSource` Protocol 與 base types

- [x] 3.1 建立 `src/ohmystock/data/sources/__init__.py`（空）
- [x] 3.2 建立 `src/ohmystock/data/sources/base.py`，定義 `BarRow(TypedDict)`（7 欄：ts/o/h/l/c/v/amount）與 `class DataSource(Protocol)`（屬性 `name: str`、方法 `fetch_daily(symbol, start, end) -> list[BarRow]`）
- [x] 3.3 撰寫 `tests/test_data_source_protocol.py`：1 個測試（dummy class 實作 protocol 後 `isinstance(obj, DataSource)` 為真，需用 `runtime_checkable`）
- [x] 3.4 跑 `uv run pytest tests/test_data_source_protocol.py -v`

## 4. FinMind adapter

- [x] 4.1 建立 `src/ohmystock/data/sources/finmind.py`，實作 `class FinMindSource`（`name = "finmind"`），constructor 內建 `FinMindClient()`
- [x] 4.2 實作 `fetch_daily(symbol, start, end)`：呼叫 `FinMindClient.get_taiwan_stock_price`、把 raw row 正規化成 `BarRow`（FinMind 欄位 `Trading_Volume` / `Trading_money` / `open` / `max` / `min` / `close` / `date` 對應）
- [x] 4.3 撰寫 `tests/test_source_finmind.py`：2 個測試（mock `FinMindClient` 回 raw rows → 正規化正確；mock raise `FinMindConnectionError` → 重新拋出）
- [x] 4.4 跑 `uv run pytest tests/test_source_finmind.py -v`

## 5. twstock adapter

- [x] 5.1 建立 `src/ohmystock/data/sources/twstock.py`，實作 `class TwstockSource`（`name = "twstock"`）
- [x] 5.2 實作 `fetch_daily(symbol, start, end)`：呼叫 `twstock.Stock(symbol).fetch_from(year, month)` 取得目標範圍、過濾 `start..end`、正規化成 `BarRow`（twstock 回 `namedtuple` 含 `date / capacity / turnover / open / high / low / close / change / transaction`）
- [x] 5.3 任何 twstock SDK 例外 raise `RuntimeError(f"twstock failed for {symbol}: {e}") from e`
- [x] 5.4 撰寫 `tests/test_source_twstock.py`：2 個測試（mock SDK 回 list of namedtuple → 正規化、過濾 start/end 正確；mock SDK raise → 重新拋出）
- [x] 5.5 跑 `uv run pytest tests/test_source_twstock.py -v`

## 6. yfinance adapter

- [x] 6.1 建立 `src/ohmystock/data/sources/yfinance.py`，實作 `class YFinanceSource`（`name = "yfinance"`）
- [x] 6.2 實作 internal `_to_yahoo_symbol(symbol)`：先試 `{symbol}.TW`，若整段 dataframe 為空再試 `{symbol}.TWO`；都空則回 empty list
- [x] 6.3 實作 `fetch_daily(symbol, start, end)`：呼叫 `yfinance.Ticker(yahoo_symbol).history(start=start, end=end, interval="1d")`、將 dataframe 正規化成 `BarRow`（注意 `Volume` 為股數，需 `// 1000` 轉張數；`amount` yfinance 沒給 → 用 `close * volume_in_shares` 估算並標註）
- [x] 6.4 任何 yfinance 例外 raise `RuntimeError(f"yfinance failed for {symbol}: {e}") from e`
- [x] 6.5 撰寫 `tests/test_source_yfinance.py`：2 個測試（mock `Ticker.history` 回 dataframe → 正規化正確；`.TW` 空 → 試 `.TWO` 再回正常 dataframe）
- [x] 6.6 跑 `uv run pytest tests/test_source_yfinance.py -v`

## 7. `get_kline` orchestrator

- [x] 7.1 建立 `src/ohmystock/data/market_data.py`，定義常數 `_VALID_PERIODS = {"1d"}`、`_ADAPTERS_ORDER = ("finmind", "twstock", "yfinance")`、error code 字串常數
- [x] 7.2 實作 `_validate_inputs(symbol, period, bars, end_date) -> str | None`：參照 spec「Input validation」需求，回傳 error message 或 `None`
- [x] 7.3 實作 `_classify_exception(adapter_name, exc) -> tuple[code, retriable]`：依 design.md §D4 表格映射（`429` / `quota` → `RATE_LIMIT`；`401` / `403` → `AUTH_FAILED`；其餘 → `UPSTREAM_ERROR`）
- [x] 7.4 實作 `_business_day_range(end_date, bars) -> list[str]`：從 `end_date` 往前 skip 週六日抓 `bars` 個日期；單元測試覆蓋月底跨月案例
- [x] 7.5 實作 `get_kline(symbol, period="1d", bars=250, end_date=None) -> dict`：(a) 驗證輸入 → 失敗回 envelope INVALID_INPUT；(b) 算 date range；(c) 從 cache 取現有；(d) 缺哪些 → 依 `_ADAPTERS_ORDER` 試；(e) 寫回 cache；(f) 回標準 envelope（含 `elapsed_ms`）
- [x] 7.6 確認 `get_kline` 任何路徑都不會把 adapter 例外往外拋（最外層 try/except 收所有 `Exception`，分類後封入 envelope）

## 8. orchestrator 測試

- [x] 8.1 撰寫 `tests/test_market_data_orchestrator.py`：覆蓋 spec 中 8 個 scenarios — success / all-fail / 5m rejected / empty symbol / malformed end_date / cache hit on 2nd call / partial cache gap-fetch / FinMind 429
- [x] 8.2 加 1 個測試：FinMind 401 → AUTH_FAILED 優先（非 UPSTREAM_ERROR）
- [x] 8.3 加 1 個測試：所有 adapter 回空 list → `DATA_UNAVAILABLE`
- [x] 8.4 加 1 個測試：所有 adapter raise 5xx → `UPSTREAM_ERROR`
- [x] 8.5 跑 `uv run pytest tests/test_market_data_orchestrator.py -v` 確認全綠

## 9. 反向 import 防護

- [x] 9.1 在 `tests/test_market_data_orchestrator.py` 或新檔加測試：grep 5 個目標檔（`market_data.py` / `cache.py` / `sources/{finmind,twstock,yfinance}.py`）source 確認無 `from ohmystock.api` / `import ohmystock.api`
- [x] 9.2 加測試：subprocess 跑 `python -c "import ohmystock.data.market_data, ohmystock.data.cache, ohmystock.data.sources.finmind, ohmystock.data.sources.twstock, ohmystock.data.sources.yfinance"` 後檢查 `sys.modules` 不含 `fastapi` / `uvicorn` / `starlette`

## 10. 全套驗收

- [x] 10.1 跑 `uv run pytest -v` 全綠（既有 ~26 + 新增 ~18 個 ≈ 44 個全 pass）
- [x] 10.2 在本機放好真實 `.env`，手動跑一次 `uv run python -c "from ohmystock.data.market_data import get_kline; import json; print(json.dumps(get_kline('2330', bars=10, end_date='2026-04-28'), indent=2))"`，確認回傳真實 10 根日 K
- [x] 10.3 重複跑同一指令第二次，觀察 `elapsed_ms` 顯著下降（cache hit）
- [x] 10.4 跑 `openspec validate market-data-fetch-cache --strict` 通過
- [x] 10.5 commit 並 push（commit message 引用本 change name + 列關鍵子模組）
