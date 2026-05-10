## 1. Module scaffolding

- [x] 1.1 在 `src/ohmystock/review/` 加 `__init__.py` export 公開 API（`run_review`、`ReviewResult`、`ReviewAlreadyExistsError` 等）；既存空 namespace package 維持
- [x] 1.2 在 `src/ohmystock/review/` 建子目錄 `prompts/`，預留 `attributor.md` / `critic.md` / `proposer.md` 三個空白 system prompt 檔
- [x] 1.3 在 `src/ohmystock/proposal/` 加 `__init__.py` export（`ProposalDraft`、`write_proposal`、`parse_proposal`、`ProposalParseError`）
- [x] 1.4 在 `tests/review/` 與 `tests/proposal/` 建空目錄 + `__init__.py`；放 `tests/review/fixtures/.gitkeep`

## 2. proposal-writer capability（最先做，pipeline 倚賴）

- [x] 2.1 寫 `src/ohmystock/proposal/schema.py` 含 `ProposalDraft` pydantic frozen model，欄位齊全且 `extra="forbid"`；topic 用 `field_validator` 檢 kebab-case + 1-40 字；motivation 用 `field_validator` 檢需含 `metrics.json#`
- [x] 2.2 寫 `src/ohmystock/proposal/writer.py::write_proposal(draft, proposals_dir) -> Path`：建檔名 `<YYYY-MM-DD>-<topic>.md`、collision 加 `-2`/`-3`/.../`-99` suffix、>99 拋 `RuntimeError("too many proposals...")`
- [x] 2.3 在同檔 `writer.py` 寫 markdown 模板 helper（YAML frontmatter + 8 個 `## N. <title>` 段落 + 變更紀錄含 created 行），status 強制 `"pending"`
- [x] 2.4 寫 `parse_proposal(path) -> ProposalDraft` 反向解析 + `ProposalParseError`（缺段拋含欄位名 message）
- [x] 2.5 加 `tests/proposal/test_schema.py` 覆蓋 `ProposalDraft` 5 個 validator scenario
- [x] 2.6 加 `tests/proposal/test_writer.py` 覆蓋 status-forced / 8-section / proposal_id 對齊 / 變更紀錄行
- [x] 2.7 加 `tests/proposal/test_collision.py` 覆蓋 `-2 / -3 / -99 / >99` 四個衝突情境
- [x] 2.8 加 `tests/proposal/test_round_trip.py` 覆蓋 write + parse 取回原 draft

## 3. data_loader 節點（pure data，無 LLM）

- [x] 3.1 在 `src/ohmystock/review/models.py` 定義 `DataLoaderInput` / `DataLoaderOutput` pydantic（含 `period`、`trades`、`rejected`、`expired`、`stats` 五個 key）
- [x] 3.2 寫 `src/ohmystock/review/nodes/data_loader.py::run_data_loader(period_from, period_to, journal_repo, market_data_loader, *, limit_trades=None) -> DataLoaderOutput`，從 `journal_entries` 撈 4 種 kind
- [x] 3.3 對 `kind=exit` 的 row 透過 `market_data_loader.select_bars(symbol, exit_date, days=21)` 抓 21 個交易日 close，計算 `post_exit_return_5d/10d/20d`，rounded to 4 decimals
- [x] 3.4 缺資料（< 20 列）標 `data_missing=true` + 三個 return 欄為 `null`
- [x] 3.5 `limit_trades=N` 截 `trades` 前 N 筆（依 entry_ts ASC），`rejected` / `expired` 不截
- [x] 3.6 加 `tests/review/test_data_loader.py` 含 byte-identical 重跑 + post-return 計算正確 + data_missing 路徑 + 空輸入 + limit_trades

## 4. aggregator 節點（pure data，無 LLM）

- [x] 4.1 在 `src/ohmystock/review/models.py` 加 `MetricsOutput` pydantic（7 個頂層 key）
- [x] 4.2 寫 `src/ohmystock/review/nodes/aggregator.py::run_aggregator(data_output, attribution_output) -> MetricsOutput`，純 Python 算 7 維度
- [x] 4.3 計算 `overall.win_rate / profit_factor / expectancy_pct / max_drawdown_pct / max_consecutive_loss / avg_hold_days`；防除零（n=0 時直接回 0.0）
- [x] 4.4 `by_skill` / `by_pattern` / `by_exit_tag` / `by_confidence` / `by_sector` 對應分組統計；`by_confidence` 用固定 4 區間（0.6-0.7 / 0.7-0.8 / 0.8-0.9 / 0.9-1.0）
- [x] 4.5 `rejection_breakdown` 4 層恆出現（即使 0 筆）
- [x] 4.6 加 `tests/review/test_aggregator.py` 含 win_rate / PF 正確值 + 空輸入不除零 + 4 層 rejection 恆現

## 5. LLM client helper

