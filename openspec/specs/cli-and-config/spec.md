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

系統 SHALL 在 `ohmystock` CLI 提供八個子命令：`run`、`backtest`、`review`、`propose`、`screen`、`api`、`smoke-test`、`score`。前五個（`run` / `backtest` / `review` / `propose` / `screen`）在當前階段 SHALL 為 stub：執行時印 `not implemented` 至 stdout 並以 exit code 1 結束，避免 shell pipeline 誤判為成功。第六個子命令 `api` SHALL **非** stub：執行時 SHALL 透過 `uvicorn` 啟動 `ohmystock.api.app:create_app` factory（dev mode 預設 `--reload`），並接受 `--host` / `--port` / `--reload / --no-reload` 旗標。第七個子命令 `smoke-test` SHALL **非** stub：執行時 SHALL 依序驗證 FinMind / Shioaji / Anthropic 三方連線（詳 `external-connectors` capability 對應 Requirement）。第八個子命令 `score` SHALL **非** stub：為 Typer 子命令群組（`score_app`），其下提供 `watchlist` 子命令，行為由本 capability 內「`ohmystock score watchlist` 子命令」Requirement 定義。前五個子命令的真實邏輯由後續 change 補完（`run`：LLM Decider 主流程；`backtest`：歷史回測；`review`：Phase 5 復盤 swarm；`propose`：策略改動提案；`screen`：股票篩選）。

#### Scenario: root help 列出八個子命令
- **WHEN** 執行 `uv run ohmystock --help`
- **THEN** stdout 同時包含 `run`、`backtest`、`review`、`propose`、`screen`、`api`、`smoke-test`、`score` 八個子命令名稱

#### Scenario: 前五個子命令 stub 行為一致
- **WHEN** 執行 `uv run ohmystock <子命令>`（其中 `<子命令>` 為 `run` / `backtest` / `review` / `propose` / `screen` 任一）
- **THEN** 命令以 exit code 1 結束，stdout 包含字串 `not implemented`

#### Scenario: 子命令各自有 help
- **WHEN** 執行 `uv run ohmystock <子命令> --help`（八者任一）
- **THEN** 命令以 exit code 0 結束，stdout 包含該子命令的說明文字（不為空字串、不為 generic placeholder）

#### Scenario: api 子命令不為 stub
- **WHEN** 執行 `uv run ohmystock api --help`
- **THEN** 命令以 exit code 0 結束，stdout 不含字串 `not implemented`，且至少包含 `--host` 與 `--port` 兩個旗標名稱

#### Scenario: smoke-test 子命令不為 stub
- **WHEN** 執行 `uv run ohmystock smoke-test --help`
- **THEN** 命令以 exit code 0 結束，stdout 不含字串 `not implemented`，且包含 `finmind`、`shioaji`、`anthropic` 三個字串（大小寫不敏感）

#### Scenario: score 子命令群組不為 stub
- **WHEN** 執行 `uv run ohmystock score --help`
- **THEN** 命令以 exit code 0 結束，stdout 不含字串 `not implemented`，且包含 `watchlist` 子命令名稱

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

### Requirement: `ohmystock score watchlist` 子命令

系統 SHALL 在 `ohmystock` CLI 提供 `score watchlist` 子命令，呼叫 `ohmystock.scoring.score_watchlist(asof_date, candidates, *, top_n, ...)` 並將回傳的 envelope 渲染為 stdout。子命令 SHALL 接受以下旗標：

- `--asof <YYYY-MM-DD>`（必填）— 對應 `score_watchlist` 的 `asof_date` 參數
- `--symbols <s1,s2,...>`（必填）— 逗號分隔字串，trim 後對應 `candidates` list
- `--top-n <int>`（選填，預設 None）— 對應 `top_n` 參數
- `--json / --no-json`（選填，預設 `--no-json`）— `--json` 時 stdout 為原始 envelope 的 JSON dump（`json.dumps(env, ensure_ascii=False)` + 結尾 newline），`--no-json` 時 stdout 為 CSV

CSV 輸出格式 SHALL 為：第一行 header `symbol,final_score,classification,risk_off_applied,tech,chip,fund,sent`；其後每個 candidate 一行；`final_score` SHALL 以浮點數列印（`repr` 等價，例如 `78.0` / `0.0`）；`risk_off_applied` SHALL 列印為 `true` 或 `false`（lowercase）；`tech`/`chip`/`fund`/`sent` 對應 `tech_subtotal`/`chip_subtotal`/`fund_subtotal`/`sent_subtotal`。輸出順序 SHALL 為 `final_score` 由大到小排序，並列以 `symbol` 字典序由小到大 tie-break。`--top-n` SHALL 在排序後 truncate 至前 N 筆。

