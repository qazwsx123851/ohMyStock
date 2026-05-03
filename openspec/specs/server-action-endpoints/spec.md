## Purpose

Defines the v0 admin server-action HTTP endpoints under `/api/admin/*` that wrap the existing screener / confirm-gate / exit-engine business logic in a single FastAPI router with a unified success/error envelope, per-request `sqlite3.Connection` lifecycle, and no auth (Bearer auth is layered on later by `web-admin-bearer-auth`). Owns the spec invariants for envelope shape, HTTP status mapping, sensitive-data redaction, and which capabilities each endpoint delegates to.

## Requirements

### Requirement: 統一 success / error envelope 與 HTTP status mapping

本 capability 涵蓋的所有端點 SHALL 使用以下 JSON envelope：

- **Success**：HTTP 200，body 形如 `{"ok": true, "data": <object>}`，`data` 內容由各 endpoint 自定。
- **Error**：HTTP 4xx/5xx（依下表），body 形如 `{"ok": false, "error": {"code": "<machine_code>", "message": "<human msg>"}}`。`code` 必為 ASCII snake_case 字串，`message` 為人類可讀英文或繁中字串。

| 異常來源 | error.code | HTTP status |
|---|---|---|
| screener envelope `code="invalid_input"` | `"invalid_input"` | 400 |
| screener envelope `code="data_unavailable"` | `"data_unavailable"` | 503 |
| screener envelope `code="upstream_error"` | `"upstream_error"` | 502 |
| `ConfirmGateError(code="not_found")` | `"not_found"` | 404 |
| `ConfirmGateError(code="not_pending")` | `"not_pending"` | 409 |
| `ConfirmGateError(code="payload_invalid")` | `"payload_invalid"` | 409 |
| `ConfirmGateError(code="broker_failed")` | `"broker_failed"` | 502 |
| `ExitEngineError(code="market_data_unavailable")` | `"market_data_unavailable"` | 503 |
| `ValueError`（router 內 / Pydantic 驗證 422 例外） | `"invalid_input"` | 400 |
| 任何其他 `Exception`（fallback） | `"internal_error"` | 500 |

任何端點的 error body SHALL **不**回傳 stack trace、SQL 字串、檔案絕對路徑、或環境變數值。

#### Scenario: 成功回 envelope 形狀正確
- **GIVEN** 任一本 capability 端點走 success path
- **WHEN** 對該端點發起合法 request
- **THEN** HTTP status 為 200；response body JSON `["ok"] is True`、含 key `"data"`、不含 key `"error"`

#### Scenario: ConfirmGateError("not_found") 回 404
- **GIVEN** confirm endpoint 收到不存在的 `decision_id`
- **WHEN** 呼叫該 endpoint
- **THEN** HTTP status 為 404；body `["ok"] is False`、`["error"]["code"] == "not_found"`、`["error"]["message"]` 為非空字串

#### Scenario: ConfirmGateError("not_pending") 回 409
- **GIVEN** confirm endpoint 收到的 `decision_id` 對應的 row `decision_status != "pending_confirm"`
- **WHEN** 呼叫該 endpoint
- **THEN** HTTP status 為 409；body `["error"]["code"] == "not_pending"`

#### Scenario: 未捕獲例外 fallback 為 internal_error
- **GIVEN** monkeypatch 讓 `screen_universe()` raise `RuntimeError("boom")`
- **WHEN** 呼叫 `POST /api/admin/screener/run`
- **THEN** HTTP status 為 500；body `["error"]["code"] == "internal_error"`；`["error"]["message"]` 不含字串 `"boom"` 之外的 stack trace、不含絕對檔案路徑

#### Scenario: 錯誤 body 不洩漏 stack trace
- **GIVEN** 任一端點走 error path
- **WHEN** 取得 response body
- **THEN** body 為扁平 JSON object（無 nested traceback / `Traceback`）、不含字串 `"File \""` 或 `".py\", line "`

---

### Requirement: 每個請求自開自關 sqlite3 connection（per-request lifecycle）

本 capability 涵蓋的所有端點 SHALL 在 handler 內透過 FastAPI dependency（或等價 try/finally）取得一個新的 `sqlite3.Connection`（呼叫 `ohmystock.api.db.get_connection()`），並在 handler return / raise 後**保證關閉**該 connection。Handler SHALL **不**使用 module-level 全域 connection。

