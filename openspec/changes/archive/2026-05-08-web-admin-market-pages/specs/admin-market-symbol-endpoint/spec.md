## ADDED Requirements

### Requirement: 端點掛載與 auth 一致性
系統 SHALL 在 `src/ohmystock/api/routes/market.py` 提供 FastAPI router，並於 `src/ohmystock/api/app.py` 內掛載，使 `GET /api/admin/market/symbols/{symbol}` 路由生效。此 router SHALL 套用全域 `require_admin` Bearer-token dependency（與其他 admin read endpoints 一致），且 SHALL 透過 `Depends(get_db)` 取得 per-request `sqlite3.Connection`。所有回應 SHALL 走 `_envelope.to_success(...)` / `_envelope.map_exception_to_envelope(...)`，輸出 `{ok, data, error}` 信封。

#### Scenario: 未帶 Authorization header
- **WHEN** 任何客戶端對 `/api/admin/market/symbols/2330` 發 GET，但不帶 `Authorization` header
- **THEN** 回應狀態碼 SHALL 為 401
- **AND** 回應 body SHALL 為 `{"ok": false, "error": {"code": "auth_missing", ...}}`

#### Scenario: 帶錯誤 token
- **GIVEN** `OHMYSTOCK_ADMIN_TOKEN` 設定為 32 字以上的固定字串
- **WHEN** 客戶端帶 `Authorization: Bearer wrong` 發 GET
- **THEN** 回應狀態碼 SHALL 為 401
- **AND** error.code SHALL 為 `auth_invalid`

#### Scenario: 帶正確 token 且 symbol 有資料
- **GIVEN** `bars_daily` 內 `2330` 在過去 60 個交易日有 ≥ 30 筆資料
- **WHEN** 客戶端帶有效 Bearer token 發 `GET /api/admin/market/symbols/2330`
- **THEN** 回應狀態碼 SHALL 為 200
- **AND** `body.ok` SHALL 為 `true`
- **AND** `body.data.symbol` SHALL 等於 `"2330"`

---

### Requirement: 回應 schema
系統 SHALL 在 200 OK 時回傳 `data` 物件，欄位包含且僅包含：`symbol: string`、`quote: {price: number, change: number | null, change_pct: number | null, volume: number, asof: string}`、`bars_daily: array<{date: string, open: number, high: number, low: number, close: number, volume: number}>`、`rs: {value: integer, asof: string} | null`、`sepa: {stage: integer, since: string | null} | null`、`institutional: array<{date: string, foreign: number, trust: number, dealer: number, total: number}>`、`recent_patterns: array<{ts: string, pattern: string, score: number, outcome: string}>`。所有 `date` 欄位 SHALL 為 ISO-8601 `yyyy-mm-dd`，所有 `ts` 欄位 SHALL 為帶 `+08:00` offset 的 ISO-8601 timestamp。

#### Scenario: bars_daily 排序
- **GIVEN** `bars_daily` 內 `2330` 在窗格內有 60 筆資料
- **WHEN** 對 `/api/admin/market/symbols/2330` 發 GET
- **THEN** `data.bars_daily` SHALL 包含 60 個元素
- **AND** `data.bars_daily[0].date` SHALL 早於 `data.bars_daily[59].date`（升序）

#### Scenario: quote.asof 與最新 bar 對齊
- **GIVEN** `bars_daily` 內 `2330` 最新一筆 date 為 `"2026-05-08"`，close 為 `1025.0`
- **WHEN** 對 `/api/admin/market/symbols/2330` 發 GET
- **THEN** `data.quote.price` SHALL 等於 `1025.0`
- **AND** `data.quote.asof` SHALL 等於 `"2026-05-08"`

#### Scenario: change 與 change_pct 由前兩根 bar 算
- **GIVEN** 最新兩根 bar close 為 `1025.0` 與 `1013.0`（昨日）
- **WHEN** 對 `/api/admin/market/symbols/2330` 發 GET
- **THEN** `data.quote.change` SHALL 等於 `12.0`
- **AND** `data.quote.change_pct` SHALL 在 `0.01184 ± 1e-6` 範圍內

#### Scenario: 只有一根 bar 時 change 為 null
- **GIVEN** `bars_daily` 內 `2330` 在窗格內僅有 1 筆資料
- **WHEN** 對 `/api/admin/market/symbols/2330` 發 GET
- **THEN** `data.quote.change` SHALL 為 `null`
- **AND** `data.quote.change_pct` SHALL 為 `null`

---

