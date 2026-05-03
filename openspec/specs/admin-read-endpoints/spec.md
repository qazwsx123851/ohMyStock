# admin-read-endpoints Specification

## Purpose
TBD - created by archiving change read-side-admin-endpoints-v0. Update Purpose after archive.
## Requirements
### Requirement: 統一 success/error envelope、auth gate、per-request connection 沿用

本 capability 的所有端點 SHALL 沿用 `server-action-endpoints` 與 `web-admin-bearer-auth` 已建立的不變式：

- 成功回應 SHALL 為 `HTTP 200` + body `{"ok": true, "data": <object>}`，由 `ohmystock.api.routes._envelope.to_success(...)` 構造。
- 錯誤回應 SHALL 為 `{"ok": false, "error": {"code": "<snake_case>", "message": "<human msg>"}}`，由 `ohmystock.api.routes._envelope.to_error(...)` 或 `map_exception_to_envelope(...)` 構造。`ValueError` → 400 `invalid_input`；其他例外 → 500 `internal_error` 並 strip 原訊息。
- 任何 `/api/admin/*` 端點 SHALL 透過 FastAPI `Depends(require_admin)` 強制 Bearer token；缺 token → 401 `auth_missing`、token 不符 → 401 `auth_invalid`（envelope 由 `app.py` 的 `AuthError` exception handler 統一映射，本 capability 自身不再實作）。
- 每個請求 SHALL 透過 `Depends(get_db)` 取得獨立 `sqlite3.Connection`，並在 handler return / raise 後保證關閉。Handler SHALL **不**使用 module-level 全域 connection。
- 任何端點的 error body SHALL **不**含絕對檔案路徑（`/Users/`、`/home/`、`C:\\`）、SQL 字串字面量、stack trace（`Traceback`），亦 SHALL **不**包含環境變數值。

#### Scenario: 缺 Authorization header 一律 401 `auth_missing`
- **GIVEN** TestClient + `create_app()`、`OHMYSTOCK_ADMIN_TOKEN` 設為合法 token
- **WHEN** 對 `GET /api/admin/journal/rows`、`GET /api/admin/journal/decisions/x`、`GET /api/admin/positions/open`、`GET /api/admin/stats/today` 任一發 request **不**帶 `Authorization` header
- **THEN** HTTP status 為 401；body `["ok"] is False`、`["error"]["code"] == "auth_missing"`

#### Scenario: 同 endpoint 連呼兩次拿到不同 connection 物件
- **GIVEN** 一個 spy on `ohmystock.api.db.get_connection`、TestClient + `create_app()` + valid Bearer
- **WHEN** 連續發 2 次 `GET /api/admin/stats/today`
- **THEN** spy 至少被呼叫 2 次；每次回傳的 `sqlite3.Connection` 用 `is` 比較為 `False`

#### Scenario: handler 拋例外時 connection 仍被關閉
- **GIVEN** monkeypatch 讓任一本 capability 端點內部 raise `RuntimeError("boom")`、spy on `Connection.close`
- **WHEN** 帶 valid Bearer 呼叫該端點
- **THEN** response 為 500 envelope；`Connection.close` 在該請求生命週期內 SHALL 至少被呼叫 1 次

#### Scenario: 未捕獲例外 fallback 為 `internal_error` 且不洩漏訊息
- **GIVEN** monkeypatch 讓 endpoint raise `RuntimeError("/Users/secret/path failed: SELECT * FROM journal_entries WHERE token='abc'")`
- **WHEN** 帶 valid Bearer 呼叫該端點
- **THEN** HTTP status 為 500；body `["error"]["code"] == "internal_error"`；`["error"]["message"]` SHALL **不**含子字串 `"/Users/"`、`"SELECT"`、`"token='abc'"`、`"Traceback"`

---

### Requirement: GET /api/admin/journal/rows — 分頁列表 + 過濾

系統 SHALL 提供 `GET /api/admin/journal/rows` 端點。Query string 接受所有選填欄位：

