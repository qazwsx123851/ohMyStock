## Context

`ohMyStock` 是個人 solo dev + LLM 協作的 paper trading agent 專案，目前處於 *Spec / Pre-implementation* 階段。`docs/design-zh-TW.md` §4 已經把模組邊界（17 個子模組）拍板，`CLAUDE.md` §3 已決定技術棧（Python 3.11+、Claude Agent SDK、FastAPI、SQLite + FTS5、不用 LangChain），但 repo root 只有 `docs/`、`openspec/`、`proposals/`、`reviews/`、`README.md`、`LICENSE`、`CLAUDE.md`，沒有任何 `src/` 或 `pyproject.toml`。

本 change 的目的是**用最小可運作的方式建立 Python repo 著陸點**，不引入任何業務邏輯，讓後續 10 張 change 都有固定目錄可以往裡面放東西。

## Goals / Non-Goals

**Goals:**
- `uv sync` 能安裝、`uv run python -c "import ohmystock"` 不報錯
- `pytest` 能跑（即使沒有測試）
- 17 個子模組目錄齊備，可被後續 change 直接 import 對應子套件
- `.env.example` 列出 v1 已知的所有環境變數契約，避免後續 change 各自重複決定 key 命名
- `Makefile` 提供 `install` / `lint` / `test` 三個入口（指向 `uv` 對應命令）

**Non-Goals:**
- 不實作 CLI 子命令（留給 `cli-skeleton`）
- 不啟動 FastAPI（留給 `fastapi-bootstrap`）
- 不接 Shioaji / FinMind / Anthropic（留給 `external-connectors-and-cost`）
- 不安裝重型依賴（`shioaji`、`finmind`、`anthropic`、`fastapi` 等）— 後續 change 在需要時加進 `pyproject.toml`
- 不寫 Dockerfile（留給 Phase 5 `harden-and-deploy`）
- 不設定 CI（個人專案 + CLAUDE.md §2「避免過度工程」明確排除 CI lint）

## Decisions

### D1：採用 `uv` 為 package manager（非 `poetry` / `pip-tools` / `hatch`）
**選 `uv`**：執行速度快、與 PEP 621 `pyproject.toml` 完全相容、`uv.lock` 跨平台、單一 binary 安裝。
**Alt 1 `poetry`**：成熟，但 lock 解析慢、與 PEP 621 互動較笨。
**Alt 2 `hatch`**：標準化好但 dep 解析效率比 uv 差。
**Alt 3 `pip + requirements.txt`**：個人 solo dev 仍想要 lockfile 確保跨機器一致。
依據：CLAUDE.md §2「避免過度工程」+ solo dev 偏好快速反饋。

### D2：採用 `src/` layout 而非 flat layout
**選 `src/ohmystock/`**：強制安裝後才能 import，避免「在 repo root 跑 `python` 意外撈到未安裝的套件」這種隱性 bug。
**Alt** flat layout（`ohmystock/` 直接在 repo root）：少打一層字，但易誤撈。
依據：Python packaging 社群共識；對 17 個子模組的專案幫助更大。

### D3：每個子模組目錄只放空 `__init__.py`
**選空檔**：保持目錄被 git 追蹤又零實作。
**Alt** `__init__.py` 內 re-export 各子模組常用名稱：先不做，因為 17 個子模組此時都是空殼，re-export 會立刻過期。
依據：YAGNI、避免之後改一處忘另一處。

