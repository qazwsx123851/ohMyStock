## 1. pyproject 與套件管理

- [x] 1.1 在 repo root 建立 `pyproject.toml`：宣告 `[project]` 套件名 `ohmystock`、`requires-python = ">=3.11"`、`version = "0.0.0"`、`description`、生產 `dependencies = []`、`[project.optional-dependencies] dev = ["pytest"]`、`[project.scripts] ohmystock = "ohmystock.cli:main"`、`[build-system]` 採用 hatchling、`[tool.hatch.build.targets.wheel] packages = ["src/ohmystock"]`、`[tool.uv]` 最小設定（先空 table 即可）
- [x] 1.2 執行 `uv sync` 並確認產生 `.venv/`、`uv.lock`，命令 exit 0
- [x] 1.3 在乾淨環境驗證 `uv run python -c "import ohmystock"` exit 0（spec：「Python 套件可被 import」 / Scenario「安裝完成後可 import 根套件」）

## 2. src 套件骨架

- [x] 2.1 建立 `src/ohmystock/__init__.py`（內容空白或僅 `"""ohMyStock package root."""`）
- [x] 2.2 為 17 個子模組各建立目錄與空 `__init__.py`：`agent/`、`skills/`、`tools/`、`backtest/`、`paper/`、`memory/`、`swarm/`、`api/`、`strategies/`、`data/`、`safety/`、`observability/`、`decider/`、`journal/`、`review/`、`proposal/`、`eventbus/`
- [x] 2.3 執行 `uv run python -c "import ohmystock.agent, ohmystock.skills, ohmystock.tools, ohmystock.backtest, ohmystock.paper, ohmystock.memory, ohmystock.swarm, ohmystock.api, ohmystock.strategies, ohmystock.data, ohmystock.safety, ohmystock.observability, ohmystock.decider, ohmystock.journal, ohmystock.review, ohmystock.proposal, ohmystock.eventbus"` 並驗證 exit 0（spec Scenario「17 個子模組可被 import」）

## 3. tests 與 scripts 目錄

- [x] 3.1 建立 `tests/__init__.py`（空）
- [x] 3.2 建立 `tests/conftest.py`（內容空或 `# placeholder for future fixtures`）
- [x] 3.3 建立 `scripts/.gitkeep`（保留空目錄供後續 change 放 smoke-test）
- [x] 3.4 執行 `uv run pytest` （RC=5 / no tests ran — 符合 spec），確認 exit code 為 0 或 5（spec：「測試運行時不需要實際相依」 / Scenario「空 `pytest` 不會失敗」）

## 4. 環境變數契約

- [x] 4.1 建立 `.env.example`（repo root），條目順序與註解說明依 design D4，至少包含：`ANTHROPIC_API_KEY=`、`SHIOAJI_API_KEY=`、`SHIOAJI_SECRET_KEY=`、`SHIOAJI_CA_PATH=`、`SHIOAJI_CA_PASSWD=`、`SHIOAJI_PERSON_ID=`、`FINMIND_TOKEN=`、`OHMYSTOCK_AUTO_EXECUTE=false`、`OHMYSTOCK_LLM_DEGRADE=false`、`OHMYSTOCK_DB_PATH=~/.ohmystock/journal.db`、`OHMYSTOCK_LOG_LEVEL=INFO`
- [x] 4.2 在 `.env.example` 開頭加 1-2 行註解：本檔僅為 placeholder、真實值寫到 `.env`（git-ignored）
- [x] 4.3 驗證 `.env.example` 沒有任何 value 看起來像真實 secret（spec Scenario「預設值不含真實 secret」）

## 5. .gitignore

- [x] 5.1 ~~建立~~ `.gitignore` 已存在（repo root）並涵蓋以下類別（既有檔案比 task 列表更完整，無需新增）：
  - Python：`__pycache__/`、`*.py[cod]`、`*.egg-info/`、`.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`、`build/`、`dist/`
  - venv：`.venv/`、`venv/`
  - env：`.env`、`.env.*`（**例外** `!.env.example`）
  - SQLite：`*.db`、`*.sqlite`、`*.sqlite3`
  - 本地資料：`.ohmystock/`
  - IDE：`.idea/`、`.vscode/`
  - OS：`.DS_Store`、`Thumbs.db`
