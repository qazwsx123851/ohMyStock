## 1. 依賴更新

- [x] 1.1 編輯 `pyproject.toml` `[project.dependencies]`：新增 `typer>=0.12`、`pydantic-settings>=2.0`（保留 `dependencies = []` 寫法移除，改為 list 含這兩項）
- [x] 1.2 執行 `uv sync` 並確認 `uv.lock` 更新；exit 0
- [x] 1.3 驗證 `uv run python -c "import typer, pydantic_settings"` exit 0

## 2. `ohmystock.config.Settings`

- [x] 2.1 建立 `src/ohmystock/config.py`：定義 `Settings(BaseSettings)`，欄位以 lower-case 對應 `.env.example` 全部 11 個 key（`anthropic_api_key`、`shioaji_api_key`、`shioaji_secret_key`、`shioaji_ca_path`、`shioaji_ca_passwd`、`shioaji_person_id`、`finmind_token`、`ohmystock_auto_execute`、`ohmystock_llm_degrade`、`ohmystock_db_path`、`ohmystock_log_level`），全部型別為 `str | None = None`（`auto_execute` / `llm_degrade` 也先用字串，後續 change 再窄化成 bool）
- [x] 2.2 設定 `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")`
- [x] 2.3 為 `ohmystock_db_path` 與 `ohmystock_log_level` 補預設值字串 `"~/.ohmystock/journal.db"` 與 `"INFO"`（依 `.env.example`），其餘欄位預設 `None`
- [x] 2.4 驗證：`uv run python -c "from ohmystock.config import Settings; s = Settings(); assert s.anthropic_api_key is None; assert s.ohmystock_log_level == 'INFO'; print('ok')"` 印 `ok`，exit 0

## 3. `ohmystock.cli` 與 5 子命令 stub

- [x] 3.1 建立 `src/ohmystock/cli.py`：`import typer`，`app = typer.Typer(help="ohMyStock — 台股 AI 交易代理人 CLI")`
- [x] 3.2 為 `run` 子命令寫 stub：`@app.command(help="跑一輪完整流程：訊號偵測 → 進場決策 → Confirm Gate → Trade Journal（後續 change 實作）")`，函式內 `typer.echo("not implemented"); raise typer.Exit(1)`
- [x] 3.3 為 `backtest` 子命令寫 stub：`@app.command(help="對指定策略跑歷史回測（後續 change 實作）")`，同樣 echo + Exit(1)
- [x] 3.4 為 `review` 子命令寫 stub：`@app.command(help="跑 Phase 5 月度復盤五節點 swarm（後續 change 實作）")`
- [x] 3.5 為 `propose` 子命令寫 stub：`@app.command(help="生成策略改動提案，走 WFA 樣本外驗證（後續 change 實作）")`
- [x] 3.6 為 `screen` 子命令寫 stub：`@app.command(help="跑 Screener 篩選候選標的（後續 change 實作）")`
- [x] 3.7 加入 `def main() -> None: app()` 作為 console-script 入口
- [x] 3.8 驗證：`uv run ohmystock --help` exit 0 且 stdout 同時含 `run` / `backtest` / `review` / `propose` / `screen`
- [x] 3.9 驗證：`uv run ohmystock run` exit code = 1 且 stdout 含 `not implemented`（其他四個子命令同步驗證）
- [x] 3.10 驗證：`uv run ohmystock run --help` exit 0 且 stdout 含對應 stub help 文字

## 4. 測試（最小三條）

- [x] 4.1 建立 `tests/test_cli.py`，匯入 `from typer.testing import CliRunner`、`from ohmystock.cli import app`、`from ohmystock.config import Settings`，初始化 `runner = CliRunner()`
- [x] 4.2 寫測試 `test_root_help_lists_all_subcommands`：`result = runner.invoke(app, ["--help"])`，斷言 `result.exit_code == 0` 且五個子命令名稱皆出現於 `result.output`
- [x] 4.3 寫測試 `test_subcommand_stub_returns_not_implemented`（用 `pytest.mark.parametrize` 對五個子命令各跑一次）：斷言 `exit_code == 1` 且 `"not implemented" in result.output`
- [x] 4.4 寫測試 `test_settings_constructible_without_env`：`s = Settings()`；斷言 `s.anthropic_api_key is None` 且 `s.ohmystock_log_level == "INFO"`
- [x] 4.5 執行 `uv run pytest -v`：所有測試通過，exit 0；無新警告（pytest collect 數量 ≥ 7：1 + 5 + 1）

## 5. 端對端驗收

- [x] 5.1 在 repo root 跑完整流程：`rm -rf .venv && uv sync && uv run ohmystock --help && uv run pytest`，全部成功
- [x] 5.2 在新 shell 重複 5.1，驗證無 cache 情境也能正常啟動
- [x] 5.3 在 repo root 暫時建立 `.env` 含 `ANTHROPIC_API_KEY=test-value-not-real`，執行 `uv run python -c "from ohmystock.config import Settings; s = Settings(); assert s.anthropic_api_key == 'test-value-not-real'; print('ok')"`，應印 `ok`；測試後刪除 `.env`
- [x] 5.4 確認 `git status` 列出 `pyproject.toml`、`uv.lock`（modified）、`src/ohmystock/cli.py`、`src/ohmystock/config.py`、`tests/test_cli.py`（新增）；無多餘檔案（如 `.env`、`__pycache__`、`.pytest_cache/`）

## 6. 文件交叉檢查（不修改 docs/）

- [x] 6.1 確認 `pyproject.toml` 新增的 `typer` / `pydantic-settings` 與 `CLAUDE.md` §3 技術棧無衝突（不在 §3 表中、但 §3 未禁止；屬「§3 表內所列以外、可自由選的 utility deps」）
- [x] 6.2 確認 5 子命令名稱（`run` / `backtest` / `review` / `propose` / `screen`）與 `docs/design-zh-TW.md` §4.0 對 CLI 五大流程的描述一致；若 docs 未明列子命令名稱則 NOT-A-BLOCKER
- [x] 6.3 確認本 change 沒有修改任何 `docs/*.md` 檔案（`git diff docs/` 應為空）

## 7. Archive 前準備

- [x] 7.1 執行 `openspec validate cli-skeleton`，驗證 spec delta 結構正確（4 hashtag scenarios、MODIFIED 完整複製）
- [x] 7.2 執行 `openspec status --change cli-skeleton --json`，確認所有 task 已 `[x]`、artifact 全 `done`
- [x] 7.3 草擬 commit message：`feat(cli): typer cli with 5 stub subcommands + pydantic-settings config loader`
