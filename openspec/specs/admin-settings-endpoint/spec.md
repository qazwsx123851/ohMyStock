# admin-settings-endpoint Specification

## Purpose
TBD - created by archiving change web-admin-settings-page. Update Purpose after archive.

## Requirements

### Requirement: 端點掛載與 auth/envelope 一致性
系統 SHALL 在 `src/ohmystock/api/routes/settings.py` 提供 FastAPI router，並於 `src/ohmystock/api/app.py` 內掛載，使 `GET /api/admin/settings` 路由生效。此 router SHALL 套用 `require_admin` Bearer-token dependency（與其他 admin read endpoints 一致）。所有回應 SHALL 走 `_envelope.to_success(...)` / `_envelope.map_exception_to_envelope(...)`，輸出 `{ok, data, error}` 信封。此端點 SHALL NOT 接受任何 query / body 參數，且 SHALL NOT 開放 PUT / POST / PATCH / DELETE。

#### Scenario: 未帶 Authorization header
- **WHEN** 任何客戶端對 `/api/admin/settings` 發 GET，但不帶 `Authorization` header
- **THEN** 回應狀態碼 SHALL 為 401
- **AND** 回應 body SHALL 為 `{"ok": false, "error": {"code": "auth_missing", ...}}`

#### Scenario: 帶錯誤 token
- **GIVEN** `OHMYSTOCK_ADMIN_TOKEN` 設定為 32 字以上的固定字串
- **WHEN** 客戶端帶 `Authorization: Bearer wrong` 發 GET
- **THEN** 回應狀態碼 SHALL 為 401
- **AND** error.code SHALL 為 `auth_invalid`

#### Scenario: 帶正確 token
- **GIVEN** `OHMYSTOCK_ADMIN_TOKEN` 設定為 32 字以上的固定字串、Settings 物件成功 construct
- **WHEN** 客戶端帶有效 Bearer token 發 GET
- **THEN** 回應狀態碼 SHALL 為 200
- **AND** `body.ok` SHALL 為 `true`

#### Scenario: 拒絕 PUT
- **WHEN** 客戶端帶有效 Bearer token 發 `PUT /api/admin/settings`
- **THEN** 回應狀態碼 SHALL 為 405
- **AND** body SHALL NOT mutate `Settings` 狀態

---

### Requirement: 回應 schema — 四節 grouping
系統 SHALL 在 200 OK 時回傳 `data` 物件，其欄位 SHALL 恰好為 `api_keys`、`theme`、`safety`、`breakers` 四個 key（順序不限）。各區內容如下：

- `api_keys`: `{anthropic: bool, finmind: bool, shioaji: bool}`，三個 key 皆 SHALL 存在。
- `theme`: `{mode: "system"}`（本版本固定值）。
- `safety`: `{auto_execute: bool, broker: "mock" | "shioaji-sim" | "shioaji-live"}`。
- `breakers`: `{min_confidence: number, daily_limit: integer, max_notional_pct: number, max_sizing_deviation: number, loss_lockout_hours: integer, loss_pct_threshold: number, account_equity_twd: integer}`，七個 key 皆 SHALL 存在。

回應 SHALL NOT 包含任何上述未列的 key（例如 `ohmystock_db_path`、`ohmystock_log_level`、`starting_equity_twd`、`ohmystock_decider_model`、`ohmystock_confirm_timeout_minutes` 不在本版本暴露範圍）。

#### Scenario: 預設 Settings 全四節都在
- **GIVEN** 所有 secret 欄位皆未設定（None 或空字串）、auto_execute=false、broker=shioaji-sim
- **WHEN** 對端點發 GET
- **THEN** `data` 的 keys SHALL 為 `{"api_keys", "theme", "safety", "breakers"}`
- **AND** `data.api_keys` SHALL 等於 `{"anthropic": false, "finmind": false, "shioaji": false}`
- **AND** `data.theme` SHALL 等於 `{"mode": "system"}`
- **AND** `data.safety` SHALL 等於 `{"auto_execute": false, "broker": "shioaji-sim"}`

#### Scenario: 不暴露白名單外欄位
- **WHEN** 對端點發 GET
- **THEN** `data` 物件 SHALL NOT 包含 `ohmystock_db_path`、`ohmystock_admin_token`、`anthropic_api_key`、`shioaji_secret_key`、`finmind_token` 等任何 raw `Settings` 欄位名

---