- `kind: str | None`（合法值僅為 `"entry" | "exit" | "reject" | "expire" | "auto_execute_audit"`；其他 → 400 `invalid_input`）
- `symbol: str | None`（exact match，case-sensitive）
- `date_from: str | None`（`"YYYY-MM-DD"`）
- `date_to: str | None`（`"YYYY-MM-DD"`）
- `limit: int | None`（預設 100；`> 500` SHALL 靜默 clamp 至 500；`<= 0` → 400 `invalid_input`）
- `offset: int | None`（預設 0；`< 0` → 400 `invalid_input`）

Handler SHALL：

1. 將過濾條件轉成參數化 SQL：`SELECT id, decision_id, kind, symbol, created_at, payload_json FROM journal_entries WHERE <filters> ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?`
2. 在同一 connection 對相同 filter 執行 `SELECT COUNT(*) FROM journal_entries WHERE <filters>` 取得 `total`
3. `payload_json` 欄位 SHALL 以 `json.loads(...)` 還原為 dict，序列化到 JSON 時直接內嵌（而非當字串）
4. 回 HTTP 200 + envelope `{"ok": true, "data": {"items": [...], "total": int, "limit": int_effective, "offset": int_effective, "has_more": bool}}`

`date_from > date_to` SHALL 回 400 `invalid_input`（純字串字典序比較即可，因為兩者皆 `YYYY-MM-DD` 格式）。`date_from` / `date_to` 格式不合法（如 `"2026/13/40"`）SHALL 回 400 `invalid_input`。

每筆 `items[i]` 為 dict，keys 等於 `{"id", "decision_id", "kind", "symbol", "created_at", "payload"}`；`payload` 為原始 `payload_json` 解析後的 dict（非字串）。

#### Scenario: 空表回 items=[] 且 total=0
- **GIVEN** 乾淨 schema、`journal_entries` 無任何 row
- **WHEN** 帶 valid Bearer 發 `GET /api/admin/journal/rows`
- **THEN** HTTP 200；body `["data"]["items"] == []`、`["data"]["total"] == 0`、`["data"]["limit"] == 100`、`["data"]["offset"] == 0`、`["data"]["has_more"] is False`

#### Scenario: 三筆 row 按 created_at DESC, id DESC 排序回傳
- **GIVEN** journal 內三筆 row：`(kind="entry", symbol="2330", created_at="2026-05-01T09:00:00+08:00")`、`(kind="exit", symbol="2330", created_at="2026-05-02T09:00:00+08:00")`、`(kind="entry", symbol="2454", created_at="2026-05-02T09:00:00+08:00")`
- **WHEN** 帶 valid Bearer 發 `GET /api/admin/journal/rows`
- **THEN** HTTP 200；`["data"]["items"]` 長度 3；第一筆與第二筆的 `created_at` 同為 `"2026-05-02T09:00:00+08:00"` 且其 `id` 較大者排在更前；最後一筆 `kind="entry"`、`symbol="2330"`、`created_at="2026-05-01T09:00:00+08:00"`

#### Scenario: kind=entry 過濾只回 entry rows
- **GIVEN** journal 內 entry / exit / reject 各一筆
- **WHEN** 發 `GET /api/admin/journal/rows?kind=entry`
- **THEN** HTTP 200；`items` 長度 1；唯一一筆 `kind == "entry"`；`total == 1`

#### Scenario: 不合法 kind 回 400 `invalid_input`
- **WHEN** 發 `GET /api/admin/journal/rows?kind=fill`
- **THEN** HTTP 400；`["error"]["code"] == "invalid_input"`

#### Scenario: limit > 500 silently clamps to 500
- **GIVEN** journal 內 600 筆 entry row
- **WHEN** 發 `GET /api/admin/journal/rows?limit=1000`
- **THEN** HTTP 200；`len(items) == 500`；`["data"]["limit"] == 500`（echo 後的 effective 值）；`total == 600`；`has_more is True`

#### Scenario: limit=0 回 400
- **WHEN** 發 `GET /api/admin/journal/rows?limit=0`
- **THEN** HTTP 400；`["error"]["code"] == "invalid_input"`

