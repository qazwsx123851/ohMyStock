# Capability: post-trade-review-pipeline

Source: synced from openspec/changes/archive/2026-05-10-phase5-review-mvp/specs/post-trade-review-pipeline/spec.md


### Requirement: Pipeline 以固定順序 sequential 執行 5 節點

系統 SHALL 提供 `ohmystock.review.pipeline.run_review(period_from, period_to, db_conn, *, kind="manual", force=False, limit_trades=None, dry_run=False, out_dir, proposals_dir, llm_factory=None) -> ReviewResult` 函式，內部以**嚴格 sequential 順序**執行 `data_loader` → `attributor` → `aggregator` → `critic` → `proposer` 五個節點。每個節點 output SHALL 在進入下一節點之前**完整寫入** `out_dir/<review_id>/`（除 `dry_run=True` 之外）。任一節點拋例外 SHALL 中止 pipeline，已落檔的中間檔 SHALL 保留以利 debug。

#### Scenario: 5 節點按順序呼叫且每節 output 落檔
- **WHEN** 以 23 筆 entry / 8 筆 reject 的合成 journal 呼叫 `run_review(2026-04-01, 2026-04-30, conn, out_dir=tmp)`
- **THEN** `tmp/manual-2026-04-01-to-2026-04-30/` SHALL 依序出現 `data.json`（data_loader 完成後）→ `attribution.json`（attributor 完成後）→ `metrics.json`（aggregator 完成後）→ `critique.md`（critic 完成後）→ `report.md` + `proposals_created.md`（proposer 完成後）

#### Scenario: 中途節點拋例外保留前段中間檔
- **WHEN** `attributor` 因 LLM 回應 schema 錯誤拋 `AttributorOutputParseError`
- **THEN** pipeline SHALL 中止；`data.json` SHALL 已存在；`attribution.json` SHALL **不**存在；`metrics.json` SHALL **不**存在；`reviews/_index.json` SHALL **不**被更新

#### Scenario: dry_run 不落任何檔案
- **WHEN** 以 `dry_run=True` 呼叫 `run_review(...)`
- **THEN** pipeline SHALL 跑完所有 5 節點；`out_dir/` 與 `proposals_dir/` SHALL 完全沒有檔案產生；`reviews/_index.json` SHALL **不**被更新；回傳的 `ReviewResult` SHALL 包含 token / cost 預估

---

### Requirement: data_loader 走 deterministic pure-data 路徑

`data_loader` 節點 SHALL **不**呼叫任何 LLM。輸入為 `(period_from, period_to, journal_repository, market_data_loader)`，輸出 `data.json` SHALL 對齊 `docs/post-trade-review-rubric.md` §1 schema：頂層含 `period`、`trades`、`rejected`、`expired`、`stats` 五個 key。對每筆 `kind=exit` 的 row，`data_loader` SHALL 透過 `market_data_loader` 讀取出場後 21 個交易日的 daily close，計算 `post_exit_return_5d` / `post_exit_return_10d` / `post_exit_return_20d`（皆為小數，例 `0.018` 代表 +1.8%）。給定相同 journal + 相同 market_data fixture 時，產出 `data.json` SHALL byte-identical。

#### Scenario: post-exit returns 從真實 market_data 抓取
- **WHEN** 一筆 `exit_ts=2026-04-22T13:30:00+08:00` 的 trade 對應 symbol=2330 出場 close=900.0、後續第 5 / 10 / 20 個交易日 close 分別為 916、940、880
- **THEN** 該筆在 `data.json.trades[i]` 的 `post_exit_return_5d` SHALL 等於 `0.0178`（≈ 916/900-1，rounded to 4 decimal places）；`post_exit_return_10d` SHALL 等於 `0.0444`；`post_exit_return_20d` SHALL 等於 `-0.0222`

#### Scenario: 資料缺漏標 data_missing=true
- **WHEN** 一筆 trade 出場後 21 個交易日內 market_data 回傳 `select_bars` 不足 20 列（symbol 已下市）
- **THEN** 該筆 `data.json.trades[i]` SHALL 含 `"data_missing": true`；`post_exit_return_5d/10d/20d` SHALL 為 `null`

#### Scenario: 確定性重跑 byte-identical
- **WHEN** 對同一份 journal fixture 與同一份 market_data fixture **連續執行兩次** data_loader
- **THEN** 兩次 `data.json` 的 byte content SHALL 完全相同（含 key 順序、浮點精度、空白）

#### Scenario: 區間內 0 筆 entry 的空輸入
- **WHEN** 區間內 journal 沒有任何 row
- **THEN** `data.json` SHALL 含 `trades=[], rejected=[], expired=[], stats={"total_entries":0,"total_rejects":0,"total_expires":0,"expire_rate":0.0}`；不拋例外

