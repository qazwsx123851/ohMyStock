## MODIFIED Requirements

### Requirement: 套件 console-script 入口已預留

系統 SHALL 在 `pyproject.toml` 宣告 `ohmystock` console-script entry point，指向 `ohmystock.cli:main`，且該模組 SHALL 已實作（`ohmystock.cli.main` 為可呼叫物件，內部委派至 `typer.Typer` app）。執行 `ohmystock --help` SHALL 成功並列印 root help（不再 `ModuleNotFoundError`）。本 change 將原 spec 中「該符號可不存在」的暫態升級為「該符號必須存在且可執行」。

#### Scenario: entry point 已宣告
- **WHEN** 讀取 `pyproject.toml` 的 `[project.scripts]` 區塊
- **THEN** 包含 `ohmystock = "ohmystock.cli:main"`（或字面等價符號）

#### Scenario: entry point 可執行
- **WHEN** 在已安裝環境執行 `uv run ohmystock --help`
- **THEN** 命令以 exit code 0 結束，stdout 包含 typer 自動生成的 root help 文字（含 `Usage:` 與所有子命令名稱）；stderr 不含 `ModuleNotFoundError` / `AttributeError`

#### Scenario: `main()` 為公開可呼叫物件
- **WHEN** 在 Python REPL 執行 `from ohmystock.cli import main`
- **THEN** import 成功，`callable(main)` 為 `True`

---

## ADDED Requirements

### Requirement: CLI 子命令骨架

系統 SHALL 在 `ohmystock` CLI 提供五個子命令骨架：`run`、`backtest`、`review`、`propose`、`screen`。每個子命令在本 change 階段為 stub：執行時印 `not implemented` 至 stdout 並以 exit code 1 結束，避免 shell pipeline 誤判為成功。子命令的真實邏輯由後續 change 補完（`run`：LLM Decider 主流程；`backtest`：歷史回測；`review`：Phase 5 復盤 swarm；`propose`：策略改動提案；`screen`：股票篩選）。

#### Scenario: root help 列出五個子命令
- **WHEN** 執行 `uv run ohmystock --help`
- **THEN** stdout 同時包含 `run`、`backtest`、`review`、`propose`、`screen` 五個子命令名稱

#### Scenario: 子命令 stub 行為一致
- **WHEN** 執行 `uv run ohmystock <子命令>`（其中 `<子命令>` 為五者任一）
- **THEN** 命令以 exit code 1 結束，stdout 包含字串 `not implemented`

#### Scenario: 子命令各自有 help
- **WHEN** 執行 `uv run ohmystock <子命令> --help`
- **THEN** 命令以 exit code 0 結束，stdout 包含該子命令的說明文字（不為空字串、不為 generic placeholder）

---

### Requirement: 設定檔載入器

系統 SHALL 提供 `ohmystock.config.Settings` 類別（基於 `pydantic-settings.BaseSettings`），自動從 `.env`（若存在）與環境變數載入 v1 已知所有 env var。所有欄位 SHALL 有預設值（空字串、`None`、`false`、或文件預設），`Settings()` 在缺所有 env var 的情境下 SHALL 不拋例外。後續 change 在使用實際 secret 時自行檢核存在性，不在 import 時要求。

依據 `.env.example`（archive `2026-04-27-scaffold-repo` 寫入）的 11 個 key：`ANTHROPIC_API_KEY`、`SHIOAJI_API_KEY`、`SHIOAJI_SECRET_KEY`、`SHIOAJI_CA_PATH`、`SHIOAJI_CA_PASSWD`、`SHIOAJI_PERSON_ID`、`FINMIND_TOKEN`、`OHMYSTOCK_AUTO_EXECUTE`、`OHMYSTOCK_LLM_DEGRADE`、`OHMYSTOCK_DB_PATH`、`OHMYSTOCK_LOG_LEVEL`。

#### Scenario: `Settings()` 在無 `.env` 與無 env var 時可建構
- **WHEN** 在乾淨環境（無 `.env`、無相關 env var）執行 `from ohmystock.config import Settings; s = Settings()`
- **THEN** import 成功，`s` 為 `Settings` 實例，無例外拋出

#### Scenario: `Settings` 欄位涵蓋 `.env.example` 全部 key
- **WHEN** 檢視 `Settings` 類別
- **THEN** 類別欄位（或 `model_fields`）名稱集合 SHALL 包含 `.env.example` 列出的全部 11 個 env var key（大小寫處理依 pydantic-settings 預設：env var 名稱大寫，欄位可為 lower-case 並由 `model_config` 自動對映）

#### Scenario: `.env` 中設定的值會被讀取
- **WHEN** 在 repo root 建立 `.env` 含 `ANTHROPIC_API_KEY=test-value-not-real`，然後執行 `Settings()`
- **THEN** `Settings().anthropic_api_key`（或對應屬性）等於 `test-value-not-real`