當 `score_watchlist` 回傳 `ok=False` 時，子命令 SHALL 將 `error: <code>: <message>` 印至 stderr（**不**寫入 stdout），並以 exit code 1 結束。當 `ok=True` 時 SHALL 以 exit code 0 結束。

#### Scenario: `ohmystock score watchlist --help` 列旗標
- **WHEN** 執行 `uv run ohmystock score watchlist --help`
- **THEN** 命令以 exit code 0 結束，stdout 同時包含 `--asof`、`--symbols`、`--top-n`、`--json` 四個旗標名稱

#### Scenario: 成功路徑印出 CSV
- **GIVEN** `score_watchlist` 被 monkeypatch 回傳 `{"ok": True, "elapsed_ms": 12, "data": {"candidates": [{"symbol": "2330", "asof_date": "2026-04-30", "final_score": 78.0, "tech_subtotal": 30.0, "chip_subtotal": 18.0, "fund_subtotal": 25.0, "sent_subtotal": 5.0, "classification": "green", "risk_off_applied": False, "subscores": []}]}, "error": None}`
- **WHEN** 執行 `ohmystock score watchlist --asof 2026-04-30 --symbols 2330`
- **THEN** 命令以 exit code 0 結束，stdout 第一行為 `symbol,final_score,classification,risk_off_applied,tech,chip,fund,sent`，第二行為 `2330,78.0,green,false,30.0,18.0,25.0,5.0`

#### Scenario: `--json` 印出原始 envelope
- **GIVEN** `score_watchlist` 被 monkeypatch 回傳一個 `ok=True` envelope
- **WHEN** 執行 `ohmystock score watchlist --asof 2026-04-30 --symbols 2330 --json`
- **THEN** 命令以 exit code 0 結束，stdout 為合法 JSON，且 `json.loads(stdout)` 等於該 envelope

#### Scenario: `--top-n` 在排序後截斷
- **GIVEN** `score_watchlist` 被 monkeypatch 回傳兩個 candidate（`2330` final_score 70，`2317` final_score 80）
- **WHEN** 執行 `ohmystock score watchlist --asof 2026-04-30 --symbols 2330,2317 --top-n 1`
- **THEN** 命令以 exit code 0 結束，stdout 含 header 與**僅一行** `2317,...` data row（`2330` 不出現）

#### Scenario: 排序為 final_score 降序，symbol 升序 tie-break
- **GIVEN** `score_watchlist` 回傳三個 candidate：`2317` final_score 80、`2330` final_score 80、`1101` final_score 60
- **WHEN** 執行 `ohmystock score watchlist --asof 2026-04-30 --symbols 1101,2317,2330`
- **THEN** stdout data row 順序為 `2317`、`2330`、`1101`

#### Scenario: validation error 走 stderr 與 exit 1
- **GIVEN** 真實 `score_watchlist`（不 monkeypatch）
- **WHEN** 執行 `ohmystock score watchlist --asof 2026/04/30 --symbols 2330`（asof 格式錯誤）
- **THEN** 命令以 exit code 1 結束，stderr 包含字串 `INVALID_INPUT`，stdout 為空字串

#### Scenario: 缺少必填旗標
- **WHEN** 執行 `ohmystock score watchlist`（無任何旗標）
- **THEN** 命令以非 0 exit code 結束（typer usage error），stderr 包含 `--asof` 或 `--symbols` 字樣

---

### Requirement: `ohmystock decide` 子命令

系統 SHALL 在 `ohmystock` CLI 註冊 `decide` 子命令，串接 live providers 組裝的 `EntryInput` 與 `entry-decider` capability 的 `decide_entry(...)`，並把系統覆寫後的決策印至 stdout。

子命令 SHALL 接受以下旗標：

- `--symbol <s>`（必填）— 候選個股代號（4 位數字 TWSE / OTC）。
- `--asof <YYYY-MM-DD>`（必填）— 對齊 Phase 2B input assembler 的 `asof_date` 參數。
- `--json / --no-json`（選填，預設 `--no-json`）— `--json` 時 stdout 為 `OrchestrationResult` 對應 dict 的 JSON dump；`--no-json` 時 stdout 為人類可讀 summary（含 decision / force_reject_reason / cost_usd / decision_id 四行）。

