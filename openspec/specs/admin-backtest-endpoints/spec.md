# admin-backtest-endpoints Specification

## Purpose
TBD - created by archiving change web-admin-backtest-pages. Update Purpose after archive.

## Requirements

### Requirement: `backtest_jobs` schema 與 init
系統 SHALL 提供 `ohmystock.backtest.storage.init_schema(conn)`，idempotent 建立 `backtest_jobs` 表與 `idx_backtest_jobs_created_at` index。欄位包含：`id TEXT PK`、`strategy TEXT NOT NULL`、`period_from/period_to TEXT NOT NULL`（`YYYY-MM-DD`）、`custom_symbols_json TEXT NOT NULL`、`initial_capital REAL NOT NULL`、`status TEXT CHECK IN ('completed','failed')`、`elapsed_ms INTEGER NOT NULL`、`result_json TEXT NOT NULL`、`created_at TEXT NOT NULL`（ISO-8601 +08:00）。app startup 或第一個 endpoint 接到請求時 SHALL 呼叫 `init_schema`。

#### Scenario: 第一次呼叫建表
- **GIVEN** 全新 `:memory:` SQLite connection
- **WHEN** 呼叫 `init_schema(conn)`
- **THEN** `sqlite_master` 中 SHALL 出現 `backtest_jobs` table 與 `idx_backtest_jobs_created_at` index

#### Scenario: 重複呼叫不報錯
- **GIVEN** 已建表的 connection
- **WHEN** 再次呼叫 `init_schema(conn)`
- **THEN** SHALL 不拋例外
- **AND** `backtest_jobs` 表 schema SHALL 不變

---

### Requirement: 端點掛載與 auth 一致性
系統 SHALL 在 `src/ohmystock/api/routes/backtest.py` 提供 FastAPI router，並於 `src/ohmystock/api/app.py` 內掛載，使下列 4 個 routes 生效：
- `POST /api/admin/backtest/run`
- `GET /api/admin/backtest/jobs`
- `GET /api/admin/backtest/jobs/{job_id}`
- `GET /api/admin/backtest/strategies`

此 router SHALL 套用全域 `require_admin` Bearer-token dependency，且 SHALL 透過 `Depends(get_db)` 取得 per-request `sqlite3.Connection`。所有回應 SHALL 走 `_envelope.to_success(...)` / `_envelope.map_exception_to_envelope(...)`，輸出 `{ok, data, error}` 信封。

#### Scenario: 未帶 Authorization header
- **WHEN** 客戶端對任一上述 4 個 endpoint 發 request 但無 `Authorization` header
- **THEN** 回應狀態碼 SHALL 為 401
- **AND** body SHALL 為 `{"ok": false, "error": {"code": "auth_missing", ...}}`

#### Scenario: 帶錯誤 token
- **GIVEN** `OHMYSTOCK_ADMIN_TOKEN` 已設定
- **WHEN** 客戶端帶 `Authorization: Bearer wrong` 發 request
- **THEN** 回應狀態碼 SHALL 為 401
- **AND** error.code SHALL 為 `auth_invalid`

---

### Requirement: `GET /api/admin/backtest/strategies` 列出 registry
系統 SHALL 回 200 OK 與 `data.strategies: array<{name: string, description: string}>`，內容由 `ohmystock.backtest.strategy.registry.available_strategies()` 提供。註冊在 `ohmystock.backtest.strategy` 模組下、可無參數構造的 `Strategy` 子類別 SHALL 自動出現在此清單。失敗的策略（構造拋例外）SHALL 被略過、不影響其他項。

#### Scenario: 至少含 sma_cross
- **WHEN** 對 `/api/admin/backtest/strategies` 發 GET
- **THEN** `data.strategies` SHALL 為 array
- **AND** 至少一個元素的 `name` SHALL 等於 `"sma_cross"`