#### Scenario: offset 翻頁 + has_more 正確
- **GIVEN** journal 內 250 筆 row
- **WHEN** 發 `GET /api/admin/journal/rows?limit=100&offset=200`
- **THEN** HTTP 200；`len(items) == 50`；`total == 250`；`has_more is False`

#### Scenario: date_from > date_to 回 400
- **WHEN** 發 `GET /api/admin/journal/rows?date_from=2026-05-10&date_to=2026-05-01`
- **THEN** HTTP 400；`["error"]["code"] == "invalid_input"`

#### Scenario: payload_json 還原為 nested dict
- **GIVEN** journal 一筆 row，`payload_json` 為 `'{"actual_entry_price": 600.0, "stop_loss": 580.0}'`
- **WHEN** 發 `GET /api/admin/journal/rows`
- **THEN** `["data"]["items"][0]["payload"]` 為 dict、`payload["actual_entry_price"] == 600.0`、`payload["stop_loss"] == 580.0`（不是字串）

---

### Requirement: GET /api/admin/journal/decisions/{decision_id} — 單一決策完整路徑

系統 SHALL 提供 `GET /api/admin/journal/decisions/{decision_id}` 端點。`decision_id` 為 path parameter（非空字串）。

Handler SHALL：

1. 執行 `SELECT id, decision_id, kind, symbol, created_at, payload_json FROM journal_entries WHERE decision_id = ? ORDER BY created_at ASC, id ASC`
2. 若無任何 row → HTTP 404 + `{"error": {"code": "not_found", "message": "decision_id <x> not found"}}`
3. 否則回 HTTP 200 + `{"ok": true, "data": {"decision_id": str, "rows": [...]}}`，`rows` 元素 schema 與 `journal/rows` 的 `items` 一致（含解析後的 `payload` dict）

#### Scenario: 不存在的 decision_id 回 404
- **WHEN** 帶 valid Bearer 發 `GET /api/admin/journal/decisions/missing-id`
- **THEN** HTTP 404；`["error"]["code"] == "not_found"`

#### Scenario: 一筆 entry → rows 長度 1
- **GIVEN** journal 內單筆 `kind=entry, decision_id="d1", symbol="2330"` row
- **WHEN** 發 `GET /api/admin/journal/decisions/d1`
- **THEN** HTTP 200；`["data"]["decision_id"] == "d1"`；`["data"]["rows"]` 長度 1；唯一 row `kind == "entry"` 且 `symbol == "2330"`

#### Scenario: entry + exit + auto_execute_audit 三筆按 created_at ASC 排序
- **GIVEN** 同一 `decision_id="d1"` 三筆 row：`(kind="auto_execute_audit", created_at="2026-05-01T09:00:00+08:00")`、`(kind="entry", created_at="2026-05-01T09:00:01+08:00")`、`(kind="exit", created_at="2026-05-03T13:00:00+08:00")`
- **WHEN** 發 `GET /api/admin/journal/decisions/d1`
- **THEN** HTTP 200；`["data"]["rows"]` 長度 3；順序為 `["auto_execute_audit", "entry", "exit"]`

#### Scenario: 空字串 decision_id 不 match 任何 route 而由 FastAPI 回 404
- **WHEN** 發 `GET /api/admin/journal/decisions/`（trailing 為空）
- **THEN** HTTP 404（FastAPI default route-not-found，不需本 capability 自定 envelope）

---

### Requirement: GET /api/admin/positions/open — 開倉中部位列表

系統 SHALL 提供 `GET /api/admin/positions/open` 端點。無 query string 參數。

Handler SHALL：

1. 取 `now_iso = datetime.now(ZoneInfo("Asia/Taipei")).isoformat()`、`today_date = datetime.now(TPE).date()`
2. 呼叫 `ohmystock.journal.repository.open_positions(conn, asof=now_iso)` 取得 `list[OpenPosition]`
3. 對 candidate `decision_id` 集合執行單次 bulk 查詢 `SELECT decision_id, payload_json FROM journal_entries WHERE kind='entry' AND decision_id IN (?, ?, ...)`，將 `payload_json` 解析為 dict 並 keyed 於 `decision_id`
4. 將每筆 `OpenPosition` 序列化為 dict：keys 等於 `{"decision_id", "symbol", "sector", "entry_price", "qty_lots", "entry_ts", "hold_days", "stop_loss", "t1_target", "time_stop_date"}`
   - `hold_days = (today_date - date.fromisoformat(entry_ts[:10])).days`，最小值為 0（同日進場 → 0）
   - `stop_loss` / `t1_target` / `time_stop_date` 從 payload 取出，若 key 不存在 SHALL 為 `None`（JSON `null`）
