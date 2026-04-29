# cli-and-config Specification

## Purpose
TBD - created by archiving change scaffold-repo. Update Purpose after archive.
## Requirements
### Requirement: Python 套件可被 import

系統 SHALL 提供名為 `ohmystock` 的 Python 套件，安裝後可被 `import ohmystock` 成功 import，且具備 17 個子模組（依 `docs/design-zh-TW.md` §4 的模組邊界：`agent`、`skills`、`tools`、`backtest`、`paper`、`memory`、`swarm`、`api`、`strategies`、`data`、`safety`、`observability`、`decider`、`journal`、`review`、`proposal`、`eventbus`），每個子模組在本 change 階段為空模組（只有 `__init__.py`，不含任何業務邏輯）。

#### Scenario: 安裝完成後可 import 根套件
- **WHEN** 在已安裝環境執行 `python -c "import ohmystock"`
- **THEN** 命令以 exit code 0 結束，stderr 無 `ImportError` / `ModuleNotFoundError`

#### Scenario: 17 個子模組可被 import
- **WHEN** 在已安裝環境執行 `python -c "import ohmystock.agent, ohmystock.skills, ohmystock.tools, ohmystock.backtest, ohmystock.paper, ohmystock.memory, ohmystock.swarm, ohmystock.api, ohmystock.strategies, ohmystock.data, ohmystock.safety, ohmystock.observability, ohmystock.decider, ohmystock.journal, ohmystock.review, ohmystock.proposal, ohmystock.eventbus"`
- **THEN** 命令以 exit code 0 結束

#### Scenario: 子模組為空殼
- **WHEN** 任意子模組 X 被 import
- **THEN** 該模組的 `dir(ohmystock.X)` 不包含本 change 範圍以外的 public symbol（即僅有 Python builtin dunder 與來自空 `__init__.py` 的內容）

---

### Requirement: 套件管理採用 `uv` 與 PEP 621

系統 SHALL 使用 `uv` 作為 package manager，並透過 PEP 621 規範的 `pyproject.toml` 宣告套件 metadata 與相依。本 change 階段宣告 Python 版本下限為 3.11，生產相依為空，dev 相依僅含 `pytest`。後續 change 在需要時新增其他相依（如 `fastapi`、`shioaji`、`anthropic` 等）。

#### Scenario: `uv sync` 成功安裝
- **WHEN** 在乾淨環境執行 `uv sync`
- **THEN** 命令以 exit code 0 結束，產生 `.venv/` 與 `uv.lock`

#### Scenario: Python 版本約束
- **WHEN** 嘗試在 Python < 3.11 環境執行 `uv sync`
- **THEN** `uv` 拒絕安裝並提示版本不符

#### Scenario: 採用 src layout
- **WHEN** 檢查 `pyproject.toml` 套件配置
- **THEN** 套件根對應 `src/ohmystock/`（非 repo root 的 `ohmystock/`）

---

### Requirement: 環境變數契約由 `.env.example` 揭露

系統 SHALL 在 repo root 提供 `.env.example` 檔，列出 v1 已知所有環境變數的 key 與預設值（值可為空字串、`false` 或文件預設）。真實 secret 不得進入 git；`.env.example` 為跨 change 共享的環境變數命名權威。後續 change 若需新增 env var，SHALL 同時更新 `.env.example`。

依據 `docs/safety-and-simulation.md` §2.9（`OHMYSTOCK_AUTO_EXECUTE`）、`docs/v3-decisions.md` #15（`OHMYSTOCK_LLM_DEGRADE`）、`docs/design-zh-TW.md` §4.11.2（Shioaji 認證欄）、§5.1（FinMind token）。

#### Scenario: `.env.example` 包含必要 key
- **WHEN** 讀取 `.env.example`
- **THEN** 檔案至少包含以下 key：`ANTHROPIC_API_KEY`、`SHIOAJI_API_KEY`、`SHIOAJI_SECRET_KEY`、`SHIOAJI_CA_PATH`、`SHIOAJI_CA_PASSWD`、`SHIOAJI_PERSON_ID`、`FINMIND_TOKEN`、`OHMYSTOCK_AUTO_EXECUTE`、`OHMYSTOCK_LLM_DEGRADE`、`OHMYSTOCK_DB_PATH`、`OHMYSTOCK_LOG_LEVEL`