#### Scenario: 同 endpoint 連呼兩次拿到不同 connection 物件
- **GIVEN** 一個 spy on `ohmystock.api.db.get_connection`、TestClient + create_app()
- **WHEN** 連續發 2 次同樣的 request 到任一本 capability 端點（例如 `GET /api/admin/confirm-gate/pending`）
- **THEN** spy 被呼叫至少 2 次；每次回傳不同的 `sqlite3.Connection` 物件（`is` 比較為 `False`）

#### Scenario: handler 拋例外時 connection 仍關閉
- **GIVEN** 一個 endpoint 在 handler 內 raise（透過 monkeypatch 注入錯誤）、spy on `Connection.close`
- **WHEN** 呼叫該 endpoint
- **THEN** response 為 5xx envelope；`Connection.close` 在該請求生命週期內 SHALL 被呼叫至少 1 次

---

### Requirement: 全部端點維持無認證（v0 no Bearer）

本 capability 涵蓋的所有端點 SHALL 通過 `web-admin-bearer-auth` capability 的 `require_admin` dependency；不帶 token 的 request SHALL 回 HTTP 401，body 為統一 envelope `{"ok": false, "error": {"code": "auth_missing", "message": <human-readable>}}`。token 不符的 request SHALL 回 HTTP 401，`error.code == "auth_invalid"`。本 capability 自身**不**重複實作 token 比對邏輯，僅在 router 註冊時引用 `Depends(require_admin)`，由 `web-admin-bearer-auth` 的 dependency 與 envelope handler 完成 401 映射。

#### Scenario: screener endpoint 不帶 Authorization 回 401
- **WHEN** 對 `POST /api/admin/screener/run` 發 valid body 但**不**帶 `Authorization` header
- **THEN** HTTP status 為 401；body `["ok"] is False`、`["error"]["code"] == "auth_missing"`

#### Scenario: confirm endpoint 不帶 Authorization 回 401
- **WHEN** 對 `POST /api/admin/confirm-gate/confirm` 發 valid body 但**不**帶 `Authorization` header
- **THEN** HTTP status 為 401；`["error"]["code"] == "auth_missing"`

#### Scenario: 帶合法 token 端點正常運作
- **GIVEN** `Settings.ohmystock_admin_token` 設為合法 token、`Authorization: Bearer <valid>` header 帶上
- **WHEN** 對 `POST /api/admin/screener/run` 發 valid body
- **THEN** HTTP 200；走 success path；envelope shape 與本 capability 其他 success scenario 一致

---

### Requirement: POST /api/admin/screener/run

系統 SHALL 提供 `POST /api/admin/screener/run` 端點，body 為 JSON object：

- `universe: str`（必填）— `"twse" | "otc" | "all" | "custom"`
- `custom_symbols: list[str] | None`（選填，僅 `universe=="custom"` 時生效）
- `filters: list[dict[str, Any]] | None`（選填）
- `asof_date: str | None`（選填，`"YYYY-MM-DD"` 格式）

Handler SHALL：
1. 將 body 直接傳入 `ohmystock.screener.universe.screen_universe(universe=..., custom_symbols=..., filters=..., asof_date=...)`
2. 將其回傳的 `{"ok", "elapsed_ms", "data", "error"}` envelope 轉為本 capability 統一 envelope：
   - `screen_universe` 回 `ok=True` → HTTP 200，`{"ok": true, "data": {"asof_date_used": str, "candidates": list[dict], "elapsed_ms": int}}`
   - `screen_universe` 回 `ok=False, error.code="invalid_input"` → HTTP 400
   - `code="data_unavailable"` → HTTP 503
   - `code="upstream_error"` → HTTP 502
3. **不**重新 emit screener events（`screen_universe()` 內部已自帶 `screener_started` / `screener_completed` emit）

#### Scenario: 成功路徑回 200 + asof_date_used + candidates
- **GIVEN** 本機 SQLite universe snapshot 已備好 `2026-05-02` 一筆 dummy row（symbol `"2330"`, market `"TWSE"`）
- **WHEN** `POST /api/admin/screener/run` body=`{"universe": "twse", "asof_date": "2026-05-02"}`
- **THEN** HTTP 200；response body `["ok"] is True`、`["data"]["asof_date_used"] == "2026-05-02"`、`["data"]["candidates"]` 為 list、`["data"]["elapsed_ms"]` 為非負 int

#### Scenario: invalid universe 回 400
- **WHEN** `POST /api/admin/screener/run` body=`{"universe": "nonsense"}`
- **THEN** HTTP 400；body `["error"]["code"] == "invalid_input"`