5. 回 HTTP 200 + `{"ok": true, "data": {"items": [...], "asof_iso": str, "count": int}}`，`asof_iso` 為步驟 1 的 `now_iso`、`count == len(items)`

`items` 順序 SHALL 沿用 `open_positions` 回傳順序（按 entry `created_at` ASC）。

#### Scenario: 無開倉部位回 items=[]
- **GIVEN** 乾淨 journal
- **WHEN** 帶 valid Bearer 發 `GET /api/admin/positions/open`
- **THEN** HTTP 200；`["data"]["items"] == []`、`["data"]["count"] == 0`、`["data"]["asof_iso"]` 為含 `+08:00` 的 ISO 字串

#### Scenario: 一筆已 fill、未 exit 的部位回傳含 stop_loss / t1_target
- **GIVEN** journal 一筆 entry row：`decision_id="d1"`、`symbol="2330"`、`created_at="2026-05-01T09:30:00+08:00"`、`payload_json` 含 `actual_entry_price=600.0, actual_qty=1, stop_loss=580.0, t1_target=660.0, time_stop_date="2026-06-01"`；無對應 exit row
- **WHEN** 發 `GET /api/admin/positions/open`（assume today = `2026-05-03`）
- **THEN** HTTP 200；`items` 長度 1；唯一 row `decision_id == "d1"`、`symbol == "2330"`、`entry_price == 600.0`、`qty_lots == 1`、`stop_loss == 580.0`、`t1_target == 660.0`、`time_stop_date == "2026-06-01"`、`hold_days == 2`

#### Scenario: payload 缺 stop_loss → 該欄為 null
- **GIVEN** journal 一筆 entry row 已 fill，`payload_json` 僅含 `actual_entry_price` 與 `actual_qty`，無 `stop_loss` / `t1_target` / `time_stop_date`
- **WHEN** 發 `GET /api/admin/positions/open`
- **THEN** HTTP 200；該 row `stop_loss is None`、`t1_target is None`、`time_stop_date is None`

#### Scenario: 已 exit 的決策不再列為 open
- **GIVEN** journal 內 entry + 對應 exit row（同一 `decision_id`），entry 已 fill
- **WHEN** 發 `GET /api/admin/positions/open`
- **THEN** HTTP 200；`items == []`；`count == 0`

#### Scenario: 尚未 fill 的 entry（pending_confirm）不列為 open
- **GIVEN** journal 一筆 entry row，`payload_json` 無 `actual_entry_price`（仍為 pending_confirm）
- **WHEN** 發 `GET /api/admin/positions/open`
- **THEN** HTTP 200；`items == []`（`open_positions` repository 已過濾此情況）

---

### Requirement: GET /api/admin/stats/today — 當日 KPI 計數器

系統 SHALL 提供 `GET /api/admin/stats/today` 端點。無 query string 參數。

Handler SHALL：

1. 取 `today_str = datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()`（格式 `"YYYY-MM-DD"`）
2. 執行單一 SQL 聚合查詢，使用 6 個 `COALESCE(SUM(CASE WHEN ... THEN 1 ELSE 0 END), 0)` 對 `journal_entries` 篩選 `substr(created_at, 1, 10) = today_str`
3. 回 HTTP 200 + `{"ok": true, "data": {"asof_date": str, "decisions_made": int, "entries_pending": int, "entries_filled": int, "rejects": int, "expires": int, "auto_execute_audits": int}}`