#### Scenario: 預設值不含真實 secret
- **WHEN** 讀取 `.env.example` 任何一行的 value
- **THEN** value 為空字串、`false`、或不可被當成有效 API key 使用的 placeholder（如 `~/.ohmystock/journal.db` 路徑、`INFO` log level）

#### Scenario: 真實 `.env` 不進 git
- **WHEN** 在 repo root 建立 `.env`
- **THEN** `git status` 不會列出 `.env` 為 untracked 或 modified（被 `.gitignore` 忽略）

---

### Requirement: 開發任務入口由 `Makefile` 提供

系統 SHALL 在 repo root 提供 `Makefile`，包含 `install` / `lint` / `test` 三個 target。每個 target 內容為對 `uv` 對應命令的 thin wrapper（或在 lint 尚未配置時 echo 訊息）。Solo dev 也可不透過 `make`，直接執行對應 `uv` 命令。

#### Scenario: `make install` 等同 `uv sync`
- **WHEN** 執行 `make install`
- **THEN** 命令成功完成 `uv sync` 等價動作

#### Scenario: `make test` 等同 `uv run pytest`
- **WHEN** 執行 `make test`
- **THEN** 命令呼叫 `uv run pytest`（即使無測試案例，pytest 仍應 exit 0 或 5—no tests collected）

#### Scenario: `make lint` 在尚未配置 linter 時不阻塞
- **WHEN** 在 `cli-skeleton` 之前 change 執行 `make lint`
- **THEN** 命令 exit 0 並 echo「lint not configured yet」或等價訊息（不視為錯誤）

---

### Requirement: 測試運行時不需要實際相依

系統 SHALL 確保 `pytest` 可在乾淨環境跑通而不需要 Shioaji / FinMind / Anthropic 任一實際 API 連線。本 change 階段 `tests/` 為空殼（只有 `__init__.py` 與 `conftest.py`），後續 change 加入測試時 SHALL 維持此性質：integration test 使用 marker 區隔，預設不執行需要外部連線的測試。

#### Scenario: 空 `pytest` 不會失敗
- **WHEN** 在已安裝環境執行 `uv run pytest`
- **THEN** exit code 為 0 或 5（pytest 表示 no tests collected），無 `ImportError`

---

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

### Requirement: CLI 子命令骨架

系統 SHALL 在 `ohmystock` CLI 提供七個子命令：`run`、`backtest`、`review`、`propose`、`screen`、`api`、`smoke-test`。前五個（`run` / `backtest` / `review` / `propose` / `screen`）在當前階段 SHALL 為 stub：執行時印 `not implemented` 至 stdout 並以 exit code 1 結束，避免 shell pipeline 誤判為成功。第六個子命令 `api` SHALL **非** stub：執行時 SHALL 透過 `uvicorn` 啟動 `ohmystock.api.app:create_app` factory（dev mode 預設 `--reload`），並接受 `--host` / `--port` / `--reload / --no-reload` 旗標。第七個子命令 `smoke-test` SHALL **非** stub：執行時 SHALL 依序驗證 FinMind / Shioaji / Anthropic 三方連線（詳 `external-connectors` capability 對應 Requirement）。前五個子命令的真實邏輯由後續 change 補完（`run`：LLM Decider 主流程；`backtest`：歷史回測；`review`：Phase 5 復盤 swarm；`propose`：策略改動提案；`screen`：股票篩選）。

#### Scenario: root help 列出七個子命令
- **WHEN** 執行 `uv run ohmystock --help`
- **THEN** stdout 同時包含 `run`、`backtest`、`review`、`propose`、`screen`、`api`、`smoke-test` 七個子命令名稱

#### Scenario: 前五個子命令 stub 行為一致
- **WHEN** 執行 `uv run ohmystock <子命令>`（其中 `<子命令>` 為 `run` / `backtest` / `review` / `propose` / `screen` 任一）
- **THEN** 命令以 exit code 1 結束，stdout 包含字串 `not implemented`

