## 1. 依賴與套件設定

- [x] 1.1 在 `pyproject.toml` 的 `[project.dependencies]` 新增 `httpx>=0.27`、`shioaji>=1.2`、`anthropic>=0.40`
- [x] 1.2 執行 `uv sync` 更新 `uv.lock`，確認三個 wheel 可在當前 Windows 環境安裝
- [x] 1.3 用 `uv run python -c "import httpx, shioaji, anthropic"` 確認三個套件 import 不報錯

## 2. Trade Journal schema（先做，後續模組會依賴）

- [x] 2.1 建立 `src/ohmystock/journal/schema.py`，實作 `init_schema(conn)`：建 `journal_entries`（含 6 欄、`decision_id` index、`(kind, created_at)` 複合 index、`kind` CHECK constraint）
- [x] 2.2 在同檔加上 `journal_entries_fts` FTS5 external content table（索引 `entry_thesis / llm_reasoning / exit_reason`）
- [x] 2.3 在同檔加上 `journal_entries_ai / _au / _ad` 三個 trigger，使 FTS5 自動同步
- [x] 2.4 在同檔加上 `llm_costs` 表（7 欄）+ `created_at` 索引
- [x] 2.5 全 DDL 用 `IF NOT EXISTS` 包；缺 FTS5 時 raise `RuntimeError("FTS5 unavailable")`；單一 transaction commit
- [x] 2.6 撰寫 `tests/test_journal_schema.py`：3 個測試（idempotent、FTS5 MATCH 命中、`llm_costs` 表結構）
- [x] 2.7 跑 `uv run pytest tests/test_journal_schema.py -v` 確認全綠

## 3. Cost tracker

- [x] 3.1 建立 `src/ohmystock/observability/cost_tracker.py`，宣告 `MODEL_PRICING_USD_PER_MTOK` 常數 dict（含 `claude-opus-4-7` / `claude-sonnet-4-6` / `claude-haiku-4-5-20251001` 三個 model 的 `input` / `output` 費率）
- [x] 3.2 實作 `track_llm_cost(decision_id: str | None = None)` async decorator：取 result.usage、查表算 `cost_usd`、寫入 `llm_costs`；例外不寫成本但原樣 propagate
- [x] 3.3 未知 model 時 raise `ValueError`（不靜默計算為 0）
- [x] 3.4 實作 `get_monthly_cost_usd(year_month: str) -> float`：依 `created_at` prefix 比對加總；空表回 `0.0`
- [x] 3.5 撰寫 `tests/test_cost_tracker.py`：4 個測試（Haiku 計費、Opus 計費、例外不寫成本、`get_monthly_cost_usd` 正確聚合）
- [x] 3.6 跑 `uv run pytest tests/test_cost_tracker.py -v` 確認全綠

## 4. FinMind client

- [x] 4.1 建立 `src/ohmystock/data/finmind_client.py`，定義 `FinMindConnectionError(RuntimeError)`
- [x] 4.2 實作 `FinMindClient.__init__(self)`：讀 `Settings.finmind_token`，建 `httpx.Client(timeout=10.0)`
- [x] 4.3 實作 `get_taiwan_stock_price(symbol, start, end) -> list[dict]`：呼叫 FinMind `/api/v4/data?dataset=TaiwanStockPrice`，HTTP 非 2xx / JSON parse 失敗 raise `FinMindConnectionError`
- [x] 4.4 撰寫 `tests/test_finmind_client.py`：2 個測試（mock httpx 200 OK 成功 parse、500 raise）
- [x] 4.5 跑 `uv run pytest tests/test_finmind_client.py -v`

## 5. Shioaji paper client

- [x] 5.1 建立 `src/ohmystock/paper/shioaji_client.py`，定義 `ShioajiConnectionError(RuntimeError)`
- [x] 5.2 實作 `ShioajiPaperClient.__init__(self)`：讀 `Settings.shioaji_api_key / shioaji_secret_key`；內部 hardcode `Shioaji(simulation=True)`，**不**接受 simulation 參數
- [x] 5.3 實作 `login()` 與 `get_snapshot(symbol) -> dict`；失敗 `raise ShioajiConnectionError(...) from e`
- [x] 5.4 撰寫 `tests/test_shioaji_client.py`：2 個測試（mock SDK login 成功、login 失敗 raise + 例外鏈）
- [x] 5.5 跑 `uv run pytest tests/test_shioaji_client.py -v`

## 6. CLI smoke-test 子命令

- [x] 6.1 在 `src/ohmystock/cli.py` 新增 `smoke-test` 子命令，help 文字明確列 `finmind` / `shioaji` / `anthropic` 三項
- [x] 6.2 實作執行邏輯：依序跑 FinMind→Shioaji→Anthropic，每項 try/except 印 `[PASS] <name>` 或 `[FAIL] <name>: <reason>`
- [x] 6.3 任一 FAIL → exit 1；全 PASS → exit 0；三項 SHALL 全部執行完才彙總（不 fail-fast）
- [x] 6.4 更新 `tests/test_cli.py`：root help 斷言從 6 改 7 子命令；stub parametrize 不含 `smoke-test`
- [x] 6.5 撰寫 `tests/test_cli_smoke_test.py`：1 個測試（`ohmystock smoke-test --help` 列三項名稱、exit 0）
- [x] 6.6 跑 `uv run pytest tests/test_cli.py tests/test_cli_smoke_test.py -v`

## 7. 反向 import 防護驗證

- [x] 7.1 撰寫測試（可塞進 `tests/test_journal_schema.py` 或新檔）：grep 四個目標模組 source 確認無 `from ohmystock.api` / `import ohmystock.api`
- [x] 7.2 撰寫測試：subprocess 執行 `python -c "import ohmystock.data.finmind_client, ohmystock.paper.shioaji_client, ohmystock.observability.cost_tracker, ohmystock.journal.schema"` 後檢查 `sys.modules` 不含 `fastapi` / `uvicorn` / `starlette`

## 8. 全套驗收

- [x] 8.1 跑 `uv run pytest -v` 全綠（既有 13 + 新增 ~13 個測試 ≈ 26 個全 pass）
- [x] 8.2 在本機放好真實 `.env`（`FINMIND_TOKEN` / `SHIOAJI_*` / `ANTHROPIC_API_KEY`），跑 `uv run ohmystock smoke-test`，三項 `[PASS]`、exit 0
- [x] 8.3 跑 `openspec validate external-connectors-and-cost --strict` 通過
- [ ] 8.4 commit 並 push（commit message 引用本 change name + 列關鍵子模組）
