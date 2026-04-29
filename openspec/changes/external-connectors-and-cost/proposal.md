## Why

`fastapi-bootstrap`（已 archived 為 `2026-04-28-fastapi-bootstrap`）已上線 FastAPI app + EventBus + SQLite WAL/FTS5 骨架，但 Phase 0 milestone 自我驗收還缺兩件事：(1) **Shioaji 模擬倉 / FinMind 贊助會員 / Anthropic API 三方連線冒煙測試**，(2) **LLM cost tracking decorator**（對應 `docs/v3-decisions.md` 決策 #15「LLM 成本即時追蹤 + 軟性熔斷」）。後者是 Phase 1 swarm preset 的 hard prerequisite — 沒有 cost decorator，後續 Phase 3 LLM Decider 的 token 消耗就無法寫進 Trade Journal 的 `llm_input_tokens / llm_output_tokens / llm_cost_usd` 三欄（依 `docs/llm-decision-schema.md` §4.1）。本 change 補完 Phase 0d，使 `ohmystock smoke-test` 可一鍵驗證三方連線，並讓 cost decorator 落地，成為 Phase 1 開工的著陸點。

## What Changes

- **新增** `src/ohmystock/data/finmind_client.py`：`FinMindClient` 薄包裝（讀 `Settings.finmind_token`），提供 `get_taiwan_stock_price(symbol, start, end)` 一個方法做冒煙測試；HTTP 呼叫透過 `httpx`，timeout 10 秒，失敗 raise `FinMindConnectionError`（自定 exception，不靜默吞）；**不**實作 fallback 鏈、**不**實作快取（留給 Phase 1 `data_pipeline_skill`）
- **新增** `src/ohmystock/paper/shioaji_client.py`：`ShioajiPaperClient` 薄包裝（讀 `Settings.shioaji_api_key / shioaji_secret_key`），提供 `login()` 與 `get_snapshot(symbol)` 兩個方法；只跑模擬模式（`simulation=True`），不接 CA 憑證；登入失敗 raise `ShioajiConnectionError`；**不**下單、**不**訂閱即時 tick（留給 Phase 2）
- **新增** `src/ohmystock/observability/cost_tracker.py`：
  - `@track_llm_cost(decision_id: str | None = None)` decorator，包住任何回傳 Anthropic `Message` object 的 async function，自動讀 `usage.input_tokens / usage.output_tokens / cache_*` 並依模型計費表（Opus 4.7 / Sonnet 4.6 / Haiku 4.5）算 USD 成本，寫進 `llm_costs` SQLite 表
  - `get_monthly_cost_usd(year_month: str) -> float` query helper（給 Phase 4 admin dashboard widget 用）
  - 計費表 hardcode 為常數 dict（`MODEL_PRICING_USD_PER_MTOK`），未來模型版本變動走 §16 markdown proposal 流程
- **新增** `src/ohmystock/journal/schema.py`：Trade Journal 第一張表 + 索引 SQL
  - `journal_entries`（主表，欄位依 `docs/llm-decision-schema.md` §4 v3.1 schema，**僅含 entry/exit/reject 三種 kind 的共通欄位 + JSON blob 存 SEPA / cited_skills / tool_calls 等變動欄**，避免 column 爆炸）
  - `journal_entries_fts`（FTS5 virtual table，索引 `entry_thesis / llm_reasoning / exit_reason` 三欄）
  - `llm_costs`（cost decorator 寫入目標：`decision_id / model / input_tokens / output_tokens / cost_usd / created_at`）
  - `init_schema(conn)` 函式 idempotent，可重複呼叫
- **新增** `cli.py` 的 `smoke-test` 子命令：依序跑 (1) FinMind 抓 2330 最近 5 日收盤、(2) Shioaji login + 取 2330 snapshot、(3) Anthropic 一筆 1-token Haiku 4.5 ping，**每項各自獨立 try/except + 印 PASS/FAIL**（單項失敗不阻擋下一項），全跑完印彙總；任一 FAIL exit 1。CLI 子命令清單從 6 擴為 7（`run` / `backtest` / `review` / `propose` / `screen` / `api` / `smoke-test`）
- **修改** `pyproject.toml`：`[project.dependencies]` 新增 `httpx>=0.27`、`shioaji>=1.2`、`anthropic>=0.40`；不引入 `finmind` 套件（用 httpx 直打 REST，避免拉太多 transitive dep）
- **新增** tests：
  - `tests/test_finmind_client.py`（mock httpx，2 個測試：成功 parse、HTTP 500 raise `FinMindConnectionError`）
  - `tests/test_shioaji_client.py`（mock shioaji，2 個測試：login 成功、login 失敗 raise）
  - `tests/test_cost_tracker.py`（4 個測試：Haiku 計費、Opus 計費、cache_read 折扣、寫入 `llm_costs` 表後 `get_monthly_cost_usd` 正確聚合）
  - `tests/test_journal_schema.py`（3 個測試：`init_schema` idempotent、FTS5 索引可 `MATCH` 查詢、`llm_costs` 表結構符合 schema）
  - `tests/test_cli_smoke_test.py`（1 個測試：`ohmystock smoke-test --help` 列出三項檢查名稱，exit 0）