### D4：`.env.example` 列出哪些 key
依 `safety-and-simulation.md` §2.9 / `v3-decisions.md` #9、#15 + `docs/design-zh-TW.md` §4.11.2（Shioaji 認證）+ §5.1（FinMind）的環境變數列出：
- `ANTHROPIC_API_KEY`
- `SHIOAJI_API_KEY`、`SHIOAJI_SECRET_KEY`、`SHIOAJI_CA_PATH`、`SHIOAJI_CA_PASSWD`、`SHIOAJI_PERSON_ID`
- `FINMIND_TOKEN`
- `OHMYSTOCK_AUTO_EXECUTE`（預設 `false`，依 `safety-and-simulation.md` §2.9）
- `OHMYSTOCK_LLM_DEGRADE`（預設 `false`，依 `v3-decisions.md` #15 軟熔斷）
- `OHMYSTOCK_DB_PATH`（SQLite 位置，預設 `~/.ohmystock/journal.db`）
- `OHMYSTOCK_LOG_LEVEL`（預設 `INFO`）

值一律留空字串或 `false`/預設值；真正 secret 寫在 git-ignored `.env`。

### D5：不在這張 change 設定 linter / formatter
**選不設定**：`pyproject.toml` 暫不加 `ruff` / `black` / `mypy` 配置。
**Alt** 一次設好：會把 lint policy 變成必須通過，但目前沒有任何程式碼可 lint。
依據：CLAUDE.md §2 明確禁止「CI lint policy」設計；個人專案，linter 之後 `cli-skeleton` 或更後面再補即可。

### D6：`Makefile` 而非 `tasks.py`（invoke）/ `just`
**選 `Makefile`**：Windows 11 Pro + Git Bash 環境，`make` 可用；solo dev 不需要跨 shell。
**Alt** `just` / `invoke`：多一個依賴，邊際收益低。
依據：CLAUDE.md §2、environment 註明 bash + PowerShell 都可用。

### D7：tests/ 目錄結構
建立 `tests/__init__.py` 與 `tests/conftest.py`（內容空白或留 `# placeholder`），不建子目錄；後續 change 各自開 `tests/<capability>/`。
依據：YAGNI，等 capability spec 成形再分。

## Risks / Trade-offs

- **[Risk]** `uv` 還在快速演進，行為可能在大版本變動 → **Mitigation**：在 `pyproject.toml` 不依賴 `uv` 專屬欄位（只用 PEP 621 標準欄位 + `[tool.uv]` 最小設定），即使將來換工具仍可遷移。
- **[Risk]** Windows 上 `make` 可能未安裝 → **Mitigation**：`Makefile` target 內容都只是呼叫 `uv ...`，使用者直接打 `uv sync` / `uv run pytest` 也等價。
- **[Risk]** 17 個空目錄 + 18 個空 `__init__.py` 看起來「過度提前規劃」，違反 CLAUDE.md §2 「避免為 hypothetical 設計」 → **Mitigation**：這 17 個模組在 `docs/design-zh-TW.md` §4 已經一一拍板（不是 hypothetical），先建好可避免後續 10 張 change 各自決定「我這個檔案放哪」造成漂移。
- **[Risk]** 未來想改套件名（`ohmystock` → 別的）會牽動所有 import → **Mitigation**：套件名與 repo 名一致，且 `v3-decisions.md` 已穩定，改名機率極低；若真要改也僅是 sed 全 repo。
- **[Trade-off]** 不裝任何「會用到」的 deps（FastAPI、shioaji、anthropic）→ 換來 `uv sync` 在此 change 極快、之後每張 change 才漸進式加 deps；缺點是後續 change 第一次跑時會等較久 install。可接受。

## Migration Plan

不適用（first change，no rollback target）。若整張 change 想撤銷，刪掉 `src/`、`tests/`、`scripts/`、`pyproject.toml`、`uv.lock`、`.env.example`、`.gitignore`、`Makefile` 即可恢復原狀；docs/openspec/proposals/reviews 完全沒動。

## Open Questions

- 套件名是否要保留底線 `oh_my_stock`？→ 採 `ohmystock` 一字，與 repo 名 / `docs/design-zh-TW.md` §4 import path（`src/ohmystock/...`）一致。
- 是否需要 `py.typed` marker？→ 暫不加；等 `cli-skeleton` 之後加 type hints 時再放。
