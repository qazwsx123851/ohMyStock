## Why

`scaffold-repo`（已 archived 為 `2026-04-27-scaffold-repo`）已預留 `pyproject.toml` 的 `ohmystock = "ohmystock.cli:main"` console-script 入口，但 `ohmystock.cli` 模組尚不存在；目前執行 `uv run ohmystock --help` 會 `ModuleNotFoundError`。本 change 補上 CLI 骨架與設定檔載入器，讓「`ohmystock --help` 列出所有子命令」成立，作為後續 `fastapi-bootstrap`、`external-connectors-and-cost`、`core-agent-and-base-skills` 等 change 掛接子命令邏輯（`run` / `backtest` / `review` / `propose` / `screen`）的著陸點。對應 milestone Phase 0b（`docs/v3-decisions.md` §5、`C:\Users\Oolong\.claude\plans\sdd-distributed-pretzel.md` §2.2 Change 2）。

## What Changes

- **新增** `src/ohmystock/cli.py`：`typer.Typer` app + 5 個子命令 stub（`run` / `backtest` / `review` / `propose` / `screen`），每個 stub 印 `not implemented` 並 `raise typer.Exit(1)`；公開 `main()` 對應 `pyproject.toml` 的 `[project.scripts]` 入口
- **新增** `src/ohmystock/config.py`：以 `pydantic-settings.BaseSettings` 載入 `.env`，欄位 1:1 對應 `.env.example` 列出的 11 個 key（`ANTHROPIC_API_KEY`、`SHIOAJI_*` 6 欄、`FINMIND_TOKEN`、`OHMYSTOCK_AUTO_EXECUTE`、`OHMYSTOCK_LLM_DEGRADE`、`OHMYSTOCK_DB_PATH`、`OHMYSTOCK_LOG_LEVEL`），所有欄位為 `Optional` / 有預設，不在 import 時要求值（避免 stub 子命令觸發強制檢核）
- **修改** `pyproject.toml`：`[project.dependencies]` 新增 `typer>=0.12`、`pydantic-settings>=2.0`；`pydantic` 由 `pydantic-settings` 拉入，不直接列出
- **新增** `tests/test_cli.py`：3 個最小測試（`--help` 列出 5 子命令、子命令 stub 回 exit 1 並含 `not implemented`、`config.Settings()` 可在缺所有 env var 時建構成功）
- **不做**：任何子命令的真實邏輯（`run` 不接 LLM Decider、`backtest` 不接回測引擎、`review` 不接 Phase 5 swarm、`propose` 不寫 proposal、`screen` 不接 screener）；不啟動 FastAPI；不接 Shioaji / FinMind / Anthropic；不引入 `click` 或 `argparse`（CLAUDE.md §3 未指定，本 change 拍板採 `typer`，理由見 design.md）

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `cli-and-config`：原 spec（archive `2026-04-27-scaffold-repo` 寫入）只要求「console-script 已宣告」與「entry point 失敗不阻塞 install」；本 change 把該 capability 從「entry point 已宣告但模組可不存在」升級為「`ohmystock --help` 必須成功並列出 5 子命令；`Settings` 類別必須能在無 `.env` 時實例化」。spec delta 採 MODIFIED（升級 1 條既有 Requirement「套件 console-script 入口已預留」）+ ADDED（新增「CLI 子命令骨架」與「設定檔載入器」兩條 Requirement）。

## Impact

- **新增依賴**：`typer>=0.12`（含 transitive `click`、`shellingham`、`rich`）、`pydantic-settings>=2.0`（含 transitive `pydantic`、`python-dotenv`）。`uv sync` 之後 `uv.lock` 會更新
- **新增檔案**：`src/ohmystock/cli.py`、`src/ohmystock/config.py`、`tests/test_cli.py`
- **修改檔案**：`pyproject.toml`（新增 2 個 deps）、`uv.lock`（rerun `uv sync` 後）
- **不影響**：`docs/`（不修改任何設計文件）、`.env.example`（key 集合不動）、`Makefile`、`scripts/`、其他 16 個子模組目錄
- **後續 unblock**：`fastapi-bootstrap`（Phase 0c）— 將新增 `src/ohmystock/api/app.py` 並在 `cli.py` 加 `api` 子命令；`external-connectors-and-cost`（Phase 0d）— 將新增 `smoke-test` 子命令