### Requirement: 秘密欄位以布林呈現（無前綴、無長度、無 hash）
系統 SHALL 將 `anthropic_api_key`、`finmind_token`、`shioaji_api_key`、`shioaji_secret_key`、`shioaji_ca_passwd`、`shioaji_person_id`、`shioaji_ca_path`、`ohmystock_admin_token` 視為 secret-bearing。`api_keys.anthropic` SHALL 為 `Settings.anthropic_api_key` 經 `.strip()` 後非空。`api_keys.finmind` 同理對應 `finmind_token`。`api_keys.shioaji` SHALL 為 `shioaji_api_key` 與 `shioaji_secret_key` 兩者皆 `.strip()` 後非空 — 任一為空時 `shioaji=false`。回應 SHALL NOT 包含任何 secret 的部分明文、最後 N 字元、長度、SHA hash 或 fingerprint。

#### Scenario: 全部已設定
- **GIVEN** `anthropic_api_key="sk-ant-test"`、`finmind_token="ft-test"`、`shioaji_api_key="sj-key"`、`shioaji_secret_key="sj-sec"`
- **WHEN** 對端點發 GET
- **THEN** `data.api_keys` SHALL 等於 `{"anthropic": true, "finmind": true, "shioaji": true}`

#### Scenario: shioaji 只設一半
- **GIVEN** `shioaji_api_key="sj-key"`、`shioaji_secret_key=""`
- **WHEN** 對端點發 GET
- **THEN** `data.api_keys.shioaji` SHALL 等於 `false`

#### Scenario: 空白字串視為未設
- **GIVEN** `anthropic_api_key="   "`（純空白）
- **WHEN** 對端點發 GET
- **THEN** `data.api_keys.anthropic` SHALL 等於 `false`

#### Scenario: 不洩漏 raw 值
- **GIVEN** `anthropic_api_key="sk-ant-deadbeefcafe1234"`
- **WHEN** 對端點發 GET 並把 response body serialize 為 string
- **THEN** body string SHALL NOT 包含 `"sk-ant"`、`"deadbeef"`、`"cafe"`、`"1234"`、或 `anthropic_api_key` 之任意連續 4 字元 substring

---

### Requirement: safety 與 breakers 直接映射 Settings 數值
系統 SHALL 在不修改、不 clamp、不四捨五入的前提下，將 `Settings` 對應欄位映射到回應：

- `safety.auto_execute` ← `ohmystock_auto_execute`
- `safety.broker` ← `ohmystock_broker`
- `breakers.min_confidence` ← `ohmystock_auto_execute_min_confidence`
- `breakers.daily_limit` ← `ohmystock_auto_execute_daily_limit`
- `breakers.max_notional_pct` ← `ohmystock_auto_execute_max_notional_pct`
- `breakers.max_sizing_deviation` ← `ohmystock_auto_execute_max_sizing_deviation`
- `breakers.loss_lockout_hours` ← `ohmystock_auto_execute_loss_lockout_hours`
- `breakers.loss_pct_threshold` ← `ohmystock_auto_execute_loss_pct_threshold`
- `breakers.account_equity_twd` ← `ohmystock_auto_execute_account_equity_twd`

#### Scenario: 預設值
- **GIVEN** 全部 auto-execute 欄位採 `Settings` 預設（min_confidence=0.7, daily_limit=5, max_notional_pct=0.25, max_sizing_deviation=0.30, loss_lockout_hours=24, loss_pct_threshold=-0.05, account_equity_twd=1_000_000）
- **WHEN** 對端點發 GET
- **THEN** `data.breakers.min_confidence` SHALL 等於 `0.7`
- **AND** `data.breakers.daily_limit` SHALL 等於 `5`
- **AND** `data.breakers.loss_pct_threshold` SHALL 等於 `-0.05`
- **AND** `data.breakers.account_equity_twd` SHALL 等於 `1000000`

#### Scenario: auto_execute=true
- **GIVEN** `OHMYSTOCK_AUTO_EXECUTE=true`、`OHMYSTOCK_BROKER=shioaji-sim`
- **WHEN** 對端點發 GET
- **THEN** `data.safety.auto_execute` SHALL 為 `true`
- **AND** `data.safety.broker` SHALL 為 `"shioaji-sim"`

#### Scenario: 非預設 breaker 值
- **GIVEN** `OHMYSTOCK_AUTO_EXECUTE_MIN_CONFIDENCE=0.85`、`OHMYSTOCK_AUTO_EXECUTE_DAILY_LIMIT=3`
- **WHEN** 對端點發 GET
- **THEN** `data.breakers.min_confidence` SHALL 等於 `0.85`
- **AND** `data.breakers.daily_limit` SHALL 等於 `3`