行為：

1. 從 `Settings()` 讀 `decider_model`（env `OHMYSTOCK_DECIDER_MODEL`，預設 `claude-opus-4-7`）。若 `decider_model` 以 `fake://` 開頭且 env `OHMYSTOCK_ALLOW_FAKE_DECIDER` 不為 `true` → exit code 4，stderr 印 `"refused to use fake decider in non-test env"`。
2. 用既有 live providers 組 `EntryInput`（candidate / market_context / rules_digest / available_tools / available_skills）。組裝失敗 → exit code 2，stderr 印 `"entry_input_assembly_failed: <reason>"`。
3. 開或建 `OHMYSTOCK_DB_PATH` 指定的 SQLite，呼叫 `init_schema(conn)`（idempotent），呼叫 `decide_entry(...)`。
4. **enter** → exit code 0，依 `--json` 印 stdout。
5. **reject**（含 LLM 自願 reject 與系統 force_reject）→ exit code 1，依 `--json` 印 stdout。
6. **DeciderOutputParseError 或其他 internal exception** → exit code 3，stderr 印 traceback 摘要（前 5 行）。

CLI help 中 SHALL 含字面警告：`"This command writes pending_confirm entries; broker submission is not yet wired."` （提醒目前不會真的下單）。

#### Scenario: `ohmystock decide --help` 列旗標與警告
- **WHEN** 執行 `uv run ohmystock decide --help`
- **THEN** 命令以 exit code 0 結束，stdout 同時包含 `--symbol`、`--asof`、`--json` 三個旗標名稱，且含字面 `pending_confirm`

#### Scenario: enter 路徑印 summary 並 exit 0
- **GIVEN** monkeypatch `decide_entry` 回 `OrchestrationResult(decision_id="dec_2026-04-30T14-30-00_2330", final=DeciderOutput(decision="enter", ...), written_kind="entry", llm_cost=LLMCost(0.37), force_reject_reason=None)`，且 input assembler 順利
- **WHEN** 執行 `uv run ohmystock decide --symbol 2330 --asof 2026-04-30`
- **THEN** 命令以 exit code 0 結束，stdout 含字串 `decision: enter`、`decision_id: dec_2026-04-30T14-30-00_2330`、`cost_usd: 0.37`

#### Scenario: --json 印合法 JSON
- **GIVEN** 同前 GIVEN
- **WHEN** 執行 `uv run ohmystock decide --symbol 2330 --asof 2026-04-30 --json`
- **THEN** 命令以 exit code 0 結束，`json.loads(stdout)` 是 dict 且包含 `decision_id` / `decision` / `force_reject_reason` / `cost_usd` 四個 key

#### Scenario: reject 路徑 exit 1
- **GIVEN** monkeypatch `decide_entry` 回 `written_kind="reject", force_reject_reason="stage_4_excluded"`
- **WHEN** 執行 `uv run ohmystock decide --symbol 2330 --asof 2026-04-30`
- **THEN** 命令以 exit code 1 結束，stdout 含 `decision: reject`、`force_reject_reason: stage_4_excluded`

#### Scenario: input assembler 失敗 exit 2
- **GIVEN** monkeypatch `assemble_entry_input` raise `ValueError("symbol not in universe: 9999")`
- **WHEN** 執行 `uv run ohmystock decide --symbol 9999 --asof 2026-04-30`
- **THEN** 命令以 exit code 2 結束，stderr 含 `entry_input_assembly_failed:` 與 `symbol not in universe`

#### Scenario: parse error exit 3
- **GIVEN** monkeypatch `decide_entry` raise `DeciderOutputParseError(raw_text="...", cause=json.JSONDecodeError(...))`
- **WHEN** 執行 `uv run ohmystock decide --symbol 2330 --asof 2026-04-30`
- **THEN** 命令以 exit code 3 結束，stderr 含 `DeciderOutputParseError`

#### Scenario: 拒絕在非測試環境用 fake decider
- **GIVEN** env `OHMYSTOCK_DECIDER_MODEL=fake://always-enter`、env `OHMYSTOCK_ALLOW_FAKE_DECIDER` 未設或為空
- **WHEN** 執行 `uv run ohmystock decide --symbol 2330 --asof 2026-04-30`
- **THEN** 命令以 exit code 4 結束，stderr 含 `refused to use fake decider`

