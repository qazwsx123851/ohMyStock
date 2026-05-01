## MODIFIED Requirements

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

## ADDED Requirements

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