#### Scenario: SSE consumer 同時收到 screener_started + screener_completed
- **GIVEN** TestClient 開啟 SSE 訂閱 `/api/admin/events`、無其他 producer
- **WHEN** 透過另一條 task 呼叫 `POST /api/admin/screener/run` 走 success path
- **THEN** SSE consumer SHALL 收到至少兩筆 events：`event: screener_started` + `event: screener_completed`，且 `screener_completed.data.payload.symbols` 為 list

---

### Requirement: GET /api/admin/confirm-gate/pending

系統 SHALL 提供 `GET /api/admin/confirm-gate/pending` 端點。Query string 接受選填 `timeout_minutes: int`；省略時 SHALL 從 `Settings.ohmystock_confirm_timeout_minutes` 取預設值。

Handler SHALL 呼叫 `ohmystock.safety.confirm_gate.list_pending(conn, timeout_minutes=...)` 並回 `{"ok": true, "data": {"items": [...], "timeout_minutes": int}}`，其中 `items` 為 `PendingEntry` 序列，每筆含 keys：`decision_id`、`symbol`、`created_at`、`age_seconds`、`ttl_seconds`、`current_price`、`final_sizing_pct`。

`timeout_minutes` 非正整數 SHALL 回 400（`error.code="invalid_input"`）。

#### Scenario: 空 pending list 回 200 + items=[]
- **GIVEN** 乾淨 journal（無任何 entry row）、settings `ohmystock_confirm_timeout_minutes=30`
- **WHEN** `GET /api/admin/confirm-gate/pending`
- **THEN** HTTP 200；body `["data"]["items"] == []`、`["data"]["timeout_minutes"] == 30`

#### Scenario: 一筆 pending_confirm 行序列化為 dict
- **GIVEN** journal 內一筆 `kind=entry, decision_status="pending_confirm"` row（symbol `"2330"`、`current_price=600.0`、`final_sizing_pct=0.05`）
- **WHEN** `GET /api/admin/confirm-gate/pending`
- **THEN** HTTP 200；`["data"]["items"]` 含一筆 dict，keys 等於 `{"decision_id","symbol","created_at","age_seconds","ttl_seconds","current_price","final_sizing_pct"}`；`symbol == "2330"`、`current_price == 600.0`、`final_sizing_pct == 0.05`

#### Scenario: timeout_minutes=0 回 400
- **WHEN** `GET /api/admin/confirm-gate/pending?timeout_minutes=0`
- **THEN** HTTP 400；`["error"]["code"] == "invalid_input"`

---

### Requirement: POST /api/admin/confirm-gate/confirm

系統 SHALL 提供 `POST /api/admin/confirm-gate/confirm` 端點，body 為 JSON object：

- `decision_id: str`（必填，非空）
- `user: str`（必填，非空）

Handler SHALL：
1. 構造 `FakePaperBroker(clock=system_clock)`（v0 不接 Shioaji；real broker 由後續 change 替換）
2. 從 settings 取 `default_capital_twd = Settings.ohmystock_default_capital_twd`
3. 呼叫 `ohmystock.safety.confirm_gate.confirm(conn, decision_id=..., broker=broker, default_capital_twd=..., user=..., auto_executed=False, clock=system_clock)`
4. Success → HTTP 200，body `{"ok": true, "data": {"decision_id": str, "fill": {"fill_price": float, "filled_qty": int, "fill_ts": str}, "qty": int}}`
5. `ConfirmGateError` 依 §1 mapping 轉 4xx/5xx envelope

`auto_executed` 永遠為 `False`（auto-execute 不透過此 endpoint 觸發）。

#### Scenario: 成功 confirm 回 fill + qty
- **GIVEN** journal 內一筆合法 pending_confirm row（symbol `"2330"`、`final_sizing_pct=0.05`、`current_price=600.0`、`atr_14_pct=2.0`）、settings `ohmystock_default_capital_twd=1_000_000`
- **WHEN** `POST /api/admin/confirm-gate/confirm` body=`{"decision_id": "<id>", "user": "mark"}`
- **THEN** HTTP 200；`["data"]["decision_id"]` 等於 request id；`["data"]["fill"]["fill_price"]` 為正浮點；`["data"]["fill"]["filled_qty"]` 為正整數、等於 `["data"]["qty"]`