---

### Requirement: `OHMYSTOCK_DECIDER_MODEL` 與 `OHMYSTOCK_ALLOW_FAKE_DECIDER` 環境變數

`Settings` 類別 SHALL 新增兩個欄位：

- `decider_model: str`（env `OHMYSTOCK_DECIDER_MODEL`），預設 `"claude-opus-4-7"`。
- `ohmystock_allow_fake_decider: bool`（env `OHMYSTOCK_ALLOW_FAKE_DECIDER`），預設 `False`。

`.env.example` SHALL 同時新增這兩個 key（值為 `claude-opus-4-7` 與 `false`）。

#### Scenario: Settings 預設值
- **WHEN** test 透過 `monkeypatch.delenv` 清掉這兩個 env var key（`raising=False`），執行 `Settings(_env_file=None)`
- **THEN** `s.decider_model == "claude-opus-4-7"` 且 `s.ohmystock_allow_fake_decider is False`

#### Scenario: env 覆寫 decider_model
- **GIVEN** env `OHMYSTOCK_DECIDER_MODEL=claude-sonnet-4-6`
- **WHEN** `Settings()`
- **THEN** `s.decider_model == "claude-sonnet-4-6"`

#### Scenario: `.env.example` 新增兩個 key
- **WHEN** 讀取 `.env.example`
- **THEN** 檔案 SHALL 含 `OHMYSTOCK_DECIDER_MODEL` 與 `OHMYSTOCK_ALLOW_FAKE_DECIDER` 兩個 key

### Requirement: `ohmystock confirm` 子命令

系統 SHALL 在 `ohmystock` CLI 註冊 `confirm` 子命令，包裝 `confirm-gate` capability 的四個函式（`list_pending` / `confirm` / `reject` / `sweep_expired`），讓 solo dev 可由命令列驅動 pending entry 的人工生命週期。

子命令 SHALL 支援以下旗標組合（互斥群組）：

| 旗標組合 | 行為 | Exit code |
|---|---|---|
| `--list` | 印出目前所有 pending entry（decision_id、symbol、age、TTL）；表格形式至 stdout | `0`（含空 list） |
| `<decision_id>` | 對該 decision_id 呼叫 `confirm(...)`；成功印 fill 摘要至 stdout | `0` 成功 / `2` not_found / `2` not_pending / `2` already expired / `3` broker_failed |
| `<decision_id> --reject [--reason "..."]` | 對該 decision_id 呼叫 `reject(...)`；`--reason` 為空時用預設 `"human rejected via confirm gate"` | `1` 成功（人工 reject 為「semantic non-zero」）/ `2` not_found / `2` not_pending |
| `--sweep-expired` | 呼叫 `sweep_expired(...)`；印被 sweep 的 decision_id 數量與清單至 stdout | `0`（含 sweep 0 筆） |
| 同時給 `--list` 與 `--reject` / `--sweep-expired` | Typer mutually-exclusive options 拒絕 | `2`（Typer usage error） |

子命令 SHALL 共用以下旗標：
- `--user TEXT`（預設 `os.getenv("USER", "unknown")`）— 寫入 `human_confirmed_by` / `rejected_by`。
- `--db PATH`（預設來自 `Settings().ohmystock_db_path`）— SQLite 路徑。
- `--timeout-minutes INT`（預設來自 `Settings().ohmystock_confirm_timeout_minutes`）— sweep / list 用的 TTL。
- `--default-capital-twd INT`（預設來自 `Settings().ohmystock_default_capital_twd`）— confirm 計算 qty 用。
- `--json` — 將結構化結果以 JSON 印至 stdout（含 `action`、`decision_id`、`fill` / `reject` / `expire` / `pending` 細節）。

子命令 SHALL 在執行任何寫入前呼叫 `init_schema(conn)` 確保表存在（idempotent）。子命令 SHALL 在 `OHMYSTOCK_AUTO_EXECUTE=true` 時於 stderr 印一行警告 `"warning: auto mode requires the Phase 3.5 breaker, falling back to human confirm"`，然後正常執行人工流程（v0 不支援 auto）。

子命令 root help SHALL 含字面 `pending_confirm` 與 `expire` 字串，以提示用戶其影響的 lifecycle 狀態。

