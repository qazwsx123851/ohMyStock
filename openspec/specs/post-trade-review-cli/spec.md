# Capability: post-trade-review-cli

Source: synced from openspec/changes/archive/2026-05-10-phase5-review-mvp/specs/post-trade-review-cli/spec.md


### Requirement: 註冊 ohmystock review Typer 子命令

系統 SHALL 在既有 `ohmystock` Typer app（`src/ohmystock/cli/__init__.py`）註冊 `review` 子命令，入口函式 `ohmystock.cli._review.review_cmd`。`uv run ohmystock review --help` SHALL 列出本 spec 規範的全部 flag。命令名 SHALL **不**與既有 `decide` / `assemble` 等子命令衝突。

#### Scenario: --help 列出 review 子命令
- **WHEN** 執行 `uv run ohmystock --help`
- **THEN** stdout SHALL 列出 `review` 子命令名與簡短 description

#### Scenario: review --help 列出全部 flag
- **WHEN** 執行 `uv run ohmystock review --help`
- **THEN** stdout SHALL 列出 `--from` / `--to` / `--out-dir` / `--proposals-dir` / `--limit-trades` / `--dry-run` / `--force` / `--json` 八個 flag

---

### Requirement: --from 與 --to 必填且 ISO 格式

`--from` 與 `--to` SHALL 為必填參數，值 SHALL 為 `YYYY-MM-DD` ISO date。任一參數缺漏 SHALL `typer.Exit(code=2)` 並在 stderr 印錯誤訊息。任一參數非 ISO 格式 SHALL `typer.Exit(code=2)` 並在 stderr 印錯誤訊息。`--from` > `--to` SHALL `typer.Exit(code=2)` 並在 stderr 印 `"period_from must be <= period_to"` 同義訊息。

#### Scenario: 缺 --from 退出 code 2
- **WHEN** 執行 `uv run ohmystock review --to 2026-04-30`
- **THEN** exit code SHALL 為 `2`；stderr SHALL 含 `--from` 字樣

#### Scenario: --from 格式錯誤退出 code 2
- **WHEN** 執行 `uv run ohmystock review --from 2026/04/01 --to 2026-04-30`
- **THEN** exit code SHALL 為 `2`；stderr SHALL 含 `YYYY-MM-DD` 或同義 ISO format 字樣

#### Scenario: --from > --to 退出 code 2
- **WHEN** 執行 `uv run ohmystock review --from 2026-04-30 --to 2026-04-01`
- **THEN** exit code SHALL 為 `2`；stderr SHALL 含 `period_from` 字樣

---

### Requirement: --out-dir 與 --proposals-dir 預設值

`--out-dir` 預設為 `reviews/`（相對於 `Path.cwd()`）；`--proposals-dir` 預設為 `proposals/`。兩者 SHALL 接受相對與絕對路徑。若目錄不存在 SHALL 自動建立（`Path.mkdir(parents=True, exist_ok=True)`）。

#### Scenario: 預設目錄
- **WHEN** 執行 `uv run ohmystock review --from 2026-04-01 --to 2026-04-30`（不傳 `--out-dir` / `--proposals-dir`）
- **THEN** review 完成後 `<cwd>/reviews/manual-2026-04-01-to-2026-04-30/` SHALL 存在；可能寫出的提案 SHALL 在 `<cwd>/proposals/` 下

#### Scenario: 自訂目錄不存在自動建立
- **WHEN** 執行 `uv run ohmystock review --from 2026-04-01 --to 2026-04-30 --out-dir /tmp/test-reviews --proposals-dir /tmp/test-proposals`，且兩目錄事前不存在
- **THEN** 兩目錄 SHALL 被建立；review 完成後對應檔案出現

---

### Requirement: --limit-trades 截斷 data_loader 輸出

`--limit-trades N`（int ≥ 1）SHALL 把 `data.json.trades` 截到前 N 筆（依時間排序），用於 debug / 回放。**`rejected` 與 `expired` 不受此 flag 影響**（仍全量保留）。`limit_trades=None`（未傳 flag）SHALL 不截斷。`--limit-trades 0` 或負值 SHALL `typer.Exit(code=2)` 並印錯誤訊息。

#### Scenario: --limit-trades 5 只保留 5 筆 trades
- **WHEN** 區間內有 23 筆 entry，執行 `uv run ohmystock review --from 2026-04-01 --to 2026-04-30 --limit-trades 5`
- **THEN** `reviews/<review_id>/data.json.trades` SHALL 只含 5 筆；`rejected` / `expired` 仍為全量

#### Scenario: --limit-trades 0 退出 code 2
- **WHEN** 執行 `uv run ohmystock review --from 2026-04-01 --to 2026-04-30 --limit-trades 0`
- **THEN** exit code SHALL 為 `2`；stderr SHALL 含 `--limit-trades` 字樣

---

### Requirement: --dry-run 跑全 pipeline 但不寫檔

