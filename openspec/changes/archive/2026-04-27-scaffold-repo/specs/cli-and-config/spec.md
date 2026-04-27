## ADDED Requirements

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

系統 SHALL 在 `pyproject.toml` 宣告 `ohmystock` console-script entry point，指向 `ohmystock.cli:main` 或等價符號。本 change 階段該符號可不存在（後續 change `cli-skeleton` 會實作 `ohmystock.cli`），但 `pyproject.toml` 的宣告 SHALL 已就位，避免後續 change 改動 packaging metadata。

#### Scenario: entry point 已宣告
- **WHEN** 讀取 `pyproject.toml` 的 `[project.scripts]` 區塊
- **THEN** 包含 `ohmystock = "ohmystock.cli:main"`（或字面等價符號）

#### Scenario: entry point 失敗不阻塞 install
- **WHEN** 安裝完成後執行 `ohmystock --help`
- **THEN** 即使 `ohmystock.cli` 模組尚未實作而報錯，`uv sync` 與 `import ohmystock` 仍 SHALL 成功（即 entry point 失敗不阻塞套件安裝）