- [x] 5.1 寫 `src/ohmystock/review/llm_client.py::call_llm(model, system, user, schema, review_id, *, db_conn, expect_json=True, cache_blocks=None) -> tuple[T, CostRow]`，重用 `decider/node.py::AnthropicPMConclusionNode` 的 anthropic client 模式
- [x] 5.2 支援 `cache_blocks=[...]` 把指定段落以 `cache_control: {"type":"ephemeral"}` 標記（給 critic 的 cheatsheet 段用）
- [x] 5.3 LLM 完成後寫一筆 `llm_costs` row（`decision_id=review_id`、`model` / `input_tokens` / `output_tokens` / `cost_usd` / `created_at`）；`dry_run=True` 路徑由 caller 決定不寫
- [x] 5.4 加 `FakeReviewLLM` class（同 `FakePMConclusionNode` 概念）給測試用，model id 走 `fake://attributor` / `fake://critic` / `fake://proposer`
- [x] 5.5 加 `tests/review/test_llm_client.py` 含 cost row 寫入 + cache_blocks 標記 + JSON parse 失敗拋 specific exception

## 6. attributor 節點（LLM，rule-first）

- [x] 6.1 寫 `src/ohmystock/review/nodes/attributor.py::run_attributor(data_output, *, llm_factory, db_conn, review_id) -> AttributionOutput`
- [x] 6.2 實作 6-rule decision tree（time_stop / hit_stop_loss / hit_t1* / chandelier / thesis_invalid）走規則直接給 category；其他 + `data_missing=true` 走 LLM
- [x] 6.3 對所有 trade 都呼叫 LLM 補 `evidence` 文字（規則分類的 trade 也要）；prompt 寫到 `src/ohmystock/review/prompts/attributor.md`
- [x] 6.4 LLM 回傳 schema 不符（`category` 不是 6 類 Literal）拋 `AttributorOutputParseError`
- [x] 6.5 寫 `attribution.json` 含 `attribution[]` + `category_distribution` 6 key 計數
- [x] 6.6 加 `tests/review/test_attributor.py` 含 6 個規則路徑 + LLM fallback + data_missing 強制 LLM + parse error 拋例外

## 7. critic 節點（LLM，含 cheatsheet 全文）

- [x] 7.1 寫 `src/ohmystock/review/nodes/critic.py::run_critic(metrics_output, *, llm_factory, db_conn, review_id, cheatsheet_path) -> str`（回 `critique.md` 內容）
- [x] 7.2 prompt 寫到 `src/ohmystock/review/prompts/critic.md`，包含 rubric §4 的 7 條警示規則指引；要求 LLM 對每條警示引用 `metrics.json#` JSON pointer
- [x] 7.3 cheatsheet 全文用 `cache_blocks=[...]` 標 ephemeral cache
- [x] 7.4 input total token pre-flight check（用 `anthropic.tokenizer` 或近似）≤ 80,000；超過拋 `CriticTokenBudgetExceededError`
- [x] 7.5 空 metrics（`overall.total_trades=0`）路徑：critic 直接寫「本期無交易，無警示」不呼叫 LLM
- [x] 7.6 加 `tests/review/test_critic.py` 含 JSON pointer 引用 + token budget 超限拋例外 + 空 metrics 路徑 + cache_blocks 進 anthropic call args

## 8. proposer 節點（LLM，倚賴 proposal-writer）

- [x] 8.1 寫 `src/ohmystock/review/nodes/proposer.py::run_proposer(critique_md, metrics_output, *, llm_factory, db_conn, review_id, proposals_dir) -> ProposerResult`，回傳 `(written_paths: list[Path], skipped: list[str], proposals_created_md: str)`
- [x] 8.2 prompt 寫到 `src/ohmystock/review/prompts/proposer.md`；要求 LLM 對每條高/中警示輸出一份 JSON 物件對應 `ProposalDraft` 欄位
- [x] 8.3 把每份 LLM JSON parse 成 `ProposalDraft`、呼叫 `proposal.writer.write_proposal(...)`；衝突由 writer 處理；既有檔已存在被 skip 時收集到 `skipped` list
- [x] 8.4 產 `proposals_created.md` 含表格（提案連結 + status + priority + target，含 `[skipped: file exists]` 標記）；無提案時寫「本期無提案」
- [x] 8.5 critique 無高/中警示段落時直接 0 提案 + `proposals_created.md` 寫「本期無提案」
- [x] 8.6 加 `tests/review/test_proposer.py` 含成功寫多份 + skip 路徑 + 0 警示 + LLM JSON 不符 schema 拋 `ProposerOutputParseError`

## 9. _index.json 維護

- [x] 9.1 寫 `src/ohmystock/review/index.py::upsert_index_entry(out_dir, entry: IndexEntry) -> None`
- [x] 9.2 atomic write 三步驟：read 既有 → in-memory list 找同 `review_id` upsert → 寫 temp file → `os.replace`
- [x] 9.3 `IndexEntry` pydantic 含 `review_id / kind / period / trade_count / win_rate / pf / proposals_created / completed_at`；`schema_version` 在頂層 `_index.json` 為 `"v3.0"`
- [x] 9.4 首次寫入建立 `_index.json` 含 `schema_version` + `last_updated` + `reviews: []`
- [x] 9.5 加 `tests/review/test_index.py` 含首次建立 / upsert 不 append 重複 / atomic（temp file 殘留不破壞 parse）

## 10. pipeline runner