---

### Requirement: attributor 採 rule-first + LLM fallback 分類

`attributor` 節點 SHALL 把每筆 `data.json.trades` 分類為 6 類之一：`thesis_held` / `thesis_failed_but_profit` / `thesis_failed_loss` / `stop_saved` / `time_stop_correct` / `time_stop_wrong`。當 `exit_tag in ('time_stop','hit_stop_loss','hit_t1','hit_t1_5','chandelier','thesis_invalid')` 時 SHALL 走 `docs/post-trade-review-rubric.md` §2 規則直接分類；其他 `exit_tag`（如 discretionary）SHALL 走 LLM。所有 trade（包含規則分類）SHALL 由 LLM 補一段 `evidence` 文字。`data_missing=true` 的 trade SHALL **強制**走 LLM fallback。輸出 `attribution.json` SHALL 含頂層 `attribution` 陣列 + `category_distribution` 6 個 key 計數。

#### Scenario: time_stop 出場且 5 日後漲 > 5% 走 time_stop_wrong
- **WHEN** 一筆 trade `exit_tag="time_stop"`、`post_exit_return_5d=0.062`
- **THEN** `attribution.json.attribution[i].category` SHALL 等於 `"time_stop_wrong"`，**不**呼叫 LLM 做分類（仍呼叫 LLM 補 evidence）

#### Scenario: stop_loss 出場且 10 日續跌 > 5% 走 stop_saved
- **WHEN** 一筆 trade `exit_tag="hit_stop_loss"`、`post_exit_return_10d=-0.083`
- **THEN** `attribution.json.attribution[i].category` SHALL 等於 `"stop_saved"`

#### Scenario: discretionary exit 走 LLM 分類
- **WHEN** 一筆 trade `exit_tag="discretionary"`
- **THEN** attributor SHALL 呼叫 LLM；LLM 回傳的 `category` SHALL 屬於 6 類 Literal，否則 `AttributorOutputParseError` 中止 pipeline

#### Scenario: data_missing=true 強制走 LLM
- **WHEN** 一筆 trade `exit_tag="hit_t1"`、`data_missing=true`
- **THEN** attributor SHALL **不**走 hit_t1 規則直接分類，而是呼叫 LLM 取得 category + evidence

#### Scenario: 6 類計數總和等於分類過的 trade 數
- **WHEN** 23 筆 trade 全部分類完成
- **THEN** `attribution.json.category_distribution` 6 個值的總和 SHALL 等於 `len(attribution)` SHALL 等於 23

---

### Requirement: aggregator 算 7 維度 metrics deterministic

`aggregator` 節點 SHALL **不**呼叫任何 LLM。輸入 `data.json` + `attribution.json`，輸出 `metrics.json` SHALL 對齊 `docs/post-trade-review-rubric.md` §3 schema，頂層含 `overall` / `by_skill` / `by_pattern` / `by_exit_tag` / `by_confidence` / `by_sector` / `rejection_breakdown` 七個 key。`overall` SHALL 至少含 `win_rate` / `profit_factor` / `expectancy_pct` / `max_drawdown_pct` / `max_consecutive_loss` / `avg_hold_days`。給定相同 input，aggregator SHALL byte-identical 重跑。

#### Scenario: overall.win_rate 計算正確
- **WHEN** 23 筆 trade 中 13 筆 `pnl_pct > 0`、10 筆 `pnl_pct <= 0`
- **THEN** `metrics.json.overall.win_rate` SHALL 等於 `0.5652`（13/23，rounded to 4 decimal places）

#### Scenario: profit_factor 計算正確
- **WHEN** 13 筆獲利合計 +84.5%、10 筆虧損合計 -45.9%
- **THEN** `metrics.json.overall.profit_factor` SHALL 等於 `1.84`（rounded to 2 decimal places）

#### Scenario: by_skill 對每個 cited_skill 統計
- **WHEN** 12 筆 trade `cited_skills` 含 `"technical/breakout"`，其中 7 勝 5 負
- **THEN** `metrics.json.by_skill["technical/breakout"]` SHALL 含 `{"n": 12, "win_rate": 0.5833, "expectancy": <pct>}`

#### Scenario: 空輸入產出 zero metrics 不除零
- **WHEN** `data.json.trades=[]` 且 `attribution.json.attribution=[]`
- **THEN** `metrics.json.overall` SHALL 含 `{"win_rate": 0.0, "profit_factor": 0.0, "expectancy_pct": 0.0, ...}`；不拋 `ZeroDivisionError`

#### Scenario: rejection_breakdown 列 4 層
- **WHEN** journal 含 5 筆 `kind=reject` 分屬 `pre_check / llm / risk_gate / human` 不同層
- **THEN** `metrics.json.rejection_breakdown` SHALL 含 4 個 key（即使該層 0 筆，仍 SHALL 出現 `{"count": 0, "top_reason": null}`）