#### Scenario: `ohmystock confirm --help` 列旗標與警告
- **WHEN** 執行 `uv run ohmystock confirm --help`
- **THEN** stdout 含 `--list`、`--reject`、`--sweep-expired`、`--user`、`--reason`、`--timeout-minutes`、`--default-capital-twd`、`--json` 字串；含字面 `pending_confirm` 與 `expire`

#### Scenario: `--list` 印 pending entry 並 exit 0
- **GIVEN** monkeypatch `list_pending` 回 `[PendingEntry(decision_id="dec_X", symbol="2330", created_at="2026-05-02T10:00:00+08:00", age_seconds=900, ttl_seconds=900, current_price=832.0, final_sizing_pct=16.5)]`
- **WHEN** 執行 `uv run ohmystock confirm --list`
- **THEN** 命令以 exit code 0 結束，stdout 含 `dec_X`、`2330`、`832`、`16.5`、`900`

#### Scenario: `<decision_id>` 成功 confirm 並 exit 0
- **GIVEN** monkeypatch `confirm` 回 `ConfirmResult(decision_id="dec_X", fill=Fill(symbol="2330", filled_qty=1000, fill_price=832.0, fill_ts="2026-05-02T10:15:00+08:00", side="buy", requested_qty=1000), qty=1000)`
- **WHEN** 執行 `uv run ohmystock confirm dec_X`
- **THEN** 命令以 exit code 0 結束，stdout 含 `dec_X`、`2330`、`1000`、`832.0`、`confirmed`

#### Scenario: `<decision_id> --reject --reason "..."` 成功 reject 並 exit 1
- **GIVEN** monkeypatch `reject` 回 `RejectResult(decision_id="dec_X", reject_row_id=42)`
- **WHEN** 執行 `uv run ohmystock confirm dec_X --reject --reason "盤勢不對"`
- **THEN** 命令以 exit code 1 結束（semantic non-zero），stdout 含 `dec_X`、`rejected`、`盤勢不對`

#### Scenario: `<decision_id>` 對不存在的 decision exit 2
- **GIVEN** monkeypatch `confirm` raise `ConfirmGateError(code="not_found", ...)`
- **WHEN** 執行 `uv run ohmystock confirm dec_does_not_exist`
- **THEN** 命令以 exit code 2 結束，stderr 含 `not_found`

#### Scenario: `<decision_id>` broker 失敗 exit 3
- **GIVEN** monkeypatch `confirm` raise `ConfirmGateError(code="broker_failed", cause=BrokerError("forced"))`
- **WHEN** 執行 `uv run ohmystock confirm dec_X`
- **THEN** 命令以 exit code 3 結束，stderr 含 `broker_failed`

#### Scenario: `--sweep-expired` 印 sweep 結果並 exit 0
- **GIVEN** monkeypatch `sweep_expired` 回 `["dec_A", "dec_B"]`
- **WHEN** 執行 `uv run ohmystock confirm --sweep-expired`
- **THEN** 命令以 exit code 0 結束，stdout 含 `2 expired`、`dec_A`、`dec_B`

#### Scenario: `--sweep-expired` 0 筆過期 exit 0
- **GIVEN** monkeypatch `sweep_expired` 回 `[]`
- **WHEN** 執行 `uv run ohmystock confirm --sweep-expired`
- **THEN** 命令以 exit code 0 結束，stdout 含 `0 expired`

#### Scenario: 同時給 --list 與 --reject 拒絕
- **WHEN** 執行 `uv run ohmystock confirm dec_X --list --reject`
- **THEN** 命令以 exit code 2 結束（Typer usage error），stderr 含 `mutually exclusive` 或等價字串

#### Scenario: OHMYSTOCK_AUTO_EXECUTE=true 印 warning 但仍跑人工流程
- **GIVEN** env `OHMYSTOCK_AUTO_EXECUTE=true`，monkeypatch `confirm` 回 `ConfirmResult(...)`
- **WHEN** 執行 `uv run ohmystock confirm dec_X`
- **THEN** 命令以 exit code 0 結束；stderr 含字面 `auto mode requires the Phase 3.5 breaker`；stdout 含 `confirmed`（仍跑人工流程）

