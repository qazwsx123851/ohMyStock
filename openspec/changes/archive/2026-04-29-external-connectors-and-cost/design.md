## Context

`fastapi-bootstrap` 完成後，repo 中的「外部世界」三個觸點（Shioaji 模擬倉、FinMind 籌碼資料、Anthropic Claude API）尚未在 code 層接通；同時 v3 決策 #15「LLM 成本即時追蹤」也還只是 schema 上的承諾（`docs/llm-decision-schema.md` §4.1 寫了 `llm_input_tokens / llm_output_tokens / llm_cost_usd` 三欄但無寫入器）。本 change 一次補完這兩件事，並順手把 Trade Journal 第一張表（`journal_entries` + FTS5 + `llm_costs`）落地，避免每個後續 change 都要重複 init schema。

當前狀態：
- `src/ohmystock/data/`、`src/ohmystock/paper/`、`src/ohmystock/observability/`、`src/ohmystock/journal/` 四個子模組目錄存在但只有空 `__init__.py`
- `src/ohmystock/api/db.py` 已提供 `get_connection()`（WAL + FTS5 探測）但**不**自動 migrate schema
- `Settings` 類別（`config.py`）已有 11 個 env var 欄位，包含三方所需 secret（`SHIOAJI_*` / `FINMIND_TOKEN` / `ANTHROPIC_API_KEY`）

約束：
- 解 user 已表達的偏好「避免過度工程」（CLAUDE.md §2、`memory/feedback_simple_design.md`）— 三個 client 都做薄包裝，不做 fallback 鏈、retry policy、circuit breaker、connection pool
- 解 cross-stage 痛點：cost decorator 是 Phase 1 swarm 與 Phase 3 Decider 的共用基礎設施，提早做避免之後三個 change 各自湊一份
- Solo dev 個人專案：smoke-test 失敗時印人類可讀訊息即可，不做機器可讀 JSON exit code 區分

## Goals / Non-Goals

**Goals:**
- 三個外部 client 都能用 `Settings` 中的 env var 完成連線（成功 / 失敗訊息明確）
- `ohmystock smoke-test` 一鍵驗收 Phase 0 自我驗收條件（Shioaji + FinMind + Anthropic 三方連線測試通過）
- `@track_llm_cost` decorator 對 Anthropic SDK 的 `Message` object 自動萃取 token 用量並寫進 SQLite，後續 Phase 3 包 Decider 時零負擔接入
- Trade Journal `journal_entries` + FTS5 + `llm_costs` 三張表 schema 上線且 idempotent，後續 change 不再碰 DDL
- 所有測試在無真實外部 API key / 網路連線情境下可跑（unit test mock 三方 SDK）

**Non-Goals:**
- FinMind fallback 鏈（→ TWSE OpenAPI → twstock → Parquet 快取）：Phase 1 `data_pipeline_skill` 處理
- Shioaji 真實下單、CA 憑證、即時 tick 訂閱：Phase 2 `paper-broker-and-backtest`
- Anthropic prompt cache wiring、批次 API、tool use schema：Phase 3 `llm-decider-and-confirm-gate`
- 軟性熔斷（達 USD $50 月成本自動切 `OHMYSTOCK_LLM_DEGRADE=true`）：Phase 3.5 防線 9
- Admin Dashboard cost widget UI：Phase 4 `web-admin-bearer-auth`
- Trade Journal `kind=entry/exit/reject` 業務寫入器（含 SEPA 5 欄）：Phase 3
- Schema migration 框架（alembic 等）：v1 範圍以 `init_schema(conn)` idempotent SQL 取代；schema 變更時人工新增 migration 函式（個人專案規模）

## Decisions

### D1：FinMind client 用 `httpx` 直打 REST，不引入 `finmind` 套件

**選 A（採用）**：`httpx.Client` + 手寫 query string + JSON parse
**選 B**：`finmind>=1.7` Python 套件，呼叫 `DataLoader.taiwan_stock_daily(...)`

**理由**：
- B 拉入 `pandas` / `requests` / `python-dateutil` 等大量 transitive deps；A 只需 `httpx`（FastAPI 已間接依賴 starlette → httpx）
- 本 change 只需一個 endpoint（`/api/v4/data?dataset=TaiwanStockPrice`）做冒煙測試；B 的便利性無價值
- 若日後 Phase 1 要改用 `pandas.DataFrame` 介面，再切 B（不視為破壞性變更，因為連線層被 fallback 鏈包起來）

### D2：Shioaji 強制 `simulation=True`，不接 CA 憑證

**理由**：
- v1 完全 paper trading（`docs/v3-decisions.md` §2 決策 #4 Live trading 延後）
- CA 憑證需要實體買賣 → 個人安全考量提早抽離
- `ShioajiPaperClient.__init__` 不接受 `simulation: bool` 參數（避免日後不小心傳 `False`）；要走 live 必須**新增** `ShioajiLiveClient` class（強制 reviewer review）

### D3：Cost tracker 的計費表 hardcode 在 code，不放 settings / env

**選 A（採用）**：`MODEL_PRICING_USD_PER_MTOK: dict[str, dict[str, float]]` 常數
**選 B**：`pricing.yaml` + `Settings.pricing_path`