#### Scenario: 元素 schema
- **WHEN** 對 `/api/admin/backtest/strategies` 發 GET
- **THEN** 每個元素 SHALL 包含 `name`（字串）與 `description`（字串）兩個 key

---

### Requirement: `POST /api/admin/backtest/run` body schema 與驗證
系統 SHALL 接受 JSON body：
```
{
  "strategy": string (必填，必須在 registry 中),
  "symbols":  string[] (必填，長度 1..50；每個元素 4–6 位數字),
  "period_from": string (必填，YYYY-MM-DD),
  "period_to":   string (必填，YYYY-MM-DD，>= period_from),
  "initial_capital": number (選填，預設 1_000_000，> 0),
  "fee_discount":    number (選填，預設 0.28，0 < x <= 1),
  "slippage_bps":    integer (選填，預設 30，>= 0),
  "day_trade":       boolean (選填，預設 false)
}
```

驗證失敗（任何欄位）SHALL 回 400 與 `error.code = "invalid_input"` + `message` 描述。`period_to - period_from` SHALL ≤ 5 年（1830 天），超出回 400 `error.code = "input_too_large"`。`symbols.length > 50` 同樣回 400 `error.code = "input_too_large"`。

#### Scenario: 缺 strategy
- **WHEN** 客戶端 POST body `{"symbols":["2330"], "period_from":"2024-01-01", "period_to":"2024-12-31"}`
- **THEN** 回應狀態碼 SHALL 為 400 或 422
- **AND** body SHALL 為 `{ok: false, error: {...}}` 信封

#### Scenario: 不認識的 strategy
- **WHEN** 客戶端 POST `{"strategy":"nonexistent", "symbols":["2330"], "period_from":"2024-01-01", "period_to":"2024-12-31"}`
- **THEN** 回應狀態碼 SHALL 為 400
- **AND** `error.code` SHALL 為 `invalid_input`

#### Scenario: period 倒置
- **WHEN** `period_from = "2024-12-31"`, `period_to = "2024-01-01"`
- **THEN** 回應狀態碼 SHALL 為 400
- **AND** `error.code` SHALL 為 `invalid_input`

#### Scenario: symbols 過多
- **WHEN** `symbols.length = 51`
- **THEN** 回應狀態碼 SHALL 為 400
- **AND** `error.code` SHALL 為 `input_too_large`

#### Scenario: 期間過長
- **WHEN** `period_from = "2010-01-01"`, `period_to = "2024-12-31"`
- **THEN** 回應狀態碼 SHALL 為 400
- **AND** `error.code` SHALL 為 `input_too_large`

---

### Requirement: `POST /api/admin/backtest/run` 同步執行與持久化
通過驗證後，系統 SHALL：
1. 對每個 symbol 從 `bars_daily` 載入 `[period_from, period_to]` 區間的 bars。
2. 任一 symbol 在區間內 0 筆資料 → 回 400 `error.code = "missing_bars"`，message 內含 offending symbol。
3. 呼叫 `run_backtest(strategy_instance, bars_by_symbol, period={"from","to"}, initial_capital, fee_discount, slippage_bps, day_trade)`。
4. 引擎回 envelope.ok=true → `status="completed"`、`result_json = json.dumps(envelope["data"])`；engine.ok=false → `status="failed"`、`result_json = json.dumps({"error": envelope["error"]})`、HTTP 仍為 200（job 落表了）。
5. `INSERT INTO backtest_jobs (...)` 一筆，`id = uuid.uuid4().hex`、`created_at = now(+08:00).isoformat()`。
6. 回 200 與 `data = {job_id, status, elapsed_ms}`。

#### Scenario: happy path 寫表
- **GIVEN** `bars_daily` 內 `2330` 在 2024-01-01..2024-12-31 區間有 ≥ 200 筆
- **WHEN** POST `{"strategy":"sma_cross","symbols":["2330"],"period_from":"2024-01-01","period_to":"2024-12-31"}`
- **THEN** 回應狀態碼 SHALL 為 200
- **AND** `data.job_id` SHALL 為長度 32 的 hex 字串
- **AND** `data.status` SHALL 等於 `"completed"`
- **AND** `backtest_jobs` 中 SHALL 多一筆對應的 row
- **AND** 該 row 的 `result_json` SHALL 為合法 JSON 且解析後含 `equity_curve` 與 `trades` keys

