## Context

`scaffold-repo` archive 之後，repo 已有 17 個空殼子模組與 `pyproject.toml` 的 `ohmystock = "ohmystock.cli:main"` 宣告，但 `ohmystock.cli` 尚未實作。本 change 把 CLI 從「entry point 已宣告但模組不存在」推進到「`ohmystock --help` 可運作、5 個子命令 stub 各自能 print + exit 1」。`docs/design-zh-TW.md` §4.0 已拍板 CLI 為 ohMyStock 主入口（後續 `run` / `backtest` / `review` / `propose` / `screen` 五大流程的觸發點）；`CLAUDE.md` §3 技術棧已決定 Python 3.11+、不用 LangChain，但未指定 CLI / settings 框架，本 change 在這兩處作拍板。

## Goals / Non-Goals

**Goals:**
- `uv run ohmystock --help` 列出 `run` / `backtest` / `review` / `propose` / `screen` 五個子命令
- `uv run ohmystock <子命令> --help` 顯示對應子命令的 stub help（含 1-2 行說明文字，提示後續 change 會接邏輯）
- `uv run ohmystock <子命令>` 印 `not implemented` 並 exit 1（避免被誤以為成功）
- `from ohmystock.config import Settings; Settings()` 在缺所有 env var 時可建構成功，且讀得到 `.env`（若存在）
- 所有 lint / test 一致；pytest 通過 3 條最小測試

**Non-Goals:**
- 任何子命令的真實業務邏輯（留給 Phase 0c+）
- FastAPI 啟動 / `api` 子命令（留給 `fastapi-bootstrap`）
- Shioaji / FinMind / Anthropic 連線 / `smoke-test` 子命令（留給 `external-connectors-and-cost`）
- Logging / structlog 配置（這次 stub 直接 `print`，避免引入第三個依賴；後續 change 統一接）
- Settings 欄位的型別細究（如 `OHMYSTOCK_AUTO_EXECUTE` 字串轉 bool 規則）— 這次留 `Optional[str]` 即可，後續 change 在實際使用時再窄化

## Decisions

### D1：採用 `typer` 而非 `click` / `argparse`
**選 `typer`**：
- 純 type-hint 驅動，不需要 decorator boilerplate；與 `pydantic-settings` 風格一致
- 自帶子命令分組與 rich help 渲染，適合 5 子命令架構
- transitive 拉 `click`，所以後續若要混 `click`-based 套件不衝突
- 維護方為 tiangolo（與 FastAPI 同生態），與後續 `fastapi-bootstrap` 風格一致

**Alt 1 `click`**：成熟、無 type-hint 模式、decorator 較囉嗦
**Alt 2 `argparse`**：標準庫、零依賴，但 5 子命令 + 後續會擴張到 7+ 命令，手刻 subparser 與 help 較費神
**Alt 3 `fire`**：自動推斷介面，但 stub 行為（exit 1）較難控

依據：CLAUDE.md §2「避免過度工程」+ tiangolo 生態與 §3 Python 風格一致。

### D2：採用 `pydantic-settings.BaseSettings` 而非手刻 `os.environ`
**選 `pydantic-settings`**：
- 一次拿到「`.env` 自動載入 + 型別驗證 + 預設值」三件事，比手刻 30 行 `os.getenv` 短
- 後續 `external-connectors-and-cost` 會把 Anthropic / Shioaji / FinMind 的 settings 也綁進來，框架一次選定
- transitive 拉 `pydantic v2`，而 v3 後續可能會用到（如 LLM Decider 輸出驗證），先建立基礎

**Alt 1 手刻 `os.environ.get`**：零依賴，但 11 個欄位 + 預期將擴張到 ~20，重複代碼增加
**Alt 2 `dynaconf`**：功能多但學習曲線高，YAGNI

依據：YAGNI + 後續 change 必然會用到 pydantic 系列。