#### Scenario: 子命令各自有 help
- **WHEN** 執行 `uv run ohmystock <子命令> --help`（七者任一）
- **THEN** 命令以 exit code 0 結束，stdout 包含該子命令的說明文字（不為空字串、不為 generic placeholder）

#### Scenario: api 子命令不為 stub
- **WHEN** 執行 `uv run ohmystock api --help`
- **THEN** 命令以 exit code 0 結束，stdout 不含字串 `not implemented`，且至少包含 `--host` 與 `--port` 兩個旗標名稱

#### Scenario: smoke-test 子命令不為 stub
- **WHEN** 執行 `uv run ohmystock smoke-test --help`
- **THEN** 命令以 exit code 0 結束，stdout 不含字串 `not implemented`，且包含 `finmind`、`shioaji`、`anthropic` 三個字串（大小寫不敏感）

---

### Requirement: smoke-test 子命令的非 stub 行為由 external-connectors capability 主管

系統 SHALL 將 `smoke-test` 子命令的執行細節（呼叫順序、PASS/FAIL 格式、各項目失敗時的 exit code 行為）交由 `external-connectors` capability 中對應 Requirement 定義；本 capability 僅約束「子命令存在於 CLI 且非 stub」。任何對 smoke-test 行為的修改 SHALL 走 `external-connectors` 的 spec delta 流程，不得透過修改 `cli-and-config` 描述變更實際行為。

#### Scenario: smoke-test 子命令出現在 ohmystock --help
- **WHEN** 執行 `uv run ohmystock --help`
- **THEN** stdout 包含 `smoke-test` 字串（與其他六個子命令同列）

#### Scenario: smoke-test 行為定義落在 external-connectors
- **WHEN** 檢視 `openspec/specs/external-connectors/spec.md`（archive 後）
- **THEN** 該檔 SHALL 含一條 Requirement 命名為「smoke-test CLI 子命令驗證三方連線」（或語意等價）

---

### Requirement: `api` 子命令啟動 FastAPI server

系統 SHALL 在 `ohmystock` CLI 提供 `api` 子命令，透過 `uvicorn` 啟動 `ohmystock.api.app:create_app`（factory mode）。子命令 SHALL 接受以下旗標：

- `--host`（預設 `127.0.0.1`，僅綁 loopback 避免 LAN 暴露）
- `--port`（預設 `8000`）
- `--reload / --no-reload`（dev 預設 `--reload`，prod-like 跑請傳 `--no-reload`）

子命令 SHALL **不**接受 `--workers` 旗標（v1 限制單 worker，多 worker 計畫於 v2 改 Redis pub/sub，依 `docs/backend-eventbus.md` §10）。本 change 階段 `api` 子命令 SHALL 為唯一啟動 FastAPI 的入口；不提供 module-level `app` 物件供 `uvicorn ohmystock.api.app:app` 直接呼叫（強制 factory mode）。

#### Scenario: `ohmystock api --help` 列旗標
- **WHEN** 執行 `uv run ohmystock api --help`
- **THEN** 命令以 exit code 0 結束，stdout 包含 `--host`、`--port`、`--reload`（或 `--no-reload`）三個旗標名稱

#### Scenario: 預設 host / port
- **WHEN** 檢視 `api` 子命令的旗標預設值（透過 typer help 或內部 introspection）
- **THEN** `--host` 預設值為 `127.0.0.1`，`--port` 預設值為 `8000`

#### Scenario: server 真的能啟動並回應 `/healthz`
- **WHEN** 在背景執行 `uv run ohmystock api --no-reload --port <free_port>`，等待 server 啟動後對 `http://127.0.0.1:<free_port>/healthz` 發 GET 請求，再 ctrl-C / SIGTERM 結束 server
- **THEN** GET 請求收到 HTTP 200，response 為 JSON 含 `"status":"ok"`；server 收到 SIGTERM 後在合理時間內（≤ 5 秒）退出

---

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