- [x] 10.1 寫 `src/ohmystock/review/pipeline.py::run_review(...)`，串接 1.1~9.x 全部
- [x] 10.2 review_id 強制 `manual-<from>-to-<to>`（`kind="manual"` only in v0；`kind` 參數保留給未來 change）
- [x] 10.3 `force=False` 且 `out_dir/<review_id>/` 已存在 → 拋 `ReviewAlreadyExistsError`，不寫任何檔
- [x] 10.4 每節點 output 立即落檔到 `out_dir/<review_id>/`；中段 crash 保留前段檔；index 只在最後一步更新
- [x] 10.5 `dry_run=True`：跑全部節點但 patch 掉所有 file write 與 `_index.json` 更新與 `llm_costs` 寫入；llm_factory 走 fake or 真實但不寫 cost
- [x] 10.6 寫 `report.md`（期間概覽 + 2-3 段摘要 + 連結到 attribution.json / metrics.json / proposals_created.md）
- [x] 10.7 加 `tests/review/test_pipeline_golden.py` 用 fake LLM + journal fixture，跑全 pipeline 後 byte-compare `data.json` + `metrics.json`、檢查另 4 個檔存在
- [x] 10.8 加 `tests/review/test_pipeline_force.py` 覆蓋 force=False 拒絕 + force=True 覆寫 review folder + 不覆寫 proposals
- [x] 10.9 加 `tests/review/test_pipeline_dry_run.py` 覆蓋 dry_run 不寫任何檔 + token 估算欄位回傳

## 11. CLI command

- [x] 11.1 寫 `src/ohmystock/cli/_review.py::review_cmd` Typer 命令含全部 8 個 flag
- [x] 11.2 在 `src/ohmystock/cli/__init__.py` 用 `app.command("review")(review_cmd)` 註冊
- [x] 11.3 ISO date 用 `datetime.date.fromisoformat` 解析；非 ISO 拋 `typer.BadParameter` → exit 2
- [x] 11.4 `--from > --to` 自檢 → exit 2 + stderr "period_from must be <= period_to"
- [x] 11.5 `--out-dir` / `--proposals-dir` 預設 `Path("reviews")` / `Path("proposals")`；不存在自動 mkdir
- [x] 11.6 `--limit-trades` 必須 ≥ 1，否則 exit 2
- [x] 11.7 `--dry-run` flag 傳到 `run_review(dry_run=True)`；stdout 印 token / cost 估算
- [x] 11.8 `--force` flag 傳到 `run_review(force=True)`；`ReviewAlreadyExistsError` 攔截 → exit 2 + stderr "review already exists"
- [x] 11.9 `--json` flag：用 `json.dumps` 印 11 個 key 的 summary
- [x] 11.10 runtime exception traceback 過濾掉 `Settings.anthropic_api_key` 與 `sk-ant-` 前綴字串後印 stderr → exit 3
- [x] 11.11 加 `tests/cli/test_review.py` 含 8 個 flag scenario + 退出碼 0/2/3 + traceback 不洩漏 API key

## 12. SSOT / 文件更新

- [x] 12.1 在 `CLAUDE.md` §5 SSOT 表加一列「Phase 5 review pipeline v0 — 5-node sequential / `manual-<from>-to-<to>` review_id / status=pending only / no §16 gate」指向本 change archive 後路徑 + `src/ohmystock/review/pipeline.py`
- [x] 12.2 在 `CLAUDE.md` §5 SSOT 表加一列「Proposal markdown writer v0 — frontmatter + 8 段內文 / status=pending forced / `-2..-99` collision suffix / no overwrite」指向本 change archive 後路徑 + `src/ohmystock/proposal/writer.py`
- [x] 12.3 在 `CLAUDE.md` §7 任務索引加「跑月度復盤？→ `uv run ohmystock review --from --to`」一行
- [x] 12.4 確認 `docs/post-trade-review-rubric.md` / `proposals/README.md` / `reviews/README.md` 對齊本 change 行為（不需大改，但若有衝突須在 `docs/v3-decisions.md` 加 follow-up note）

## 13. 手動 smoke test

- [x] 13.1 跑 `uv run ohmystock review --help` 確認 8 個 flag 列出
- [x] 13.2 用合成 journal 跑 `uv run ohmystock review --from 2026-04-01 --to 2026-04-30 --dry-run --json`，檢查 stdout 為合法 JSON 且 `proposals_files=[]`
- [x] 13.3 把 `--dry-run` 拿掉重跑，檢查 `reviews/manual-2026-04-01-to-2026-04-30/` 6 個檔出現 + `reviews/_index.json` 含 1 筆 + `proposals/` 含 0..N 份
- [x] 13.4 不傳 `--force` 重跑同區間，確認 exit code 2 + 既有檔不變
- [x] 13.5 傳 `--force` 重跑，確認 review folder 被覆寫 + 既有 `proposals/<topic>.md` 不被覆寫（若同 topic 走 `-2.md`）
- [x] 13.6 SQL `SELECT decision_id, model, cost_usd FROM llm_costs WHERE decision_id LIKE 'manual-%'` 檢查 cost row 寫入正確
