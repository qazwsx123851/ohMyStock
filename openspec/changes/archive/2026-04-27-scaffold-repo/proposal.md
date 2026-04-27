## Why

`ohMyStock` 目前 12 份設計文件齊備，但 repo 還沒有任何原始碼骨架；後續所有 OpenSpec changes（CLI、FastAPI、connectors、skills、swarm…）都需要一個可 import 的 `ohmystock` Python 套件與固定的目錄結構作為著陸點。先把 repo scaffolding 拆出來最小化此一動作，避免之後每張 change 都要重複決定「目錄放哪裡」「pyproject 怎麼寫」。

對應 milestone Phase 0a（`docs/v3-decisions.md` §5）。

## What Changes

- **新增** `pyproject.toml`：宣告 Python 3.11+、`uv` 為 package manager、套件名 `ohmystock`、`src/` layout、`ohmystock` console-script 入口（內容先指向尚未實作的 CLI，留給下一張 change `cli-skeleton` 補完）
- **新增** `src/ohmystock/` 套件根與 17 個子模組目錄（`agent/`、`skills/`、`tools/`、`backtest/`、`paper/`、`memory/`、`swarm/`、`api/`、`strategies/`、`data/`、`safety/`、`observability/`、`decider/`、`journal/`、`review/`、`proposal/`、`eventbus/`），每個目錄放空 `__init__.py`，模組邊界依 `docs/design-zh-TW.md` §4
- **新增** `tests/` 目錄與 `tests/__init__.py`、`tests/conftest.py`（最小 pytest 配置）
- **新增** `scripts/` 目錄（後續 change 會放 smoke-test 等運維腳本）
- **新增** `.env.example`：列出 Shioaji / FinMind / Anthropic / `OHMYSTOCK_AUTO_EXECUTE` / `OHMYSTOCK_LLM_DEGRADE` 等環境變數占位（**值留空**，依 `safety-and-simulation.md` §2.9 / `v3-decisions.md` #9、#15）
- **新增** `.gitignore`：覆蓋 Python venv、`.env*`（`.env.example` 例外）、SQLite、build artifacts、`.ohmystock/` 本地資料目錄
- **新增** `Makefile`：先放 `install` / `lint` / `test` 三個 target（內容只 echo「not yet implemented」或呼叫 `uv` 對應命令）
- **不做**：CLI 子命令邏輯、FastAPI app、任何 connector、任何 strategy / skill / tool 實作（留給後續 changes）

## Capabilities

### New Capabilities
- `cli-and-config`: 提供 Python 套件骨架、套件管理（`uv` + `pyproject.toml`）、環境變數契約、目錄結構，作為所有後續 capability 的著陸點。本 change 只實作「可 import 的空套件 + 環境變數契約」；CLI 子命令骨架留給後續 change `cli-skeleton`。

### Modified Capabilities
（無 — 此為 repo 內第一張 change，`openspec/specs/` 目前為空）

## Impact

- **新增依賴**：`pyproject.toml` 宣告生產 deps 為空、dev deps 含 `pytest`；不安裝 `shioaji` / `finmind` / `anthropic` / `fastapi`（留給後續 change 在需要時加）
- **新增檔案**：`pyproject.toml`、`uv.lock`（執行 `uv sync` 後生成）、`.env.example`、`.gitignore`、`Makefile`、`src/ohmystock/__init__.py` × 18（含根與 17 子模組）、`tests/__init__.py`、`tests/conftest.py`
- **不影響**：`docs/`（不修改任何設計文件）、`proposals/`、`reviews/`、`openspec/specs/` 既有內容（目前為空）
- **跨機協作**：所有產物進 git；`.env.example` 進 git，真正 `.env` 不進
- **後續 unblock**：`cli-skeleton`、`fastapi-bootstrap`、`external-connectors-and-cost`（plan §2.1 DAG）