**理由**：
- Anthropic 官方公布價格時間軸固定（每次模型發布跟著公布），不會「快速變動」
- Solo dev 改價格只要 PR 改一行，沒必要走 config
- 如果走 §16 提案閘流程，未來換模型時 reviewer 一定看得到 diff
- 計費表結構（input / output / cache_write / cache_read 四種費率）暫時不複雜化，先支援 input / output；cache_write / cache_read 在 Phase 3 接 prompt cache 時再加

### D4：`@track_llm_cost` 為 async decorator，不做 sync 版

**理由**：
- Anthropic SDK 主流用 `AsyncAnthropic`，Phase 3 swarm 全 async
- 同步版本只在 smoke-test 用一次（一筆 Haiku ping），smoke-test 不走 decorator 也沒關係（直接呼叫 Anthropic SDK + 印訊息即可）
- 砍同步版減少 50% 測試矩陣

### D5：Trade Journal `journal_entries` 用 `payload_json` 存變動欄位

**選 A（採用）**：核心欄位（`id / decision_id / kind / symbol / created_at`）成 column；其他依 `kind` 變動的欄位（entry: `entry_price / atr_at_entry / sepa_*`；exit: `exit_reason / pnl_pct`；reject: `reject_layer / reject_reason`）塞進 `payload_json TEXT`
**選 B**：所有欄位都是 SQL column（依 schema doc §4 完整展開 ~30 欄）
**選 C**：分 3 張表（`journal_entries_entry / _exit / _reject`）

**理由**：
- 欄位數會隨策略演化（例如未來加 SEPA 欄、加 LLM 思考鏈中間步驟）→ B 每次都要 migration
- C 查詢時要做 UNION ALL，FTS5 索引也要建三份
- A 用 SQLite JSON1 extension（內建）可索引：`SELECT json_extract(payload_json, '$.entry_price') FROM journal_entries WHERE kind='entry'`
- FTS5 仍可索引 entry_thesis / llm_reasoning / exit_reason（這幾欄從 payload_json 抽出來進 FTS5 表）→ 全文檢索不受影響

### D6：FTS5 索引採「外部 content」模式（external content）

**理由**：
- 避免 FTS5 表複製 entry_thesis 全文（節省 50% 空間）
- INSERT/UPDATE 透過 trigger 同步更新 FTS5 表
- `init_schema()` 同時建主表 + FTS5 + 三個 trigger（INSERT/UPDATE/DELETE）

### D7：smoke-test 子命令的執行順序與失敗模式

**順序**：FinMind → Shioaji → Anthropic
- FinMind 最快（<1 秒）：失敗最常見（token 過期），先擋掉
- Shioaji 次之（1-3 秒 login）
- Anthropic 最慢（API 1 token ping 約 1-2 秒）也最貴

**失敗模式**：每項獨立 try/except，全跑完再彙總；任一 FAIL 整體 exit 1。理由：solo dev 想一眼看到「三項哪幾項過」，比 fail-fast 有用。

## Risks / Trade-offs

- **[Risk] Shioaji 套件 Windows wheel 體積大（~30MB）+ PyPI mirror 不穩** → Mitigation: `pyproject.toml` 不釘 mirror；mocked test 不依賴實際 wheel；human dev 失敗時 fallback `pip install --index-url https://pypi.org/simple`。**不**做 retry / 鏡像切換邏輯（個人專案）
- **[Risk] FinMind 贊助會員 token 帶在 query string 會出現在 log** → Mitigation: `httpx.Client` 全程用 HTTPS；`logging.getLogger("httpx")` 在 `cost_tracker.py` 設 `WARNING` 級別避免 INFO log url；token 仍放 query string（FinMind API 不支援 header auth）。本 change **不**新增 secret scrubbing middleware（過度工程）
- **[Risk] Anthropic SDK 版本可能改 `usage` 物件 schema** → Mitigation: `cost_tracker.py` 只讀 `usage.input_tokens / usage.output_tokens` 兩個欄位（最穩定的 stable API）；cache_read / cache_write 加上去時用 `getattr(usage, "cache_read_input_tokens", 0)` 容錯
- **[Risk] `init_schema()` 重複執行可能造成 trigger / FTS5 conflict** → Mitigation: 全 SQL 用 `CREATE TABLE IF NOT EXISTS` / `CREATE TRIGGER IF NOT EXISTS` / `CREATE VIRTUAL TABLE IF NOT EXISTS`；test 中明確驗證 idempotent（呼叫兩次不報錯）
- **[Risk] `track_llm_cost` 在 SDK 例外時可能漏寫 cost** → Mitigation: decorator 內 try/finally：呼叫包住 function 的 await，例外仍 raise；finally 區塊只在拿到 result.usage 時才寫 SQLite。**不**做「估算 token」fallback（estimated cost 比不寫還危險）
- **[Trade-off] payload_json 用 TEXT 存 JSON 而非 BLOB** → 失去型別約束；換來人類可讀 + `sqlite3` CLI 可直接 `json_extract` 查詢（debug 友好）
- **[Trade-off] smoke-test 子命令真的呼叫外部 API（不 mock）** → 走 CI 環境會失敗（無 secret）；解法：CI 不跑 `ohmystock smoke-test`，只跑 `pytest`（pytest 完全 mock）。Solo dev 本機才需要跑 smoke-test