### Requirement: `?days=` 參數驗證與 clamp
系統 SHALL 接受 query 參數 `days` 為 1–252 之整數，預設 60。若超出範圍，回應狀態碼 SHALL 為 400 並回 `error.code = "invalid_days"`；非整數同樣回 400 或 422（FastAPI 預設）。系統 SHALL NOT 自動 clamp，而是直接拒絕（避免「靜默修改 input」）。

#### Scenario: 預設值 60
- **WHEN** 客戶端 GET `/api/admin/market/symbols/2330`（不帶 `days`）
- **THEN** `data.bars_daily.length` SHALL ≤ 60
- **AND** 後端 SHALL 至多查詢 60 個交易日

#### Scenario: days=1
- **WHEN** 客戶端 GET `/api/admin/market/symbols/2330?days=1`
- **THEN** 回應狀態碼 SHALL 為 200
- **AND** `data.bars_daily.length` SHALL ≤ 1

#### Scenario: days=252
- **WHEN** 客戶端 GET `/api/admin/market/symbols/2330?days=252`
- **THEN** 回應狀態碼 SHALL 為 200

#### Scenario: days=253
- **WHEN** 客戶端 GET `/api/admin/market/symbols/2330?days=253`
- **THEN** 回應狀態碼 SHALL 為 400
- **AND** `error.code` SHALL 為 `invalid_days`

#### Scenario: days=0
- **WHEN** 客戶端 GET `/api/admin/market/symbols/2330?days=0`
- **THEN** 回應狀態碼 SHALL 為 400
- **AND** `error.code` SHALL 為 `invalid_days`

#### Scenario: days 非整數
- **WHEN** 客戶端 GET `/api/admin/market/symbols/2330?days=foo`
- **THEN** 回應狀態碼 SHALL 為 400 或 422
- **AND** body SHALL 為 `{ok: false, error: {...}}` 信封

---

### Requirement: 404 僅由 `bars_daily` 缺資料觸發
系統 SHALL 在 `bars_daily` 對該 symbol 在請求窗格內為 0 筆資料時，回應 404 並 `error.code = "market_symbol_not_found"`。RS / SEPA / institutional / recent_patterns 任一為空 SHALL NOT 觸發 404。

#### Scenario: bars_daily 無此 symbol
- **GIVEN** `bars_daily` 表內無任何 `symbol = "9999"` 的列
- **WHEN** 客戶端 GET `/api/admin/market/symbols/9999`
- **THEN** 回應狀態碼 SHALL 為 404
- **AND** `error.code` SHALL 為 `market_symbol_not_found`

#### Scenario: 有 bars 但 RS / 法人 / patterns 全空
- **GIVEN** `bars_daily` 有 `2330` 60 筆，`rs_rating_cache` 無 `2330`，chip 表無 `2330`，`journal_entries` 無 pattern 列
- **WHEN** 客戶端 GET `/api/admin/market/symbols/2330`
- **THEN** 回應狀態碼 SHALL 為 200
- **AND** `data.rs` SHALL 為 `null`
- **AND** `data.institutional` SHALL 等於 `[]`
- **AND** `data.recent_patterns` SHALL 等於 `[]`

---

### Requirement: SEPA 階段以最新 bars 即時分類
系統 SHALL 從本次回傳的 `bars_daily` 序列直接呼叫 `ohmystock.sepa.stage.classify_stage(bars)` 計算 stage。若 `bars_daily` 數量不足 `classify_stage` 所需最小資料量導致其拋例外或回 `None`，`data.sepa` SHALL 為 `null`。若分類成功，`data.sepa.stage` SHALL 為整數 1..4，`data.sepa.since` 可為 `null`（短期內無變更紀錄時）。

#### Scenario: 60 根 bars 足以分類
- **GIVEN** `bars_daily` 有 `2330` 60 筆且 `classify_stage` 對該序列回傳 `StageResult(stage=2)`
- **WHEN** 對端點發 GET
- **THEN** `data.sepa.stage` SHALL 等於 `2`

#### Scenario: bars 不足
- **GIVEN** `bars_daily` 在窗格內僅 5 筆，`classify_stage` 拋例外或回 `None`
- **WHEN** 對端點發 GET
- **THEN** `data.sepa` SHALL 為 `null`
- **AND** 回應狀態碼 SHALL 為 200

---

