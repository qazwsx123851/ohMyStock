## Purpose

Defines the Bearer token gate that protects every `/api/admin/*` route (REST + SSE) of the ohMyStock backend. Owns the `require_admin` FastAPI dependency, the startup-time validation of `OHMYSTOCK_ADMIN_TOKEN` (fail-fast in `create_app()`), the 401 envelope shape (`auth_missing` / `auth_invalid`), the constant-time token comparison rule, and the `Settings.ohmystock_admin_token` field. `GET /healthz` stays open. This capability is the single source of truth for admin authentication in v0; downstream capabilities (`server-action-endpoints`, `backend-api-and-eventbus`) simply attach `Depends(require_admin)` and inherit the 401 mapping.

## Requirements

### Requirement: 啟動時驗證 OHMYSTOCK_ADMIN_TOKEN（fail-fast）

系統 SHALL 在 `ohmystock.api.app.create_app()` 內、`FastAPI` 實例 return 之前，呼叫 `ohmystock.api.auth._validate_admin_token(settings)` 對 `Settings.ohmystock_admin_token` 進行驗證：

- 若值為 `None` 或空字串 → SHALL raise `RuntimeError`，message SHALL 包含字串 `"OHMYSTOCK_ADMIN_TOKEN must be set"` 與字串 `"32"`（用以提示使用者最小長度與產生指令）。
- 若值為非空字串但 `len(token) < 32` → SHALL raise `RuntimeError`，同上 message 規範。
- 若值為非空字串且 `len(token) >= 32` → SHALL 通過驗證、`create_app()` 正常 return。

驗證 SHALL 在 admin 路由註冊之前執行，確保任何 admin 端點不會在缺 token 的情況下被掛上 app。

#### Scenario: 未設 token 時 create_app() 拒絕啟動
- **GIVEN** `OHMYSTOCK_ADMIN_TOKEN` 環境變數未設或為空字串
- **WHEN** 呼叫 `create_app()`
- **THEN** raise `RuntimeError`，`str(exc)` 包含 `"OHMYSTOCK_ADMIN_TOKEN must be set"` 且包含 `"32"`

#### Scenario: token 太短拒絕啟動
- **GIVEN** `OHMYSTOCK_ADMIN_TOKEN="too-short"`（長度 9）
- **WHEN** 呼叫 `create_app()`
- **THEN** raise `RuntimeError`，message 包含 `"32"`

#### Scenario: 合法 token 順利啟動
- **GIVEN** `OHMYSTOCK_ADMIN_TOKEN` 為長度 ≥ 32 的字串
- **WHEN** 呼叫 `create_app()`
- **THEN** 正常 return `FastAPI` 實例、不 raise

---

### Requirement: require_admin dependency 檢查 Bearer token

系統 SHALL 在 `ohmystock.api.auth` 模組提供 FastAPI dependency `require_admin(authorization: str | None = Header(None)) -> None`。dependency SHALL：

- 當 `authorization` 為 `None`、空字串、或不以 `"Bearer "` 開頭（含大小寫、含空白變體 `"bearer "` 視為**無效**） → raise `AuthError(code="auth_missing", message="Missing or malformed Authorization header")`。
- 當 `authorization` 形如 `"Bearer <token>"` 但 `<token>` 與 `Settings.ohmystock_admin_token` 不相等 → raise `AuthError(code="auth_invalid", message="Invalid admin token")`。token 比對 SHALL 使用 `secrets.compare_digest`（constant-time comparison），不得使用 `==`。
- 當 token 相等 → 正常 return `None`。

`AuthError` SHALL 為一個自訂 exception class（位於 `ohmystock.api.auth`），含 `code: str` 與 `message: str` 兩個屬性。

#### Scenario: 缺 Authorization header
- **GIVEN** request 不帶 `Authorization` header
- **WHEN** 任一掛 `Depends(require_admin)` 的端點被呼叫
- **THEN** raise `AuthError`，`code == "auth_missing"`

#### Scenario: 錯誤 scheme（Basic 而非 Bearer）
- **GIVEN** request header `Authorization: Basic dXNlcjpwYXNz`
- **WHEN** 任一掛 `Depends(require_admin)` 的端點被呼叫
- **THEN** raise `AuthError`，`code == "auth_missing"`

#### Scenario: token 不符
- **GIVEN** `Settings.ohmystock_admin_token == "valid-token-32-characters-or-more-xxx"`、request header `Authorization: Bearer wrong-token-32-characters-or-more-zz`
- **WHEN** 端點被呼叫
- **THEN** raise `AuthError`，`code == "auth_invalid"`

#### Scenario: token 相符
- **GIVEN** `Settings.ohmystock_admin_token == "valid-token-32-characters-or-more-xxx"`、request header `Authorization: Bearer valid-token-32-characters-or-more-xxx`
- **WHEN** 端點被呼叫
- **THEN** dependency return `None`、handler 正常執行

#### Scenario: 比對使用 secrets.compare_digest
- **GIVEN** monkeypatch `secrets.compare_digest` 改為一個 spy
- **WHEN** request 帶任意 Bearer token 觸發 `require_admin`
- **THEN** spy 至少被呼叫一次；`==` 比對在 token 比較段不被使用（可由 spy `call_count >= 1` 確認）

---

### Requirement: AuthError 經 envelope handler 映射為 401

