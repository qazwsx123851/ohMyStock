## ADDED Requirements

### Requirement: FinMind client 提供薄連線層

系統 SHALL 提供 `ohmystock.data.finmind_client.FinMindClient` 類別，初始化時讀取 `Settings.finmind_token`，提供 `get_taiwan_stock_price(symbol: str, start: str, end: str) -> list[dict]` 方法做為冒煙測試入口。HTTP 呼叫 SHALL 透過 `httpx.Client`，timeout 10 秒。連線 / HTTP 非 2xx / JSON parse 失敗 SHALL raise 自定 exception `FinMindConnectionError`（繼承 `RuntimeError`），錯誤訊息 SHALL 包含原因（HTTP status code、網路錯誤類別、或 parse 失敗欄位）。本 Requirement **不**包含 fallback 鏈、快取、retry、rate limit 處理；那些留給 Phase 1 `data_pipeline_skill`。

#### Scenario: 成功呼叫回傳 list[dict]
- **WHEN** `FinMindClient` 在 mock httpx `200 OK` 且 body 為合法 FinMind JSON `{"data": [...]}` 的環境執行 `get_taiwan_stock_price("2330", "2026-04-22", "2026-04-29")`
- **THEN** 回傳值 SHALL 為 `list[dict]`，每筆 dict 包含 FinMind 原 schema 欄位（如 `date`、`stock_id`、`close`），且不拋例外

#### Scenario: HTTP 500 raise FinMindConnectionError
- **WHEN** `FinMindClient` 在 mock httpx `500 Internal Server Error` 的環境執行 `get_taiwan_stock_price("2330", ...)`
- **THEN** 拋出 `FinMindConnectionError`，message 包含 `"500"` 字串

#### Scenario: 缺 token 不在 import 時拋例外
- **WHEN** `Settings.finmind_token` 為空字串時執行 `from ohmystock.data.finmind_client import FinMindClient`
- **THEN** import 成功，僅在實際呼叫 `get_taiwan_stock_price()` 時才會 raise `FinMindConnectionError`（auth 失敗）

---

### Requirement: Shioaji paper client 提供模擬倉薄連線層

系統 SHALL 提供 `ohmystock.paper.shioaji_client.ShioajiPaperClient` 類別，建構時讀取 `Settings.shioaji_api_key / shioaji_secret_key`，內部透過 `shioaji.Shioaji(simulation=True)` 建立連線，**不**接受 `simulation` 參數覆寫（編譯時保證模擬模式）。提供 `login()`（同步呼叫底層 SDK 的 login）與 `get_snapshot(symbol: str) -> dict`（取一檔即時快照）兩個方法。連線 / login 失敗 SHALL raise 自定 exception `ShioajiConnectionError`（繼承 `RuntimeError`）。**不**支援下單 / 訂閱即時 tick / CA 憑證 / live 模式 — 這些留給 Phase 2。

#### Scenario: login 成功
- **WHEN** `ShioajiPaperClient` 在 mock shioaji SDK 回傳成功 contract 列表的環境執行 `login()`
- **THEN** 不拋例外；後續 `get_snapshot("2330")` 可回傳 dict（至少含 `symbol` 與 `close` key）

#### Scenario: login 失敗 raise ShioajiConnectionError
- **WHEN** `ShioajiPaperClient` 在 mock shioaji SDK 拋出任意 exception 的環境執行 `login()`
- **THEN** 拋出 `ShioajiConnectionError`，原始例外的訊息 SHALL 出現在 message chain（透過 `raise ... from`）

#### Scenario: 編譯時禁止 live 模式
- **WHEN** 檢視 `ShioajiPaperClient.__init__` 簽章
- **THEN** 該 method SHALL **不**含 `simulation` 參數；且 source 中 `Shioaji(simulation=True)` 為 hardcoded（非從變數帶入）

---

### Requirement: smoke-test CLI 子命令驗證三方連線

系統 SHALL 提供 `ohmystock smoke-test` 子命令，執行時依序呼叫 (1) `FinMindClient.get_taiwan_stock_price("2330", ...)` 取最近 5 個交易日資料、(2) `ShioajiPaperClient.login()` 後 `get_snapshot("2330")`、(3) Anthropic SDK 一筆 1-token Haiku 4.5 ping。每項 SHALL 各自獨立 try/except 並印 `[PASS] <name>` 或 `[FAIL] <name>: <reason>`，三項全部執行完才彙總；任一 FAIL → 命令 exit code 1，全部 PASS → exit code 0。本子命令 SHALL **不**為 stub。

#### Scenario: smoke-test --help 列出三項檢查
- **WHEN** 執行 `uv run ohmystock smoke-test --help`
- **THEN** stdout 同時包含 `finmind`、`shioaji`、`anthropic` 三個字串（大小寫不敏感）；exit code 0

#### Scenario: 三項全 PASS exit 0
- **WHEN** 三方 client 全 mock 為成功，執行 `uv run ohmystock smoke-test`
- **THEN** stdout 同時包含 `[PASS] finmind`、`[PASS] shioaji`、`[PASS] anthropic`；exit code 0

#### Scenario: 任一 FAIL exit 1
- **WHEN** mock FinMind 拋 `FinMindConnectionError`，其他兩項成功，執行 `uv run ohmystock smoke-test`
- **THEN** stdout 包含 `[FAIL] finmind`、`[PASS] shioaji`、`[PASS] anthropic`；exit code 1