### Requirement: RS rating 從 `rs_rating_cache` 取最新一筆
系統 SHALL 從 `rs_rating_cache` 表 `WHERE symbol = ? ORDER BY asof_date DESC LIMIT 1` 取得 RS rating；存在則 `data.rs = {value, asof}`，不存在則 `data.rs = null`。系統 SHALL NOT 在請求路徑上重新計算 RS。

#### Scenario: 有快取
- **GIVEN** `rs_rating_cache` 內 `(symbol="2330", asof_date="2026-05-08", rs_rating=92)` 為最新列
- **WHEN** 對端點發 GET
- **THEN** `data.rs.value` SHALL 等於 `92`
- **AND** `data.rs.asof` SHALL 等於 `"2026-05-08"`

#### Scenario: 無快取
- **GIVEN** `rs_rating_cache` 內無 `symbol = "2330"` 任何列
- **WHEN** 對端點發 GET
- **THEN** `data.rs` SHALL 為 `null`

---

### Requirement: 三大法人最近 5 個交易日（fail-soft）
系統 SHALL 提供 `data.institutional` 為陣列，內含該 symbol 最近不超過 5 個交易日的法人買賣超列；空表回 `[]` 不報錯。每列欄位 SHALL 為 `{date, foreign, trust, dealer, total}`，數值單位為「張」（lots）。`total` SHALL 等於 `foreign + trust + dealer`。

#### Scenario: 有 5 日資料
- **WHEN** 對端點發 GET 且 chip 表內 `2330` 最近 5 個交易日皆有資料
- **THEN** `data.institutional.length` SHALL 等於 `5`
- **AND** 每列 `total` SHALL 等於 `foreign + trust + dealer`
- **AND** `data.institutional[0].date` SHALL 是其中最早的日期，`data.institutional[4].date` SHALL 是最新的（升序）

#### Scenario: 部分天數空
- **GIVEN** chip 表內 `2330` 僅最近 3 個交易日有資料
- **WHEN** 對端點發 GET
- **THEN** `data.institutional.length` SHALL 等於 `3`

#### Scenario: 完全空
- **GIVEN** chip 表內無 `2330` 任何列
- **WHEN** 對端點發 GET
- **THEN** `data.institutional` SHALL 等於 `[]`
- **AND** 回應狀態碼 SHALL 為 200

---

### Requirement: 近 30 日 pattern 列（fail-soft）
系統 SHALL 從 `journal_entries` 取出 `kind` 屬於 pattern-detection 類別、`symbol = ?` 且 `ts` 在最近 30 個日曆日內的列，依 `ts DESC` 排列，至多 20 列。每列輸出欄位 SHALL 為 `{ts, pattern, score, outcome}`。`outcome` 計算規則：若該 pattern row 對應同 symbol 後續存在 `kind="exit"` row，則 `outcome` 為 `"{+/-}{X}% 出場"`；若存在 `kind="entry"` row 但無 `exit`，則 `outcome` 為 `"{+/-}{X}% 持有中"`（百分比以最新 `bars_daily` close 為準）；其他為 `"未進場"`。

#### Scenario: 無 pattern
- **GIVEN** `journal_entries` 內無 `2330` 任何 pattern row
- **WHEN** 對端點發 GET
- **THEN** `data.recent_patterns` SHALL 等於 `[]`

#### Scenario: 有 1 筆未進場 pattern
- **GIVEN** `journal_entries` 內 `2330` 在 7 天前有 1 筆 pattern row、score=0.86，且無對應 entry row
- **WHEN** 對端點發 GET
- **THEN** `data.recent_patterns.length` SHALL 等於 `1`
- **AND** `data.recent_patterns[0].outcome` SHALL 等於 `"未進場"`

#### Scenario: 有 entry + exit 配對
- **GIVEN** pattern row 後 1 日有 `kind="entry"` row、entry_price=1000；3 日後 `kind="exit"` row、exit_price=1025
- **WHEN** 對端點發 GET
- **THEN** `data.recent_patterns[0].outcome` SHALL 包含 `"+2.5"`（容許 ±0.05 表示誤差）
- **AND** `outcome` SHALL 包含 `"出場"`

#### Scenario: 有 entry 無 exit
- **GIVEN** pattern row 後 1 日有 `kind="entry"` row、entry_price=1000；無 exit row；最新 close 為 1020
- **WHEN** 對端點發 GET
- **THEN** `data.recent_patterns[0].outcome` SHALL 包含 `"持有中"`

#### Scenario: 30 日窗外
- **GIVEN** 唯一 pattern row 在 35 日前
- **WHEN** 對端點發 GET
- **THEN** `data.recent_patterns` SHALL 等於 `[]`