#### Scenario: bars 缺失
- **GIVEN** `bars_daily` 內 `9999` 任何日期都無資料
- **WHEN** POST `{"strategy":"sma_cross","symbols":["9999"],"period_from":"2024-01-01","period_to":"2024-12-31"}`
- **THEN** 回應狀態碼 SHALL 為 400
- **AND** `error.code` SHALL 為 `missing_bars`
- **AND** `error.message` SHALL 包含字串 `"9999"`

#### Scenario: 引擎 ok=false 仍存 row
- **GIVEN** 通過外部驗證但 `run_backtest` 回 envelope `{ok: false, error: {code:"INVALID_INPUT", message:"warmup not satisfied"}, ...}`
- **WHEN** POST 該 input
- **THEN** 回應狀態碼 SHALL 為 200
- **AND** `data.status` SHALL 等於 `"failed"`
- **AND** `backtest_jobs` 中 SHALL 多一筆 row、status="failed"、result_json 內含 `error` key

---

### Requirement: `GET /api/admin/backtest/jobs` 分頁列表
系統 SHALL 接受 query 參數 `limit`（預設 20，clamp 至 [1, 100]）。回應 200 與 `data = {items: array<JobSummary>, count: number}`，依 `created_at DESC` 排序。`JobSummary` SHALL 為：
```
{
  id: string,
  strategy: string,
  period_from: string,
  period_to: string,
  status: 'completed' | 'failed',
  elapsed_ms: number,
  created_at: string,
  // 衍生欄位（從 result_json.metrics 解出，failed 時為 null）
  annual_return_pct: number | null,
  sharpe: number | null,
  max_drawdown_pct: number | null,
  win_rate_pct: number | null
}
```

`result_json` 本身 SHALL **不**回到 list（避免 payload 爆炸）；只在 detail endpoint 回。

#### Scenario: 空表
- **WHEN** `backtest_jobs` 為空、客戶端 GET `/api/admin/backtest/jobs`
- **THEN** 回應狀態碼 SHALL 為 200
- **AND** `data.items` SHALL 等於 `[]`
- **AND** `data.count` SHALL 等於 `0`

#### Scenario: 排序
- **GIVEN** 表內三筆 jobs 分別 created_at `2026-05-01T10:00:00+08:00`、`2026-05-08T10:00:00+08:00`、`2026-05-04T10:00:00+08:00`
- **WHEN** 客戶端 GET `/api/admin/backtest/jobs`
- **THEN** `data.items[0].created_at` SHALL 等於 `"2026-05-08T10:00:00+08:00"`
- **AND** `data.items[2].created_at` SHALL 等於 `"2026-05-01T10:00:00+08:00"`

#### Scenario: limit clamp
- **WHEN** 客戶端 GET `/api/admin/backtest/jobs?limit=500`
- **THEN** 回應狀態碼 SHALL 為 200
- **AND** `data.items.length` SHALL ≤ 100

#### Scenario: failed job 衍生欄位為 null
- **GIVEN** 表內一筆 status="failed" 的 row
- **WHEN** 客戶端 GET `/api/admin/backtest/jobs`
- **THEN** 該 item 的 `annual_return_pct`、`sharpe`、`max_drawdown_pct`、`win_rate_pct` SHALL 皆為 `null`

#### Scenario: list 不回 result_json
- **WHEN** 客戶端 GET `/api/admin/backtest/jobs`
- **THEN** 任一 item SHALL 不包含 `result_json` 或 `equity_curve` 或 `trades` 等大欄位

---