`ohmystock.api.routes._envelope` 的 exception handler SHALL 在 `AuthError` 被 raise 時，回 HTTP 401 + body `{"ok": false, "error": {"code": <auth_missing|auth_invalid>, "message": <human-readable>}}`，與其他 admin error 共用同一個 envelope 形狀（`server-action-endpoints` capability 的 envelope invariants）。response body SHALL **不**包含 `Authorization` header 原值、SHALL **不**包含 stack trace。

#### Scenario: auth_missing 回 401 + envelope
- **WHEN** 對 `POST /api/admin/screener/run` 不帶 Authorization header 發請求
- **THEN** HTTP 401；body `["ok"] is False`；`["error"]["code"] == "auth_missing"`；body 不含 stack trace、不含絕對檔案路徑

#### Scenario: auth_invalid 回 401 + envelope
- **WHEN** 對 `POST /api/admin/screener/run` 帶 `Authorization: Bearer wrong-token-32-characters-or-more-zz` 發請求
- **THEN** HTTP 401；`["error"]["code"] == "auth_invalid"`

#### Scenario: 401 body 不洩漏 token 原值
- **GIVEN** `Settings.ohmystock_admin_token == "valid-token-32-characters-or-more-xxx"`
- **WHEN** 對任一 admin 端點帶 `Authorization: Bearer wrong-token-32-characters-or-more-zz` 發請求
- **THEN** response body 字串不含 `"valid-token-32-characters-or-more-xxx"`、不含 `"wrong-token-32-characters-or-more-zz"`

---

### Requirement: 全部 /api/admin/* 端點掛 require_admin

系統 SHALL 在 `create_app()` 註冊以下端點時掛上 `Depends(require_admin)`，使其所有路由都通過 `require_admin` 檢查：

- `GET /api/admin/events`（SSE）
- `POST /api/admin/screener/run`
- `GET /api/admin/confirm-gate/pending`
- `POST /api/admin/confirm-gate/confirm`
- `POST /api/admin/confirm-gate/reject`
- `POST /api/admin/confirm-gate/sweep-expired`
- `POST /api/admin/exit-engine/run`

`GET /healthz` SHALL **不**掛 `require_admin`（保留 liveness probe 不需 token）。

實作上 SHALL 在三個 admin router (`screener_router`, `confirm_gate_router`, `exit_engine_router`) 的 `APIRouter(...)` 建構參數加入 `dependencies=[Depends(require_admin)]`，並在 `/api/admin/events` 端點的 decorator 加入 `dependencies=[Depends(require_admin)]`。

#### Scenario: /healthz 不需 token
- **WHEN** `GET /healthz` 不帶任何 Authorization header
- **THEN** HTTP 200；body `["status"] == "ok"`

#### Scenario: 每個 admin 端點都拒絕無 token request
- **GIVEN** 上述 7 個 admin 端點清單
- **WHEN** 對每個端點以對應 method 不帶 Authorization header 發 request
- **THEN** 每個 response HTTP status 為 401；`["error"]["code"] == "auth_missing"`

#### Scenario: SSE 端點同樣需 token
- **WHEN** `GET /api/admin/events` 不帶 Authorization header
- **THEN** HTTP 401（不為 200、不進入 streaming）；`["error"]["code"] == "auth_missing"`

#### Scenario: 帶合法 token 後所有 admin 端點正常工作
- **GIVEN** valid token 已注入 fixture
- **WHEN** 對 `POST /api/admin/screener/run` 帶 `Authorization: Bearer <valid>` 發合法 body
- **THEN** HTTP 200；`["ok"] is True`

---

### Requirement: Settings 新增 ohmystock_admin_token 欄位

`ohmystock.config.Settings` SHALL 新增欄位 `ohmystock_admin_token: str | None = None`，對應環境變數 `OHMYSTOCK_ADMIN_TOKEN`（pydantic-settings case-insensitive 規則）。預設 `None` 確保 `Settings()` 在 token 未設時仍可建構（不破壞 CLI / 測試 import 路徑）；實際拒絕啟動的責任落在 `create_app()` 的 `_validate_admin_token` 上（見上文）。

#### Scenario: env 未設時 Settings() 仍可建構
- **GIVEN** `OHMYSTOCK_ADMIN_TOKEN` 未設
- **WHEN** 執行 `Settings()`
- **THEN** 不 raise；`settings.ohmystock_admin_token is None`

#### Scenario: env 設值時欄位被讀入
- **GIVEN** `OHMYSTOCK_ADMIN_TOKEN="abcdefghijklmnopqrstuvwxyz0123456"`（33 chars）
- **WHEN** 執行 `Settings()`
- **THEN** `settings.ohmystock_admin_token == "abcdefghijklmnopqrstuvwxyz0123456"`

---

### Requirement: 端點不洩漏 token 或環境變數值

本 capability 涵蓋的所有 401 response SHALL **不**包含：

- `Settings.ohmystock_admin_token` 的值（即使是 prefix / suffix 片段也禁止）
- request 帶來的 token 原值（若有）
- Python stack trace（`Traceback (most recent call last):`、`File "...", line ...`）
- 絕對檔案路徑（`/Users/...`、`/home/...`）

延伸 `server-action-endpoints` capability 的「端點不洩漏內部路徑或 settings 值」requirement 至本 capability 涵蓋的 401 path。

#### Scenario: 401 body 不含 stack trace
- **WHEN** 任一 admin 端點 raise `AuthError`
- **THEN** response body 字串不含 `"Traceback"`、不含 `"File \""`

#### Scenario: 401 body 不含絕對路徑
- **WHEN** 任一 admin 端點 raise `AuthError`
- **THEN** response body 字串不含 `"/Users/"`、不含 `"/home/"`、不含 `".py\", line "`