#### Scenario: `--json` 路徑回合法 JSON dict
- **WHEN** 執行 `uv run ohmystock confirm dec_X --json`（對成功 confirm 路徑）
- **THEN** stdout 為合法 JSON，`json.loads` 後為 dict，含 keys：`action`（值 `"confirm"`）、`decision_id`、`fill`（dict 含 `fill_price`、`filled_qty`、`fill_ts`）、`exit_code`

---

### Requirement: 新增 Settings 欄位 `ohmystock_confirm_timeout_minutes` / `ohmystock_default_capital_twd`

系統 SHALL 在 `ohmystock.config.Settings` 新增以下兩個欄位：

- `ohmystock_confirm_timeout_minutes: int = 30`（env `OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES`，case-insensitive）
- `ohmystock_default_capital_twd: int = 1_000_000`（env `OHMYSTOCK_DEFAULT_CAPITAL_TWD`，case-insensitive）

兩欄位 SHALL 為正 int；當 env 解析得到的值 ≤ 0 時，pydantic SHALL raise `ValidationError`（pydantic 的 `int` 型別不會主動拒絕 0 或負值，故本 requirement SHALL 在 `Settings` model 上加 `field_validator` 強制 `> 0`）。

`.env.example` SHALL 在 `# --- ohMyStock runtime toggles ---` 區塊或新區塊 `# --- Confirm Gate v0 ---` 中新增兩行：
```
OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES=30
OHMYSTOCK_DEFAULT_CAPITAL_TWD=1000000
```

#### Scenario: 預設值 — 不設 env 時等於文件預設
- **WHEN** 在無相關 env 的環境執行 `Settings()`
- **THEN** `s.ohmystock_confirm_timeout_minutes == 30` 且 `s.ohmystock_default_capital_twd == 1_000_000`

#### Scenario: env 覆寫 timeout
- **GIVEN** monkeypatch env `OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES=60`
- **WHEN** 執行 `Settings()`
- **THEN** `s.ohmystock_confirm_timeout_minutes == 60`

#### Scenario: env 覆寫 default capital
- **GIVEN** monkeypatch env `OHMYSTOCK_DEFAULT_CAPITAL_TWD=2500000`
- **WHEN** 執行 `Settings()`
- **THEN** `s.ohmystock_default_capital_twd == 2_500_000`

#### Scenario: timeout ≤ 0 raise ValidationError
- **GIVEN** monkeypatch env `OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES=0`
- **WHEN** 執行 `Settings()`
- **THEN** raise `pydantic.ValidationError`，message 含 `ohmystock_confirm_timeout_minutes`

#### Scenario: default_capital ≤ 0 raise ValidationError
- **GIVEN** monkeypatch env `OHMYSTOCK_DEFAULT_CAPITAL_TWD=-1`
- **WHEN** 執行 `Settings()`
- **THEN** raise `pydantic.ValidationError`，message 含 `ohmystock_default_capital_twd`

#### Scenario: `.env.example` 含兩個新 key
- **WHEN** 讀取 repo root 的 `.env.example`
- **THEN** 檔案內容含 `OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES=30` 與 `OHMYSTOCK_DEFAULT_CAPITAL_TWD=1000000` 兩行（值為文件預設）

### Requirement: `ohmystock evaluate-exits` 子命令

系統 SHALL 在 `ohmystock` CLI 註冊 `evaluate-exits` 子命令，包裝 `exit-engine` capability 的 `evaluate_open_positions(...)`，讓 solo dev 可在每日盤後 close 一輪：對所有 confirmed entry 評估三條 v0 出場條件，將觸發者寫成 `kind=exit` row 並翻 entry status 為 `closed`。

子命令 SHALL 支援以下旗標：

| 旗標 | 必填 | 行為 |
|---|---|---|
| `--asof YYYY-MM-DD` | 必填 | 評估的交易日（用於 lookup close price 與計算 hold_days） |
| `--symbol XXXX` | 選填 | 限定評估單一 symbol（用於人工 spot-check） |
| `--price FLOAT` | 選填 | 覆寫 market_data lookup 的 close 價（**只能與 `--symbol` 一起用**） |
| `--db PATH` | 選填 | SQLite 路徑；預設讀 `OHMYSTOCK_DB_PATH` |
| `--json` | 選填 | 將結構化結果以 JSON 印至 stdout |

子命令 SHALL 在執行任何寫入前呼叫 `init_schema(conn)` 確保表存在（idempotent）。