---

### Requirement: critic 寫 critique.md 並引用 metrics.json JSON pointer

`critic` 節點 SHALL 呼叫 LLM（model = `claude-opus-4-7`，input 含 `docs/workflow-cheatsheet.md` 全文 + `metrics.json`），輸出 `critique.md` 自然語言批評。`critique.md` SHALL 至少分「高警示 / 中警示 / 觀察項」三段（標題以 `### ` 開頭即可）。每條警示 SHALL 引用至少一個 `metrics.json` JSON pointer 字串（例 `metrics.json#/by_pattern/VCP`）。critic 的 LLM input SHALL 透過 Anthropic prompt caching 標記 cheatsheet 段為 `cache_control: {"type":"ephemeral"}`。critic 的 LLM input total token 數 SHALL ≤ 80,000。

#### Scenario: critique.md 引用具體 JSON pointer
- **WHEN** `metrics.json.by_pattern.VCP.win_rate=0.375` 且 `n=8`
- **THEN** `critique.md` SHALL 至少出現一次 `metrics.json#/by_pattern/VCP` 子字串

#### Scenario: critic input token budget 守住
- **WHEN** critic 收到 cheatsheet 全文（≈ 50K tokens）+ metrics.json（≈ 4K tokens）+ system prompt
- **THEN** input total token count SHALL ≤ 80,000；超過時 SHALL 拋 `CriticTokenBudgetExceededError`，**不**截斷 cheatsheet 後送出

#### Scenario: 空 metrics（0 trades）critique.md 仍產出但無警示
- **WHEN** `metrics.json.overall.win_rate=0` 且 `total_trades=0`（區間內無交易）
- **THEN** `critique.md` SHALL 產生並含「本期無交易，無警示」字樣；不呼叫 proposer 產生提案

---

### Requirement: proposer 寫 0..N proposals 與 proposals_created.md

`proposer` 節點 SHALL 呼叫 LLM（model = `claude-opus-4-7`，input = `critique.md` + `metrics.json`），對每條「高警示」與「中警示」產出 1 份 proposal markdown，呼叫 `proposal-writer` 寫到 `proposals_dir/`。同時 SHALL 寫 `reviews/<review_id>/proposals_created.md` 含 markdown 表格，列出本次產出的所有提案連結（含 `[skipped: file exists]` 標記未實際寫入的）。若 `critique.md` 無警示（含「觀察項」），SHALL 產出 0 份提案，`proposals_created.md` 內容 SHALL 為「本期無提案」。

#### Scenario: 高警示產出對應提案
- **WHEN** `critique.md` 含 1 條高警示 `VCP 命中率 37.5%`
- **THEN** `proposals_dir/<YYYY-MM-DD>-vcp-volume-threshold.md`（或類似 topic）SHALL 出現；`proposals_created.md` SHALL 含一列指向此提案的 markdown link

#### Scenario: 提案檔已存在則 skip 並標記
- **WHEN** `proposals_dir/2026-04-30-vcp-volume-threshold.md` 已存在（人工修過），proposer 嘗試寫同 topic
- **THEN** proposer SHALL **不**覆寫該檔（透過 proposal-writer 的衝突 suffix 邏輯寫到 `-2.md` 或 skip）；`proposals_created.md` 標 `[skipped: file exists]`

#### Scenario: 0 警示產出 0 提案
- **WHEN** `critique.md` 完全無「高 / 中警示」標題段落
- **THEN** `proposals_dir/` SHALL 無新增檔；`proposals_created.md` SHALL 寫「本期無提案」字樣

---

### Requirement: reviews/<period>/ 輸出檔案布局對齊 reviews/README.md §3

每次 review 完成（非 dry_run）SHALL 在 `out_dir/<review_id>/` 產出**至少**以下 6 個檔：`data.json`、`attribution.json`、`metrics.json`、`critique.md`、`report.md`、`proposals_created.md`。`<review_id>` 在 v0 SHALL 強制為 `manual-<from>-to-<to>` 格式（`<from>` / `<to>` 為 ISO date `YYYY-MM-DD`）。`report.md` SHALL 含期間概覽 + 頂層 2-3 段摘要 + 連結到 attribution / metrics / proposals。

#### Scenario: review_id 命名固定
- **WHEN** `run_review(2026-04-01, 2026-04-30, ..., kind="manual")`
- **THEN** `out_dir/manual-2026-04-01-to-2026-04-30/` SHALL 出現；其他命名變體（`2026-04` / `forced-2026-04`）SHALL **不**被本 capability 使用

