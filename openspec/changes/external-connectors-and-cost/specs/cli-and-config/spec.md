## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: smoke-test 子命令的非 stub 行為由 external-connectors capability 主管

系統 SHALL 將 `smoke-test` 子命令的執行細節（呼叫順序、PASS/FAIL 格式、各項目失敗時的 exit code 行為）交由 `external-connectors` capability 中對應 Requirement 定義；本 capability 僅約束「子命令存在於 CLI 且非 stub」。任何對 smoke-test 行為的修改 SHALL 走 `external-connectors` 的 spec delta 流程，不得透過修改 `cli-and-config` 描述變更實際行為。

#### Scenario: smoke-test 子命令出現在 ohmystock --help
- **WHEN** 執行 `uv run ohmystock --help`
- **THEN** stdout 包含 `smoke-test` 字串（與其他六個子命令同列）

#### Scenario: smoke-test 行為定義落在 external-connectors
- **WHEN** 檢視 `openspec/specs/external-connectors/spec.md`（archive 後）
- **THEN** 該檔 SHALL 含一條 Requirement 命名為「smoke-test CLI 子命令驗證三方連線」（或語意等價）