- **不做**：FinMind fallback 鏈（→ TWSE OpenAPI → twstock → Parquet 快取，留給 Phase 1）、Shioaji CA 憑證 / live 下單（Phase 2）、Anthropic prompt cache wiring（Phase 3）、admin dashboard cost widget（Phase 4）、軟性熔斷 `OHMYSTOCK_LLM_DEGRADE` 自動觸發邏輯（Phase 3.5 防線 9）、Trade Journal `kind=entry/exit/reject` 業務欄位寫入器（Phase 3）

## Capabilities

### New Capabilities

- `external-connectors`：FinMind / Shioaji / Anthropic 三個外部服務的薄連線層（client class + 自定 exception + smoke-test entry point），不含 fallback、快取、業務邏輯，純粹 connectivity 驗證 + 後續 change 的注入點
- `cost-tracking`：`@track_llm_cost` decorator + `llm_costs` SQLite 表 + 月成本聚合 query；對應 v3 決策 #15 可觀測性需求
- `trade-journal-schema`：Trade Journal `journal_entries` 主表 + FTS5 索引 + `llm_costs` 表的 schema 與 `init_schema()` migration helper；不含業務寫入器（後續 change 補）

### Modified Capabilities

- `cli-and-config`：新增 `smoke-test` 子命令（從 6 子命令擴充為 7）。spec delta 採 ADDED「`smoke-test` 子命令依序驗證 FinMind / Shioaji / Anthropic 三方連線」一條 Requirement；既有「CLI 子命令骨架」Requirement 須 MODIFIED 把子命令清單從 6 個更新為 7 個，且 `smoke-test` 與 `api` 同樣**非** stub（會真正執行外部連線檢查）
- `backend-api-and-eventbus`：`get_connection()` 在 `db.py` 既有實作上**不**改介面，但本 change 在 `journal/schema.py` 補上實際 schema migration entry point；spec delta 採 ADDED「Trade Journal schema 由 `init_schema(conn)` 提供 idempotent migration」一條 Requirement

## Impact

- **新增依賴**：`httpx>=0.27`（含 `httpcore` / `h11`）、`shioaji>=1.2`（含 `protobuf` / `grpcio`，Windows wheel ~30MB）、`anthropic>=0.40`（官方 SDK，含 `httpx` 已被前者拉入）。`uv sync` 後 `uv.lock` 會更新
- **新增檔案**：`src/ohmystock/data/finmind_client.py`、`src/ohmystock/paper/shioaji_client.py`、`src/ohmystock/observability/cost_tracker.py`、`src/ohmystock/journal/schema.py`、5 個 tests 檔
- **修改檔案**：`pyproject.toml`（3 個 deps）、`uv.lock`、`src/ohmystock/cli.py`（新增 `smoke-test` 子命令）、`tests/test_cli.py`（更新斷言：6 → 7 子命令、`smoke-test` 不在 stub parametrize 名單）
- **不影響**：`docs/`（schema 規格已寫於 `llm-decision-schema.md` v3.1，不需異動）、`.env.example`（沿用既有 11 個 key，本 change 不新增 env var）、其他 14 個尚為空殼的子模組
- **後續 unblock**：
  - **Phase 1 skills 開工**：`technical-skills-and-backtest`（Phase 1）— 將在 `data/` 新增 fallback 鏈、在 `skills/technical/` 寫第一個 skill
  - **Phase 3 LLM Decider**：`llm-decider-and-confirm-gate`（Phase 3）— 將用 `@track_llm_cost` 包住 `entry_decision_team` swarm 的 PM 節點
  - **Phase 4 admin dashboard**：`web-admin-bearer-auth`（Phase 4）— 將呼叫 `get_monthly_cost_usd()` 餵 Dashboard cost widget（依 `docs/frontend.md` §17.B）
- **風險**：Shioaji Windows wheel 體積大（~30MB）+ 有時 PyPI mirror 不穩 → 若 `uv sync` 卡住，記錄到 `docs/v3-decisions.md` §6 backlog；本 change 不為此 risk 設計緩解（mocked test 已避免 CI 依賴 wheel；human dev 環境 fallback 為 `pip install --index-url` pypi 主站）