#### Scenario: 不存在的 decision_id 回 404
- **WHEN** `POST /api/admin/confirm-gate/confirm` body=`{"decision_id": "missing", "user": "mark"}`
- **THEN** HTTP 404；`["error"]["code"] == "not_found"`

#### Scenario: 已 confirmed 的 row 再 confirm 回 409
- **GIVEN** journal 內一筆 `decision_status="confirmed"` row
- **WHEN** 再呼叫 confirm endpoint 帶同 `decision_id`
- **THEN** HTTP 409；`["error"]["code"] == "not_pending"`

#### Scenario: missing user 回 400
- **WHEN** `POST /api/admin/confirm-gate/confirm` body=`{"decision_id": "x", "user": ""}`
- **THEN** HTTP 400；`["error"]["code"] == "invalid_input"`

#### Scenario: SSE consumer 收到 order_sent
- **GIVEN** TestClient SSE 訂閱 + 一筆合法 pending_confirm
- **WHEN** 呼叫 confirm endpoint 走 success path
- **THEN** SSE consumer SHALL 收到一筆 `event: order_sent`，`data.payload.symbol` 等於 entry symbol

---

### Requirement: POST /api/admin/confirm-gate/reject

系統 SHALL 提供 `POST /api/admin/confirm-gate/reject` 端點，body 為 JSON object：

- `decision_id: str`（必填，非空）
- `user: str`（必填，非空）
- `reason: str`（必填，非空白）

Handler SHALL 呼叫 `ohmystock.safety.confirm_gate.reject(conn, decision_id=..., reason=..., user=..., clock=system_clock)`。

- Success → HTTP 200，body `{"ok": true, "data": {"decision_id": str, "reject_row_id": int}}`
- `ConfirmGateError` 依 §1 mapping
- `ValueError`（reason 全空白）→ HTTP 400 `invalid_input`

#### Scenario: 成功 reject 回 reject_row_id
- **GIVEN** journal 內一筆 pending_confirm row
- **WHEN** `POST /api/admin/confirm-gate/reject` body=`{"decision_id": "<id>", "user": "mark", "reason": "weak setup"}`
- **THEN** HTTP 200；`["data"]["reject_row_id"]` 為正整數

#### Scenario: empty reason 回 400
- **WHEN** body=`{"decision_id": "x", "user": "mark", "reason": "   "}`
- **THEN** HTTP 400；`["error"]["code"] == "invalid_input"`

#### Scenario: 已 rejected 的 row 再 reject 回 409
- **GIVEN** 一筆已 `decision_status="rejected"` row
- **WHEN** 再呼叫 reject endpoint
- **THEN** HTTP 409；`["error"]["code"] == "not_pending"`

---

### Requirement: POST /api/admin/confirm-gate/sweep-expired

系統 SHALL 提供 `POST /api/admin/confirm-gate/sweep-expired` 端點，body 為 JSON object：

- `timeout_minutes: int | None`（選填）— 省略時從 `Settings.ohmystock_confirm_timeout_minutes` 取預設值

Handler SHALL 呼叫 `ohmystock.safety.confirm_gate.sweep_expired(conn, timeout_minutes=..., clock=system_clock)`，回 `{"ok": true, "data": {"swept_decision_ids": list[str], "swept_count": int, "timeout_minutes": int}}`。

`timeout_minutes <= 0` SHALL 回 HTTP 400 `invalid_input`。

#### Scenario: 無 expired row 回空 list
- **GIVEN** 無任何 `created_at` 早於 `now - timeout_minutes` 的 pending_confirm row
- **WHEN** `POST /api/admin/confirm-gate/sweep-expired` body=`{}`
- **THEN** HTTP 200；`["data"]["swept_decision_ids"] == []`、`["data"]["swept_count"] == 0`

#### Scenario: 一筆 expired row 被 sweep
- **GIVEN** 一筆 pending_confirm row，`created_at` 為 `now - 60` 分鐘；timeout_minutes=30
- **WHEN** body=`{"timeout_minutes": 30}`
- **THEN** HTTP 200；`swept_decision_ids` 含該 row 的 decision_id；`swept_count == 1`

#### Scenario: timeout_minutes=-1 回 400
- **WHEN** body=`{"timeout_minutes": -1}`
- **THEN** HTTP 400；`["error"]["code"] == "invalid_input"`

---

### Requirement: POST /api/admin/exit-engine/run

系統 SHALL 提供 `POST /api/admin/exit-engine/run` 端點，body 為 JSON object：

