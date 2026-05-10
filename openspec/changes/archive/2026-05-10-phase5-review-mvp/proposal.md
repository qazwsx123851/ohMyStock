## Why

Phase 5（LLM 月度復盤）是 v3 自我改進閉環的入口，但目前所有上游零件（trade-journal-schema / market-data-cache / memory-store / cost-tracking）都已 archive，**沒有任何下游把 trade journal 消化成 `reviews/<period>/` + `proposals/<id>.md`**。在沒有這層之前，Trade Journal 只進不出、Phase 5 系列文件（`docs/post-trade-review-rubric.md`、`reviews/README.md`、`proposals/README.md`）也只是空 README。

本 change 切出**最小可行**的 Phase 5 vertical slice：5 節點 sequential pipeline + 寫檔 + CLI 觸發，刻意**不**做 §16 WFA 驗證閘 / 人工合併流程 / `web-admin` Reviews 頁 / `reviews/_golden/` regression set / 自動排程觸發 — 這些每一項都是後續 change 的範圍，先把「raw journal → 提案 markdown」這條路走通。

## What Changes

- 新增 `src/ohmystock/review/` pipeline，5 個 node 物件 sequential 執行：`data_loader` → `attributor` → `aggregator` → `critic` → `proposer`。每個 node 各自有 input/output pydantic model，output 即時寫到 `reviews/<period>/`，下個 node 從檔案重讀（簡化重跑與 debug）。
- `data_loader`（pure data，無 LLM）：從 `journal_entries` 撈區間 `kind in ('entry','exit','reject','expire')`，對每筆 `exit` 透過 `market_data_tool.get_kline` 抓出場後 5/10/20 個交易日後的收盤計算報酬，組成 `data.json`。資料缺漏（停牌 / 下市）標 `data_missing: true`，不參與聚合。
- `attributor`（Sonnet 4.6）：逐筆把交易分類為 6 類（`thesis_held` / `thesis_failed_but_profit` / `thesis_failed_loss` / `stop_saved` / `time_stop_correct` / `time_stop_wrong`），同時寫 `evidence` 證據文字。`exit_tag in ('time_stop','hit_stop_loss','hit_t1','hit_t1_5','chandelier','thesis_invalid')` 走規則直接分類；其餘走 LLM。輸出 `attribution.json`。
- `aggregator`（pure data，無 LLM）：依 `overall / by_skill / by_pattern / by_exit_tag / by_confidence / by_sector / rejection_breakdown` 7 維度算命中率 / 期望值 / PF / MDD，輸出 `metrics.json`。**不**算 `time_series` / 跨月趨勢（v0 只看單一區間）。
- `critic`（Opus 4.7，input 含 cheatsheet 全文）：對比 rubric §4 的 7 條警示規則，輸出 `critique.md` 自然語言批評，必須引用 `metrics.json` 的 JSON pointer。
- `proposer`（Opus 4.7）：把高/中警示轉成 0..N 份 `proposals/<YYYY-MM-DD>-<topic>.md`，status 只會是 `pending`（**不**呼叫驗證閘、**不**改成 `validating`/`approved`/`merged`）。同時寫 `reviews/<period>/proposals_created.md` 含提案連結表格。
- 新增 `src/ohmystock/proposal/` writer：產生符合 `proposals/README.md` §4 模板的 markdown（必填 frontmatter + 必填 8 段內文），檔名 `<YYYY-MM-DD>-<topic>.md`；topic kebab-case ≤ 40 字、檔名衝突時自動加 `-2 / -3` suffix。**只寫**新檔，不做狀態轉換、不移檔到 `merged/` `rejected/` `PENDING_REVIEW/`。
- 新增 CLI `uv run ohmystock review --from YYYY-MM-DD --to YYYY-MM-DD [--out-dir reviews/] [--proposals-dir proposals/] [--limit-trades N] [--dry-run]`；`--dry-run` 跑全部 node 但不落檔（給 token 預估用）；`--limit-trades` 把 data_loader 結果截到 N 筆（給回放/debug）。
- 維護 `reviews/_index.json`：每次 review 完成 append 一筆 `{review_id, kind, period, trade_count, win_rate, pf, proposals_created, completed_at}`；`kind` MVP 固定 `manual`（月度自動 / 季度自動 / 月度熔斷強制觸發都是後續 change）。
- LLM 呼叫**全部**寫入 `llm_costs` 表（trade-journal-schema 已建好），`decision_id` 欄填 `review_id`（如 `manual-2026-04-01-to-2026-04-30`）以便日後與交易決策成本分流統計。
- **明確不做（deferred to follow-up changes）**：§16 WFA 驗證閘 / 提案狀態轉換到 `validating`+ / 自動 PR 開單 / 人工 ConfirmDialog merge / `proposal_tool` API / web-admin `/reviews` 與 `/proposals` 頁 / EventBus `review_completed` event / 月度自動排程 / 季度自動排程 / 月度熔斷強制觸發 / `reviews/_golden/` regression set / Phase 5 `attribution` 跨月趨勢 / Memory store integration（review summary 寫進 `memory_rows`）。

