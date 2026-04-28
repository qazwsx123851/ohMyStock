## MODIFIED Requirements

### Requirement: CLI 子命令骨架

系統 SHALL 在 `ohmystock` CLI 提供六個子命令：`run`、`backtest`、`review`、`propose`、`screen`、`api`。前五個（`run` / `backtest` / `review` / `propose` / `screen`）在當前階段 SHALL 為 stub：執行時印 `not implemented` 至 stdout 並以 exit code 1 結束，避免 shell pipeline 誤判為成功。第六個子命令 `api` SHALL **非** stub：執行時 SHALL 透過 `uvicorn` 啟動 `ohmystock.api.app:create_app` factory（dev mode 預設 `--reload`），並接受 `--host` / `--port` / `--reload / --no-reload` 旗標。子命令的真實邏輯由後續 change 補完（`run`：LLM Decider 主流程；`backtest`：歷史回測；`review`：Phase 5 復盤 swarm；`propose`：策略改動提案；`screen`：股票篩選；`api` 已於本 change 完成 server 啟動骨架）。

#### Scenario: root help 列出六個子命令
- **WHEN** 執行 `uv run ohmystock --help`
- **THEN** stdout 同時包含 `run`、`backtest`、`review`、`propose`、`screen`、`api` 六個子命令名稱

#### Scenario: 前五個子命令 stub 行為一致
- **WHEN** 執行 `uv run ohmystock <子命令>`（其中 `<子命令>` 為 `run` / `backtest` / `review` / `propose` / `screen` 任一）
- **THEN** 命令以 exit code 1 結束，stdout 包含字串 `not implemented`

#### Scenario: 子命令各自有 help
- **WHEN** 執行 `uv run ohmystock <子命令> --help`（六者任一）
- **THEN** 命令以 exit code 0 結束，stdout 包含該子命令的說明文字（不為空字串、不為 generic placeholder）

#### Scenario: `api` 子命令不為 stub
- **WHEN** 執行 `uv run ohmystock api --help`
- **THEN** 命令以 exit code 0 結束，stdout 不含字串 `not implemented`，且至少包含 `--host` 與 `--port` 兩個旗標名稱

## ADDED Requirements

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