- [x] 5.2 在 repo root 建立 `.env`（測試用，內容隨意）後執行 `git status`，驗證 `.env` 未列出（spec Scenario「真實 `.env` 不進 git」），完成後刪除測試 `.env`

## 6. Makefile

- [x] 6.1 建立 `Makefile`（repo root），含 `install` / `lint` / `test` / `help` 四個 target；每個 target 內容為：
  - `install`：`uv sync`
  - `test`：`uv run pytest`
  - `lint`：`echo "lint not configured yet"`
  - `help`：列出可用 target
  - `.PHONY: install lint test help`
- [x] 6.2 在 `Makefile` 中將 `help` 設為預設 target（即第一個 target）
- [x] 6.3 ~~執行 `make install`~~ 環境未裝 `make`（option C），改以 inspection：Makefile `install:` recipe 為 `uv sync`，且 `uv sync` 已於 task 1.2 / 8.1 通過 → spec 等價需求滿足
- [x] 6.4 ~~執行 `make test`~~ 環境未裝 `make`（option C），改以 inspection：Makefile `test:` recipe 為 `uv run pytest`，且 `uv run pytest` 已於 task 3.4 通過（RC=5）→ spec 等價需求滿足
- [x] 6.5 ~~執行 `make lint`~~ 環境未裝 `make`（option C），改以 inspection：Makefile `lint:` recipe 為 `@echo "lint not configured yet"` → spec 不阻塞需求滿足

## 7. Console-script 入口預留

- [x] 7.1 確認 `pyproject.toml` `[project.scripts]` 已含 `ohmystock = "ohmystock.cli:main"`（task 1.1 應已包含；此處為交叉檢查）
- [x] 7.2 執行 `uv run ohmystock --help` （`ModuleNotFoundError: No module named 'ohmystock.cli'` 如預期；`import ohmystock` 仍 OK），預期會因 `ohmystock.cli` 模組未存在而報錯；驗證錯誤是 `ModuleNotFoundError: No module named 'ohmystock.cli'` 或等價，但 `uv sync` 與 `import ohmystock` 仍成功（spec Scenario「entry point 失敗不阻塞 install」）

## 8. 端對端驗收

- [x] 8.1 在 repo root 執行完整流程：`rm -rf .venv uv.lock && uv sync --extra dev && uv run python -c "import ohmystock" && uv run pytest`，全部成功（`make help` 部分因 option C 未裝 make 而以 task 6.x 的 inspection 替代）
- [x] 8.2 `git status` 列出新增檔案符合 proposal「Impact / 新增檔案」清單；無意外的多餘檔案（如 `.env`、SQLite db、`__pycache__`）
- [x] 8.3 在 `D:\ohMyStock` 開啟新的 shell 重複 8.1，驗證在「沒有 cache 的情境」也能正常啟動（subshell 重跑 `uv run python -c "import ohmystock"` 與 `uv run pytest` 均通過）

## 9. 文件交叉檢查（不修改 docs/）

- [x] 9.1 比對 `pyproject.toml` 套件版本（`requires-python`）與 `CLAUDE.md` §3 技術棧表一致（Python 3.11+）
- [x] 9.2 比對 `.env.example` key 集合與 `docs/safety-and-simulation.md` §2.9（`OHMYSTOCK_AUTO_EXECUTE`）/ `docs/v3-decisions.md` #15（`OHMYSTOCK_LLM_DEGRADE`）/ `docs/design-zh-TW.md` §4.11.2（Shioaji 認證）一致；若 docs 未列某個 key（如 `OHMYSTOCK_DB_PATH`、`OHMYSTOCK_LOG_LEVEL`）則 NOT-A-BLOCKER（本 change 新建契約，後續 change 若擴充 docs 即可）
- [x] 9.3 確認本 change 沒有修改任何 `docs/*.md` 檔案（`git diff docs/` 應為空）

## 10. Archive 前準備

- [x] 10.1 在 repo root 執行 `openspec validate scaffold-repo` （回報 "Change 'scaffold-repo' is valid"）（若 CLI 提供）或 `openspec status --change scaffold-repo --json` 確認所有 task 已 `[x]`
- [x] 10.2 草擬 commit message：`feat(scaffold): bootstrap python repo with uv + 17 module skeleton`（實際 commit 由人工或後續 `/opsx:archive` 步驟處理）