定義：
- `decisions_made` = `kind='entry'` row 總數
- `entries_pending` = `kind='entry'` 且 `payload_json` 無 `actual_entry_price` 的 row 數
- `entries_filled` = `kind='entry'` 且 `payload_json` 含非 null `actual_entry_price` 的 row 數
- `rejects` = `kind='reject'` row 數
- `expires` = `kind='expire'` row 數
- `auto_execute_audits` = `kind='auto_execute_audit'` row 數

`decisions_made == entries_pending + entries_filled`（同一日內的不變式）。

#### Scenario: 空表回所有計數器為 0
- **GIVEN** 乾淨 journal
- **WHEN** 帶 valid Bearer 發 `GET /api/admin/stats/today`
- **THEN** HTTP 200；body `["data"]["asof_date"]` 為 `"YYYY-MM-DD"` 字串；`decisions_made == 0`、`entries_pending == 0`、`entries_filled == 0`、`rejects == 0`、`expires == 0`、`auto_execute_audits == 0`（皆為 int 0，非 null）

#### Scenario: 今日 1 entry pending + 1 entry filled + 1 reject
- **GIVEN** today = `2026-05-03`；journal 三筆 row：(a) `kind='entry'`、`created_at="2026-05-03T09:00:00+08:00"`、payload 無 `actual_entry_price`；(b) `kind='entry'`、`created_at="2026-05-03T09:30:00+08:00"`、payload `actual_entry_price=600.0`；(c) `kind='reject'`、`created_at="2026-05-03T10:00:00+08:00"`
- **WHEN** 發 `GET /api/admin/stats/today`
- **THEN** HTTP 200；`decisions_made == 2`、`entries_pending == 1`、`entries_filled == 1`、`rejects == 1`

#### Scenario: 昨日的 row 不計入
- **GIVEN** today = `2026-05-03`；journal 一筆 `kind='entry'`、`created_at="2026-05-02T23:59:00+08:00"`、payload `actual_entry_price=600.0`
- **WHEN** 發 `GET /api/admin/stats/today`
- **THEN** HTTP 200；`decisions_made == 0`、`entries_filled == 0`

#### Scenario: 跨午夜 TPE 邊界正確切日
- **GIVEN** today (TPE) = `2026-05-03`；journal 一筆 `kind='entry'`、`created_at="2026-05-03T00:00:01+08:00"`、payload `actual_entry_price=600.0`
- **WHEN** 發 `GET /api/admin/stats/today`
- **THEN** HTTP 200；`decisions_made == 1`、`entries_filled == 1`（`substr(created_at, 1, 10) == "2026-05-03"` 命中）

#### Scenario: auto_execute_audit row 計入專屬計數器
- **GIVEN** today = `2026-05-03`；journal 兩筆 `kind='auto_execute_audit'` row 皆於今日 created_at
- **WHEN** 發 `GET /api/admin/stats/today`
- **THEN** HTTP 200；`auto_execute_audits == 2`；`decisions_made == 0`（audit row 不算 entry）

---

### Requirement: 4 個 router 註冊在 create_app()

`ohmystock.api.app.create_app()` SHALL 在現有 `screener_router / confirm_gate_router / exit_engine_router` 之外，再 `include_router` 三個本 capability 的 router：`journal_router`（覆蓋 `journal/rows` + `journal/decisions/{id}` 兩個 path）、`positions_router`（`positions/open`）、`stats_router`（`stats/today`）。三個 router SHALL 全部使用 `prefix="/api/admin"` 與 `dependencies=[Depends(require_admin)]`，與既有寫端點完全一致。

#### Scenario: TestClient 對四個 path 都拿到非 404 route-not-found
- **GIVEN** valid `OHMYSTOCK_ADMIN_TOKEN`、TestClient + `create_app()` + valid Bearer
- **WHEN** 對 `GET /api/admin/journal/rows`、`GET /api/admin/journal/decisions/x`（不存在）、`GET /api/admin/positions/open`、`GET /api/admin/stats/today` 各發一次 request
- **THEN** 每個 response body 都是合法 JSON 含 `"ok"` key（個別端點本身的 404 邏輯仍允許，例如 `decisions/x` 會回 404 `not_found` envelope；但這代表 route 已註冊、未走 FastAPI default 404）

