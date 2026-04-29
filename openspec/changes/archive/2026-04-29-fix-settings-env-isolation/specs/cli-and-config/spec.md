## MODIFIED Requirements

### Requirement: 設定檔載入器

系統 SHALL 提供 `ohmystock.config.Settings` 類別（基於 `pydantic-settings.BaseSettings`），自動從 `.env`（若存在）與環境變數載入 v1 已知所有 env var。所有欄位 SHALL 有預設值（空字串、`None`、`false`、或文件預設），`Settings()` 在缺所有 env var 的情境下 SHALL 不拋例外。後續 change 在使用實際 secret 時自行檢核存在性，不在 import 時要求。

依據 `.env.example`（archive `2026-04-27-scaffold-repo` 寫入）的 11 個 key：`ANTHROPIC_API_KEY`、`SHIOAJI_API_KEY`、`SHIOAJI_SECRET_KEY`、`SHIOAJI_CA_PATH`、`SHIOAJI_CA_PASSWD`、`SHIOAJI_PERSON_ID`、`FINMIND_TOKEN`、`OHMYSTOCK_AUTO_EXECUTE`、`OHMYSTOCK_LLM_DEGRADE`、`OHMYSTOCK_DB_PATH`、`OHMYSTOCK_LOG_LEVEL`。

驗證 zero-env 行為的 unit test SHALL 主動構造 isolated 環境（透過 pydantic-settings 的 `_env_file=None` 參數跳過 `.env` 載入，並透過 pytest `monkeypatch.delenv` 清掉 11 個 env var key），不假設 repo 工作目錄不存在 `.env`。原因：Phase 0d archive 後 repo root 必有真實 `.env` 才能跑 `ohmystock smoke-test`，依賴「執行環境本身為空」會與 smoke-test 前提衝突。

#### Scenario: `Settings()` 在 isolated env 中可建構（無 `.env` 載入、無 env var）
- **WHEN** test 透過 `monkeypatch.delenv` 清掉 11 個 env var key（`raising=False`），然後執行 `from ohmystock.config import Settings; s = Settings(_env_file=None)`
- **THEN** import 成功，`s` 為 `Settings` 實例，無例外拋出，且 `s.anthropic_api_key is None`、`s.ohmystock_log_level == "INFO"`、`s.ohmystock_db_path == "~/.ohmystock/journal.db"`

#### Scenario: `Settings` 欄位涵蓋 `.env.example` 全部 key
- **WHEN** 檢視 `Settings` 類別
- **THEN** 類別欄位（或 `model_fields`）名稱集合 SHALL 包含 `.env.example` 列出的全部 11 個 env var key（大小寫處理依 pydantic-settings 預設：env var 名稱大寫，欄位可為 lower-case 並由 `model_config` 自動對映）

#### Scenario: `.env` 中設定的值會被讀取
- **WHEN** 在 repo root 建立 `.env` 含 `ANTHROPIC_API_KEY=test-value-not-real`，然後執行 `Settings()`
- **THEN** `Settings().anthropic_api_key`（或對應屬性）等於 `test-value-not-real`