### Requirement: `GET /api/admin/backtest/jobs/{job_id}` 完整回傳
系統 SHALL 在 row 存在時回 200 與 `data = JobDetail`：
```
{
  id, strategy, period_from, period_to, custom_symbols: string[],
  initial_capital, status, elapsed_ms, created_at,
  metrics: { annual_return_pct, sharpe, max_drawdown_pct, win_rate_pct, ... } | null,
  equity_curve: array<{date: string, equity: number}>,    // failed → []
  drawdown:     array<{date: string, dd: number}>,        // failed → []，dd 為 ≤0 的 pct
  trades:       array<BacktestTrade>,                     // failed → []
  error: { code, message } | null                         // completed → null
}
```

`BacktestTrade` SHALL 為 `{entry_date, exit_date, symbol, side, qty, entry_price, exit_price, pnl_twd, hold_days, pattern?}`，欄位由引擎 `result_json.trades` 經 light normalization 而來。`drawdown` 序列由系統從 `equity_curve` 即時計算（每點 = `equity / max(equity前綴) - 1`），不在 result_json 中持久化。

不存在的 `job_id` SHALL 回 404 `error.code = "not_found"`。

#### Scenario: 不存在
- **WHEN** 客戶端 GET `/api/admin/backtest/jobs/0123456789abcdef0123456789abcdef`
- **THEN** 回應狀態碼 SHALL 為 404
- **AND** `error.code` SHALL 為 `not_found`

#### Scenario: completed 完整回傳
- **GIVEN** 表內一筆 completed row、`result_json` 內含至少 1 筆 trade 與 ≥ 5 個 equity points
- **WHEN** 客戶端 GET 該 `id`
- **THEN** 回應狀態碼 SHALL 為 200
- **AND** `data.metrics` SHALL 不為 `null`
- **AND** `data.equity_curve.length` SHALL ≥ 5
- **AND** `data.drawdown.length` SHALL 等於 `data.equity_curve.length`
- **AND** `data.trades.length` SHALL ≥ 1
- **AND** `data.error` SHALL 為 `null`

#### Scenario: drawdown 計算正確
- **GIVEN** `equity_curve = [{equity:100},{equity:120},{equity:90},{equity:150}]`
- **WHEN** 客戶端 GET 該 job
- **THEN** `data.drawdown[0].dd` SHALL 等於 `0`
- **AND** `data.drawdown[1].dd` SHALL 等於 `0`
- **AND** `data.drawdown[2].dd` SHALL 在 `-0.25 ± 1e-6` 範圍內
- **AND** `data.drawdown[3].dd` SHALL 等於 `0`

#### Scenario: failed job
- **GIVEN** 表內一筆 status="failed" row
- **WHEN** 客戶端 GET 該 `id`
- **THEN** 回應狀態碼 SHALL 為 200
- **AND** `data.metrics` SHALL 為 `null`
- **AND** `data.equity_curve` SHALL 等於 `[]`
- **AND** `data.trades` SHALL 等於 `[]`
- **AND** `data.error.code` SHALL 為非空字串

---

### Requirement: 不洩漏內部路徑或 SQL 片段
所有錯誤回應 SHALL 不含 `/Users/`、`/home/`、絕對路徑、`SELECT`、`INSERT`、`Traceback`、Python tracebacks。Generic 500 SHALL 用 `{code: "internal_error", message: "internal server error"}`。

#### Scenario: 內部例外
- **GIVEN** 處理器內 `INSERT` 拋出 `RuntimeError("/Users/secret/db corrupt: SELECT * FROM backtest_jobs")`
- **WHEN** 客戶端 POST `/api/admin/backtest/run` 觸發此例外
- **THEN** 回應狀態碼 SHALL 為 500
- **AND** body 字串化後 SHALL 不包含 `/Users/`
- **AND** body 字串化後 SHALL 不包含 `SELECT`
- **AND** body 字串化後 SHALL 不包含 `Traceback`