`--dry-run` flag SHALL 觸發 `pipeline.run_review(..., dry_run=True)`。所有 5 節點 SHALL 被執行（含 LLM 呼叫以估 token），但 SHALL **不**寫任何檔到 `--out-dir` 或 `--proposals-dir`，SHALL **不**更新 `_index.json`，SHALL **不**寫 `llm_costs` 表。stdout SHALL 印估算結果（總 input / output tokens、估算 cost USD、預估 0..N 提案數）。

#### Scenario: dry-run 不寫任何檔
- **WHEN** 執行 `uv run ohmystock review --from 2026-04-01 --to 2026-04-30 --dry-run`
- **THEN** `reviews/manual-2026-04-01-to-2026-04-30/` SHALL **不**存在；`reviews/_index.json` SHALL **不**存在或保持原狀；`proposals/` 下 SHALL 無新增檔；`llm_costs` 表 row 數 SHALL 不變

#### Scenario: dry-run 印 token 估算
- **WHEN** 執行 `uv run ohmystock review ... --dry-run`
- **THEN** stdout SHALL 含「input tokens」「output tokens」「estimated cost」三個關鍵字（中文或英文）

---

### Requirement: --force 覆寫既有 reviews/<period>/

`--force` flag SHALL 把 `pipeline.run_review(force=True)` 開啟。預設（不傳 `--force`）且 `<out-dir>/<review_id>/` 已存在 SHALL `typer.Exit(code=2)` 並在 stderr 印 `"review already exists"` 同義訊息。`--force` SHALL 覆寫既有 review folder 6 個檔；**SHALL 不**覆寫 `<proposals-dir>/` 下既有提案（受 proposal-writer 規則保護）。

#### Scenario: 預設拒絕覆寫退出 code 2
- **WHEN** `reviews/manual-2026-04-01-to-2026-04-30/` 已存在，執行 `uv run ohmystock review --from 2026-04-01 --to 2026-04-30`（不傳 `--force`）
- **THEN** exit code SHALL 為 `2`；stderr SHALL 含 `already exists` 字樣；既有 review folder 內容 SHALL **不**變動

#### Scenario: --force 覆寫 review folder
- **WHEN** 既有 review folder + 既有 `proposals/2026-04-30-vcp-volume-threshold.md`，執行 `uv run ohmystock review --from 2026-04-01 --to 2026-04-30 --force`
- **THEN** review folder 6 個檔 SHALL 被新版覆寫；exit code SHALL 為 `0`；既有提案檔 SHALL **不**被覆寫；新提案若 topic 同名 SHALL 寫到 `-2.md`

---

### Requirement: --json 印機器可讀 summary 到 stdout

`--json` flag SHALL 在 review 完成後以 JSON 格式印 summary 到 stdout，至少含 `review_id` / `period.from` / `period.to` / `trade_count` / `proposals_created` (int) / `proposals_files` (list of relative paths) / `total_input_tokens` / `total_output_tokens` / `total_cost_usd` / `out_dir` / `proposals_dir`。`--json` 與 `--dry-run` SHALL 可同時使用。預設（無 `--json`）SHALL 印人類可讀的多行摘要而非 JSON。

#### Scenario: --json 印 JSON 物件
- **WHEN** 執行 `uv run ohmystock review --from 2026-04-01 --to 2026-04-30 --json`
- **THEN** stdout 第一個非空白字元 SHALL 為 `{`；JSON parse 後 SHALL 含上述至少 11 個 key

#### Scenario: --json --dry-run 同時使用
- **WHEN** 執行 `uv run ohmystock review --from 2026-04-01 --to 2026-04-30 --dry-run --json`
- **THEN** stdout SHALL 為合法 JSON；含 `total_input_tokens` 等估算欄位；`proposals_files` SHALL 為空陣列

---

### Requirement: 退出碼語意

CLI SHALL 採以下退出碼，禁止使用其他值：

| Exit code | 語意 |
|---|---|
| 0 | review 成功完成（含 dry_run 成功） |
| 2 | 參數錯誤 / 既有 review 拒絕覆寫（pre-flight 失敗） |
| 3 | pipeline 內部錯誤（LLM parse 失敗、節點拋例外、I/O 錯誤等 runtime 失敗） |

退出碼 SHALL 與此表完全對應。pipeline 內部錯誤 SHALL 在 stderr 印 traceback 摘要（最後 3 frame 即可），但 SHALL **不**洩漏 `ANTHROPIC_API_KEY` 或同類 secret 內容。

#### Scenario: 成功跑完退出 0
- **WHEN** 執行成功的 review 命令
- **THEN** exit code SHALL 為 `0`

#### Scenario: 參數錯誤退出 2
- **WHEN** 執行 `uv run ohmystock review`（無 from/to）
- **THEN** exit code SHALL 為 `2`

#### Scenario: pipeline 內部錯誤退出 3
- **WHEN** attributor 因 LLM 回應 schema 錯誤拋 `AttributorOutputParseError`
- **THEN** exit code SHALL 為 `3`；stderr SHALL 含 traceback 摘要

#### Scenario: 內部錯誤 traceback 不洩漏 API key
- **WHEN** 任何 runtime exception traceback 印到 stderr
- **THEN** stderr 內容 SHALL **不**含 `Settings.anthropic_api_key` 的實際值或 `sk-ant-` 前綴的字串