## Capabilities

### New Capabilities
- `post-trade-review-pipeline`: 5-node sequential post-trade review runner — data_loader / attributor / aggregator / critic / proposer，逐節點落檔到 `reviews/<period>/`，維護 `reviews/_index.json`。
- `proposal-writer`: 結構化策略改動提案 markdown 寫入器 — 產 `proposals/<YYYY-MM-DD>-<topic>.md`（status=pending only），對齊 `proposals/README.md` §4 模板，**無**狀態轉換。
- `post-trade-review-cli`: `uv run ohmystock review` Typer 子命令 — 手動觸發 pipeline，含 `--dry-run` / `--limit-trades` / `--from` / `--to` / `--out-dir` / `--proposals-dir` flag。

### Modified Capabilities
（無 — 本 change 只**消費** trade-journal-schema / market-data-cache / cost-tracking 既有 spec，不改變它們的 requirement。）

## Impact

- **新增程式碼**（皆為新 module，無既有檔修改）
  - `src/ohmystock/review/{__init__,nodes,pipeline,writer,index}.py` — 5 個 node + sequential runner + reviews/_index.json 維護
  - `src/ohmystock/review/prompts/{attributor,critic,proposer}.md` — 三個 LLM node 的 system prompt
  - `src/ohmystock/proposal/{__init__,writer,schema}.py` — 提案 markdown writer + 模板驗證
  - `src/ohmystock/cli/_review.py` — Typer 子命令；註冊到既有 `cli/__init__.py`
  - `tests/review/`、`tests/proposal/`、`tests/cli/test_review.py` — 黃金檔比對 + 各 node 純函式測試 + CLI smoke
- **產出檔案**（執行時寫入 repo 內容）
  - `reviews/<period>/{data,attribution,metrics}.json`、`reviews/<period>/{critique,report,proposals_created}.md`、`reviews/_index.json`
  - `proposals/<YYYY-MM-DD>-<topic>.md`（0..N 份；可能為 0 — 區間表現好的話 critic 不出警示就不出提案）
- **依賴 / 上游 spec**（read-only consumer，**不**改其 requirement）
  - `trade-journal-schema`：讀 `journal_entries` + 寫 `llm_costs`
  - `market-data-cache`：讀 daily kline 計算 post-exit 5/10/20 日報酬
  - `cost-tracking`：寫 `llm_costs` row（decision_id=review_id）
  - `cli-and-config`：註冊 `review` 子命令到既有 typer app
- **配置 / 環境變數**（皆已存在於 `Settings`，**不**需新增）
  - `anthropic_api_key`：3 個 LLM node 共用
  - `ohmystock_db_path`：sqlite 連線
  - `ohmystock_llm_degrade`：本 change **不**強制讀 — degrade 模式下走 fail-loud（v0 不為節省成本退化到 Haiku）
- **不影響的範圍**（明確列出避免後續誤改）
  - web-admin frontend：完全沒變動，Reviews 頁是後續 change
  - EventBus：不發 `review_started` / `review_completed` event（後續 change 補）
  - Memory store：不寫 `memory_rows.kind=review_summary`（後續 change 補）
  - 既有 LLM Decider / Confirm Gate / Exit Engine / Auto-execute：完全獨立，不耦合
- **預估月度執行成本**（單次月度復盤，假設 23 筆 entry + 8 筆 reject）
  - attributor（Sonnet 4.6）：~25K input / 4K output ≈ $0.13
  - critic（Opus 4.7）：~50K input（含 cheatsheet）/ 4K output ≈ $1.05
  - proposer（Opus 4.7）：~30K input / 8K output ≈ $1.05
  - 合計 ≈ $2.2 / 月，落在 CLAUDE.md §3 月度預算 $20-36 內
