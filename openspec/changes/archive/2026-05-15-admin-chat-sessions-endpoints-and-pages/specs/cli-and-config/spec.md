## ADDED Requirements

### Requirement: Settings 加入 chat_model_default 與 chat_title_model 欄位

系統 SHALL 在 `Settings` 加入兩個 string 欄位：

- `chat_model_default: str = "claude-sonnet-4-6"` — 預設用於 `ChatAgent` 主對話
- `chat_title_model: str = "claude-haiku-4-5-20251001"` — 預設用於 `autogen_title` 自動標題

兩個欄位 SHALL：
- 為 fail-safe 預設值（即使環境變數未設，Settings() 也能成功建構）
- 接受 `OHMYSTOCK_CHAT_MODEL_DEFAULT` / `OHMYSTOCK_CHAT_TITLE_MODEL` env override（case-insensitive，沿用 pydantic-settings 既有設定）
- 不可為空字串 — `@field_validator` 拒絕 trim 後為空的值

`get_settings_view()` (即 `/api/admin/settings` GET 回傳的 redactor) SHALL 把這 2 個 key 加入白名單回傳（與其他非 secret 欄位同樣以原值呈現，無遮罩）。

#### Scenario: 預設值正確
- **WHEN** 在無 .env 環境執行 `Settings()`
- **THEN** `.chat_model_default == "claude-sonnet-4-6"`
- **AND** `.chat_title_model == "claude-haiku-4-5-20251001"`

#### Scenario: env override 生效
- **GIVEN** 環境變數 `OHMYSTOCK_CHAT_MODEL_DEFAULT=claude-opus-4-7`
- **WHEN** `Settings()`
- **THEN** `.chat_model_default == "claude-opus-4-7"`

#### Scenario: 空字串拒絕
- **GIVEN** 環境變數 `OHMYSTOCK_CHAT_MODEL_DEFAULT=`（空字串）
- **WHEN** `Settings()`
- **THEN** SHALL 拋 pydantic `ValidationError`

#### Scenario: /api/admin/settings 揭露兩個欄位
- **WHEN** authenticated `GET /api/admin/settings`
- **THEN** response data 含 key `chat_model_default` 與 `chat_title_model`
- **AND** 兩者的 value 為當前 Settings 值（無 mask）