### D3：所有 Settings 欄位皆 `Optional` / 有預設，import 時不要求值
**選不強制**：
- stub 子命令在沒有 `.env` 時也要能跑（驗收條件之一）
- 後續 change 在實際呼叫 Anthropic / Shioaji 前自行檢核所需 key 存在，不在 import time 拋錯
- 與 `safety-and-simulation.md` §2.9 的「軟熔斷」原則一致：缺值是降級而非崩潰

**Alt** 必填欄位 import 時拋錯：開發體驗差，每次跑 `--help` 都要求設好所有 key

### D4：每個子命令 stub 印「not implemented」並 `raise typer.Exit(1)`
**選 exit 1**：
- exit 0 會讓 shell pipeline / CI 誤判成功，未來忘了實作會悄悄通過
- typer 的 `Exit` 比 `sys.exit` 更可被 CliRunner 攔截（測試用）
- 訊息固定字串 `not implemented`（不本地化、不加表情符），方便 grep 與測試斷言

### D5：CLI app callback 不做事；help 由 typer 自動生成
**不加 `--version` / `--verbose` 等 global flag**：留給後續 change 在實際需要時加（log level 已經可由 `OHMYSTOCK_LOG_LEVEL` env 控）。本 change 只擺骨架，避免 callback 變相做業務。

### D6：`main()` 函式對應 `pyproject.toml` 的 entry
```python
def main() -> None:
    app()
```
單純包一層讓 entry point 可以 reference；不放任何 setup（log 配置、signal handler 等）。

### D7：tests 寫在 `tests/test_cli.py` 用 `typer.testing.CliRunner`
- 測試經由 `CliRunner(app)` 執行，避免 subprocess 開銷
- 3 條測試：(a) `--help` 含 5 子命令名、(b) `run` 子命令 exit code = 1 且 stdout 含 `not implemented`、(c) `Settings()` 在無 env var 時建構成功且所有欄位為 `None` 或預設

## Risks / Trade-offs

- **[Risk]** typer 的 rich help 在 Windows cmd 顯示可能亂碼 → **Mitigation**：本機環境是 Git Bash + PowerShell，UTF-8 OK；後續若需支援 cmd，再加 `--no-rich` 選項
- **[Risk]** `pydantic-settings` v2 與後續 change 引入的 `pydantic v1` 套件衝突 → **Mitigation**：v3 已決策不引入 LangChain（CLAUDE.md §3），其他主要 deps（FastAPI、Anthropic SDK、Shioaji）皆 pydantic v2 相容
- **[Risk]** 5 個 stub 印同一句 `not implemented`，未來實作時可能漏改 → **Mitigation**：每個 stub 用獨立函式（不用 generic factory），且 task 列表會逐一驗收 `--help` 文字
- **[Trade-off]** `tests/test_cli.py` 用 `CliRunner` 而非 `subprocess.run("ohmystock ...")` → 不驗證 entry point 黏合，但安裝完整性已在 `scaffold-repo` 的 spec 涵蓋（`uv run ohmystock --help` 不再 ModuleNotFoundError 由 task 8 / 整合測試檢核）

## Migration Plan

不適用（增量擴充，無 rollback target）。若整張 change 想撤銷：刪除 `src/ohmystock/cli.py`、`src/ohmystock/config.py`、`tests/test_cli.py`，從 `pyproject.toml` 刪除 `typer` 與 `pydantic-settings` 兩行 dep，重跑 `uv sync` 即可恢復 scaffold-repo 末態。

## Open Questions

- 5 個子命令未來是否要分到子模組（如 `cli/run.py`、`cli/backtest.py`）？→ 暫不分；目前每個只有 3 行 stub，5 個全擺 `cli.py` 即可。等實作後（`cli.py` > 200 行）再拆，由後續 change 處理
- `Settings.OHMYSTOCK_DB_PATH` 預設值要不要直接 `Path(...).expanduser()`？→ 暫不展開；保留字串原樣（`~/.ohmystock/journal.db`），由後續 `journal/schema.py` change 在實際開檔時 `expanduser`
- 是否要在 `cli.py` 加 `__main__.py` 讓 `python -m ohmystock` 也能跑？→ 不加；console-script entry point 已足夠，多一個入口反而要多寫一份測試