子命令 SHALL 用 `ohmystock.swarm._live_market` 模組的 close-price lookup 作為預設 `MarketDataLookup` 實作（同 `ohmystock decide` 的 live provider chain），除非 `--price` 旗標 override。

子命令 root help SHALL 含字面 `kind=exit`、`closed`、`hit_stop_loss`、`hit_t1`、`time_stop` 字串，以提示用戶其影響的 lifecycle 狀態與 v0 三標籤。

**Exit codes：**
- `0` — 評估完成（不論 close 多少筆，含 0 筆）
- `2` — usage error（缺 `--asof`、`--asof` 非合法日期、`--price` 未配 `--symbol`）
- `3` — `ExitEngineError(code="market_data_unavailable")` 或其他 engine 層錯誤；stderr 列失敗 symbol

#### Scenario: `ohmystock evaluate-exits --help` 列旗標與 lifecycle 字串
- **WHEN** 執行 `uv run ohmystock evaluate-exits --help`
- **THEN** stdout 含 `--asof`、`--symbol`、`--price`、`--db`、`--json` 字串；含字面 `kind=exit`、`closed`、`hit_stop_loss`、`hit_t1`、`time_stop`

#### Scenario: 缺 --asof exit 2
- **WHEN** 執行 `uv run ohmystock evaluate-exits`
- **THEN** 命令以 exit code 2 結束（Typer usage error）

#### Scenario: --asof 非合法日期 exit 2
- **WHEN** 執行 `uv run ohmystock evaluate-exits --asof "not-a-date"`
- **THEN** 命令以 exit code 2 結束，stderr 含 `asof` 或 `date` 字串

#### Scenario: --price 未配 --symbol exit 2
- **WHEN** 執行 `uv run ohmystock evaluate-exits --asof 2026-05-07 --price 900.0`
- **THEN** 命令以 exit code 2 結束，stderr 含 `--price` 與 `--symbol` 字串（要求兩者同時提供）

#### Scenario: --symbol 與 --price 一起 — close 觸 T1 exit 0
- **GIVEN** in-memory test DB 有一筆 confirmed entry `symbol="2330"`、`actual_entry_price=832.0`、`stop_loss_price=784.58`，monkeypatch `evaluate_open_positions` 回 `[ExitResult(decision_id="dec_X", action="closed", decision=ExitDecision(exit_tag="hit_t1", actual_exit_price=900.0, pnl_pct=8.17, hold_days=5, exit_reason="..."))]`
- **WHEN** 執行 `uv run ohmystock evaluate-exits --asof 2026-05-07 --symbol 2330 --price 900.0`
- **THEN** 命令以 exit code 0 結束，stdout 含 `dec_X`、`hit_t1`、`closed`、`8.17`

#### Scenario: 評估完成但 0 筆 close exit 0
- **GIVEN** monkeypatch `evaluate_open_positions` 回 `[]`
- **WHEN** 執行 `uv run ohmystock evaluate-exits --asof 2026-05-07`
- **THEN** 命令以 exit code 0 結束，stdout 含 `0 closed` 或等價字串

#### Scenario: 多筆 entry，一筆 close、一筆 held
- **GIVEN** monkeypatch `evaluate_open_positions` 回 兩筆 ExitResult（一筆 closed、一筆 held）
- **WHEN** 執行 `uv run ohmystock evaluate-exits --asof 2026-05-07`
- **THEN** 命令以 exit code 0 結束，stdout 兩行（含 closed 與 held 各一）

#### Scenario: market_data lookup 失敗 exit 3
- **GIVEN** monkeypatch `evaluate_open_positions` raise `ExitEngineError(code="market_data_unavailable", failed_symbols=["2317"])`
- **WHEN** 執行 `uv run ohmystock evaluate-exits --asof 2026-05-07`
- **THEN** 命令以 exit code 3 結束，stderr 含 `market_data_unavailable` 與 `2317`

#### Scenario: `--json` 路徑回合法 JSON list
- **GIVEN** 同 hit_t1 GIVEN
- **WHEN** 執行 `uv run ohmystock evaluate-exits --asof 2026-05-07 --symbol 2330 --price 900.0 --json`
- **THEN** stdout 為合法 JSON，`json.loads` 後為 dict 含 keys：`asof`、`evaluated`（list[dict]）、`exit_code`；list 元素含 `decision_id`、`action`、`exit_tag`、`actual_exit_price`、`pnl_pct`、`hold_days`