#### Scenario: 6 個必產檔皆存在
- **WHEN** review 跑完
- **THEN** `out_dir/<review_id>/` SHALL 至少含檔名 `data.json`、`attribution.json`、`metrics.json`、`critique.md`、`report.md`、`proposals_created.md`

---

### Requirement: reviews/_index.json 以 atomic rename 維護

每次 review 跑完（非 dry_run）SHALL 在 `out_dir/_index.json` append/update 一筆紀錄，至少含 `review_id` / `kind` / `period.from` / `period.to` / `trade_count` / `win_rate` / `pf` / `proposals_created` / `completed_at`（ISO-8601 含 `+08:00`）。`schema_version` SHALL 為 `"v3.0"`。寫入 SHALL 採「讀整檔 → in-memory 修改 → 寫 temp file → `os.replace`」三步驟以保 atomic。同 `review_id` 已存在 SHALL **更新該筆**（覆寫 metric），SHALL **不**追加重複 row。

#### Scenario: 首次跑建立 _index.json
- **WHEN** 對空 out_dir 跑 review 完成
- **THEN** `out_dir/_index.json` SHALL 出現；JSON parse 後 `reviews` 陣列 SHALL 含 1 筆且 `review_id` 對應本次

#### Scenario: 同 review_id 重跑 update 不 append
- **WHEN** 對已存在 `_index.json`（含 `review_id="manual-2026-04-01-to-2026-04-30"` 的 row）以 `--force` 重跑同區間
- **THEN** `_index.json.reviews` 陣列 SHALL 仍只有 1 筆對應該 review_id（即更新後的 metric），**不**出現 2 筆

#### Scenario: 寫入過程 crash 不留半套檔
- **WHEN** `_index.json` 寫入過程中（temp file 已寫但 rename 前）crash
- **THEN** 既有 `_index.json` SHALL 保持上一次完整內容；temp file 殘留 SHALL **不**讓 JSON parse 失敗

---

### Requirement: --force 覆寫 reviews/<period>/ 既有檔案

`run_review(...)` SHALL 接受 `force: bool` 參數。`force=False`（預設）且 `out_dir/<review_id>/` 已存在 SHALL 拋 `ReviewAlreadyExistsError`，**不**寫任何檔。`force=True` SHALL 覆寫 `out_dir/<review_id>/` 內既有 6 個檔。**`proposals_dir/` 內既有檔永遠不被 `force` 覆寫**（受 proposal-writer 的 collision suffix 規則保護）。

#### Scenario: 預設拒絕覆寫
- **WHEN** `out_dir/manual-2026-04-01-to-2026-04-30/` 已存在，呼叫 `run_review(..., force=False)`
- **THEN** SHALL 拋 `ReviewAlreadyExistsError`；既有檔內容 SHALL **不**變動

#### Scenario: --force 覆寫 reviews 但不動 proposals
- **WHEN** 既有 review folder + 既有 `proposals/2026-04-30-vcp-volume-threshold.md`，以 `force=True` 重跑
- **THEN** `reviews/<review_id>/` 6 個檔 SHALL 被覆寫；`proposals/2026-04-30-vcp-volume-threshold.md` SHALL **不**被覆寫；新提案若 topic 同名 SHALL 寫到 `-2.md`

---

### Requirement: LLM 呼叫成本寫入 llm_costs 表

attributor / critic / proposer 三個節點每次 LLM 呼叫 SHALL 在 `llm_costs` 表 INSERT 一筆 row：`decision_id` 欄填 `<review_id>`（如 `"manual-2026-04-01-to-2026-04-30"`，**不**填 trade decision id）；`model` 欄填實際使用 model（`claude-sonnet-4-6` / `claude-opus-4-7`）；`input_tokens` / `output_tokens` / `cost_usd` 欄填 LLM 回應的 usage 欄位換算結果；`created_at` 欄填當下 ISO-8601 含 `+08:00`。`dry_run=True` SHALL **不**寫 llm_costs（即使 LLM 真有被呼叫做估算）。

#### Scenario: 每次 LLM call 寫一筆 cost row
- **WHEN** 一次 review 內 attributor 呼叫 1 次、critic 1 次、proposer 1 次
- **THEN** `llm_costs` 表 SHALL 新增 3 筆 row，`decision_id` 全部等於該 review_id

#### Scenario: cost row 區分 review vs trade decision
- **WHEN** 既有 `llm_costs` 已含 trade decision row（`decision_id="dec_2026-04-15T..."`）
- **THEN** SQL `SELECT COUNT(*) FROM llm_costs WHERE decision_id LIKE 'manual-%'` SHALL 等於本次 review 的 LLM call 次數

#### Scenario: dry_run 不寫 llm_costs
- **WHEN** `run_review(..., dry_run=True)` 完成
- **THEN** `llm_costs` 表 row 數 SHALL 與呼叫前完全相同