- `asof_date: str | None`（選填，`"YYYY-MM-DD"`）— 省略時 SHALL 取 today (TPE +08:00)
- `symbol: str | None`（選填）— 省略時評估全部 confirmed positions

Handler SHALL 呼叫 `ohmystock.exit_engine.evaluator.evaluate_open_positions(conn, market_data=<lookup>, asof=<date>, clock=system_clock, symbol_filter=symbol)`，並把 `ExitResult` list 序列化：

- Success → HTTP 200，body `{"ok": true, "data": {"results": [...], "evaluated_count": int, "closed_count": int, "held_count": int, "asof_date_used": "YYYY-MM-DD"}}`
- 每筆 `result` 為 `{"decision_id": str, "action": "closed"|"held", "decision": {...} | null}`，`decision` 含 `exit_tag`、`exit_reason`、`actual_exit_price`、`pnl_pct`、`hold_days`
- `ExitEngineError("market_data_unavailable")` → HTTP 503 + `{"error": {"code": "market_data_unavailable", "message": "...", "failed_symbols": list[str]}}`
- `asof_date` 格式不合法 → HTTP 400 `invalid_input`

`market_data: MarketDataLookup` 由 router 層構造（v0 接既有 market data cache / FinMind client；可由 dependency injection override，方便測試）。

#### Scenario: 無 confirmed positions 回 evaluated_count=0
- **GIVEN** 乾淨 journal（無 confirmed entry）
- **WHEN** `POST /api/admin/exit-engine/run` body=`{"asof_date": "2026-05-02"}`
- **THEN** HTTP 200；`["data"]["evaluated_count"] == 0`、`results == []`、`closed_count == 0`、`held_count == 0`

#### Scenario: 一筆觸發 stop_loss 的 confirmed position 被關
- **GIVEN** journal 一筆 confirmed row（entry 600、stop_loss 580）；market_data 在 `2026-05-02` 回 close=575
- **WHEN** body=`{"asof_date": "2026-05-02"}`
- **THEN** HTTP 200；`results[0].action == "closed"`、`decision.exit_tag == "hit_stop_loss"`、`decision.actual_exit_price == 575`、`closed_count == 1`、`held_count == 0`

#### Scenario: market data 缺失回 503 + failed_symbols
- **GIVEN** 一筆 confirmed row（symbol `"2330"`）；market_data 對 `"2330"` 回 `None`
- **WHEN** body=`{"asof_date": "2026-05-02"}`
- **THEN** HTTP 503；`["error"]["code"] == "market_data_unavailable"`、`["error"]["failed_symbols"] == ["2330"]`

#### Scenario: 不合法 asof_date 回 400
- **WHEN** body=`{"asof_date": "2026/13/40"}`
- **THEN** HTTP 400；`["error"]["code"] == "invalid_input"`

#### Scenario: symbol filter 限縮評估範圍
- **GIVEN** 兩筆 confirmed row（`"2330"`、`"2454"`），都會觸發 stop_loss
- **WHEN** body=`{"asof_date": "2026-05-02", "symbol": "2330"}`
- **THEN** HTTP 200；`evaluated_count == 1`、唯一 result `decision_id` 對應 `"2330"`

---

### Requirement: 端點不洩漏內部路徑或 settings 值

本 capability 涵蓋的所有端點 SHALL 在任何 response body（success 或 error）中**不**包含：

- 絕對檔案路徑（`/Users/...`、`/home/...`、`C:\\...`）
- 環境變數值（`OHMYSTOCK_DB_PATH`、`OHMYSTOCK_FINMIND_TOKEN` 等）
- SQL 字串字面量
- Python stack trace（`Traceback (most recent call last):`）

#### Scenario: error response 不含絕對路徑
- **GIVEN** monkeypatch 讓 endpoint 內部觸發 error，包含絕對路徑訊息
- **WHEN** 呼叫該 endpoint
- **THEN** error message SHALL 不含子字串 `"/Users/"`、`"/home/"`、`"C:\\"`

#### Scenario: error response 不含 SQL 字串
- **GIVEN** monkeypatch DB 層 raise `sqlite3.OperationalError("near 'SELECT': syntax error")`
- **WHEN** 呼叫任一端點觸發該錯誤
- **THEN** response body 為 500 envelope；error message **不**含子字串 `"SELECT"` 或 `"INSERT"`（fallback `internal_error` 訊息為 generic）
