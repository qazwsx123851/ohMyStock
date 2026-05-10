## Context

Phase 5（v3 自我改進閉環的入口）所有上游 capability 已 archive：

- `trade-journal-schema` 提供 `journal_entries` 表（含 `kind in ('entry','exit','reject','expire')`）+ FTS5 索引 + `llm_costs` 表
- `market-data-cache` 提供 `select_bars(symbol, asof, days)` 讀 daily kline
- `cost-tracking` 已定義 `llm_costs` row 格式，等本 change 寫入
- `memory-store` 已部署但尚無 `kind=review_summary` row

但**沒有**任何下游消費這些資料。`docs/post-trade-review-rubric.md` 把 5 節點 DAG + 6 類歸因 + 7 條批判規則 + 提案模板都寫死了，等於 spec 已備、實作為零。同步地 `reviews/README.md` 與 `proposals/README.md` 約束了輸出檔案格式，本 change 必須**精確**對齊那兩份 README（不可自創欄位）。

`docs/v3-decisions.md` #14 把 LLM prompt 演進切到獨立通路（`prompts/decider.md`、`prompts/review.md`），不走 §16 提案閘 — 這意味著**本 change 的提案輸出僅針對 strategy code / cheatsheet 文字，不含 prompt 改動**。

CLAUDE.md §8 路線圖把 Phase 5 排在週 18-20（2026-09-15 完成）。**本 change 是 Phase 5 的第一個 MVP 砧板**，後續 change（WFA gate / web-admin 頁 / 自動排程 / `_golden/` set / proposal 狀態機 / EventBus 整合）會逐步補完。

## Goals / Non-Goals

**Goals:**

1. 把 `journal_entries` 區間查詢 → 5 節點 sequential pipeline → `reviews/<period>/` 6 個檔 + 0..N 份 `proposals/<id>.md` 這條路打通，且每一步都**可獨立重跑**（從中間檔案恢復）。
2. `data_loader` 與 `aggregator` **完全 deterministic**（純資料運算 + market_data 抓取），給定同一份 journal + 同一份 market data 必須產出 byte-identical `data.json` / `metrics.json`，方便 golden file 測試。
3. `attributor` / `critic` / `proposer` 三個 LLM node 各自走 **frozen pydantic schema**，LLM 輸出不符 schema 即 fail-loud（不靜默退化）。
4. CLI `uv run ohmystock review` 可獨立觸發，無需 web-admin / EventBus / scheduler 介入；給人手動跑、給未來 change 自動觸發都用同一個入口。
5. 所有 LLM 呼叫透過既有 `Settings.anthropic_api_key`，token / cost 寫入既有 `llm_costs` 表；`decision_id = review_id` 以利日後成本歸戶。
6. `reviews/_index.json` 在 review 完成的最後一步以 atomic rename 更新；中途 crash 不會留下半套 state。

**Non-Goals:**

- §16 WFA / Robust / 黃金樣本 / MDD 變化驗證閘 → 後續 `phase5-validation-gate` change
- 提案狀態機（`pending` → `validating` → `approved` / `rejected` / `merged`）+ 移檔 `merged/` `rejected/` `PENDING_REVIEW/` → 後續 `proposal-state-machine` change
- 人工 ConfirmDialog merge + GitHub PR 自動開單 + cheatsheet diff 套用 + git tag 版本 bump → 後續 `proposal-merge-flow` change
- web-admin `/reviews` 與 `/proposals` 頁面 + admin GET endpoints → 後續 `web-admin-review-pages` change
- EventBus `review_started` / `review_completed` event + serializer wiring → 後續 `eventbus-review-events` change
- 月度自動排程（每月 1 號 19:00）+ 季度自動 + 月度熔斷強制觸發（`forced-<period>/`）→ 後續 `phase5-scheduler` change
- `reviews/_golden/` regression set + `prompts/review.md` 黃金集驗閘 → 後續 `phase5-prompt-evolution` change（CLAUDE.md 已說「v1 啟動時可空著」）
- DAG 並行（5 節點之間有資料依賴鏈，不能並行；同時跑多個 period 也是後續，不在 v0 範圍）
- `attribution` 跨月趨勢 / `_index.json.timeseries(...)` 查詢 API（reviews/README.md §10）
- Memory store 整合（`memory_rows.kind=review_summary` 寫入）

## Decisions

### Decision 1: Sequential pipeline，**不**做 5 節點並行 DAG

5 節點是**嚴格資料依賴鏈**（`data_loader` → `attributor` → `aggregator` → `critic` → `proposer`），任何一節錯都讓後面整段失效。並行只在「同時跑多個 period」才有意義，但 v0 是手動 CLI 單次觸發，沒這需求。

選 sequential 的好處：
- 每節 output 即時落檔，crash 後可從任何節點 resume（`--resume-from <node>` 是後續 change，v0 必須整段重跑）
- 沒有 concurrency primitive、沒有 `asyncio.gather` 出錯路徑、沒有 deadline 排程；測試極簡
- 失敗時人為 debug 路徑直接（讀檔 + 讀 prompt + 讀 LLM response 即可）

代價：節點之間 I/O 多走一輪檔案 read/write（5 個節點 ≈ 5 次 read + 5 次 write）— 可忽略，每筆 review 跑時間數十秒級別。

**替代方案（已否決）**：reuse `src/ohmystock/swarm/runner.py` 的 entry-decider swarm DAG runner — 它支援節點並行，但 v0 用不到、且耦合到 `EntryDecisionInput` / `EntryDecisionOutput` model，引入更多無關依賴。

### Decision 2: 中間 state 寫檔（filesystem），**不**走 in-memory pipe

每個節點 output 寫到 `reviews/<period>/<node>.json` / `<node>.md`，下個節點從檔讀回。

理由：
- 可重跑：debug 時改 prompt 想只重跑 `critic` 不想重跑 `attributor`，filesystem 是 cache layer
- 可審視：crash 在 `critic` 時 `data.json` + `attribution.json` + `metrics.json` 都已落地，人類可直接讀
- 對齊 `reviews/README.md` §3 文件規範 — 那份 README 把每個檔當「永久保存的歷史記憶體」

代價：runtime 多 5 次磁碟 I/O — 在每次跑數十秒級別下毫秒級別 overhead 可忽略。

**替代方案（已否決）**：in-memory 物件 pipe — 跑得稍快，但 crash 即丟一切，且 `reviews/<period>/` 必落檔的需求逼著也要寫入，雙寫反而複雜。

### Decision 3: `data_loader` 與 `aggregator` 走 deterministic pure-data 路徑

兩個節點完全沒有 LLM 呼叫：

- `data_loader`：`journal_repository.list_entries(from, to, kinds=[entry,exit,reject,expire])` + 對每筆 `exit` 抓 `market_data.select_bars(symbol, exit_date, days=21)` 算 5/10/20 日 close 報酬
- `aggregator`：對 `data.json` + `attribution.json` 做純 Python 統計運算（命中率、PF、期望值、MDD、最大連敗）

好處：
- byte-identical 重跑可測（給定同 journal + 同 market_data，`metrics.json` MUST 完全相同）
- 用 golden file fixture 在 `tests/review/test_aggregator.py` 釘住 `metrics.json` schema 不漂移
- 省 token：每月省 ≈ 8K input × 0.003 ≈ $0.024，但更重要的是 schema 穩定性

**替代方案（已否決）**：用 LLM 跑 aggregator — rubric §3 列了 7 維度指標但每一條都是純算術；用 LLM 反而引入 hallucinate 風險（例如 PF 算錯）。

### Decision 4: `attributor` rule-first + LLM fallback

`exit_tag` 有 6 個確定值（`time_stop` / `hit_stop_loss` / `hit_t1` / `hit_t1_5` / `chandelier` / `thesis_invalid`），rubric §2 給出明確 if-else 規則：

```python
def attribute_trade(trade) -> Literal[<6 categories>]:
    if exit_tag == "time_stop":
        return "time_stop_wrong" if post_5d > 0.05 else "time_stop_correct"
    if exit_tag == "hit_stop_loss":
        return "stop_saved" if post_10d < -0.05 else "thesis_failed_loss"
    if exit_tag in ("hit_t1", "hit_t1_5", "chandelier"):
        return "thesis_held" if thesis_held else "thesis_failed_but_profit"
    if exit_tag == "thesis_invalid":
        return "thesis_failed_loss" if pnl_pct < 0 else "thesis_failed_but_profit"
    return llm_classify(trade)  # discretionary 才走 LLM
```

絕大多數 trade（≈ 85% 以上）走規則直接分類；只剩 discretionary exit 走 LLM。

但 `evidence` 文字（rubric §2 要求每筆都有）**全部**由 LLM 補 — 規則只能給類別、不能給佐證文字。所以 attributor 的 LLM 呼叫是「給每筆 trade 寫一段 evidence 解釋」，token 成本相對固定 ≈ 25K input / 4K output。

**替代方案（已否決）**：純規則跑（不寫 evidence）— 失去 rubric §2 的證據要求，下游 critic 引用佐證會斷鏈。

### Decision 5: `critic` input 包含 cheatsheet 全文 + prompt cache

rubric §4 的批判規則（「某 skill 拖累」「VCP 失效」等）必須對照 cheatsheet 條文判斷，prompt 必須包含 `docs/workflow-cheatsheet.md` 全文（≈ 50K tokens）。

對策：
- **Anthropic prompt caching** 開 ephemeral cache（5 分鐘 TTL）— cheatsheet 是 stable prefix，每月跑一次不會 cache hit，但同一次 review 內 critic 若需要重試可省 cost
- 第一次跑 cache miss = 50K full price；後續 90% 折扣（hit）— v0 設計上接受 cache miss
- 開 `cache_control: {type: "ephemeral"}` block 在 cheatsheet 段落

**替代方案（已否決）**：把 cheatsheet 切片只塞 critic 需要的章節 — 無法事先知道 critic 會關心哪段；切片邏輯本身就是新的 skill；複雜度不值。

### Decision 6: 提案 status 只能是 `pending`（v0 不做狀態轉換）

`proposals/README.md` §4 模板的 frontmatter 有 `status: pending | validating | approved | rejected | merged`。本 change 的 `proposal_writer` 寫出來**強制** `status: pending`，且**不**提供改 status 的 API。

理由：
- §16 驗證閘還沒實作，沒有路徑能合法把 status 推到 `validating+`
- 強制 `pending` 讓未來的 `proposal-state-machine` change 可以 grep `status: pending` 全部找出來補狀態欄位
- v0 的提案就是「LLM 寫好放著等驗證閘 + 人工 review」，stage 等於 `pending`

**替代方案（已否決）**：直接讓 LLM 寫任意 status — LLM hallucinate 變成 `approved` / `merged` 會繞過 §16 的安全約束（proposals/README.md §11 FAQ 明確說「LLM 只能寫 pending 狀態」）。

### Decision 7: review_id 命名 = `manual-<from>-to-<to>` (v0 only)

reviews/README.md §3 列了 4 種命名（`2026-04` / `2026-Q1` / `forced-2026-04` / `manual-2026-04-15-to-2026-04-22`）對應 4 種觸發。MVP 只支援人工觸發，所以 review_id 強制 `manual-<from>-to-<to>` ISO 格式。

未來 `phase5-scheduler` change 補月度 / 季度 / 強制觸發時，重用 `pipeline.run(period_kind, ...)` 同一個 entry，只差 `review_id` 與 `kind` 欄。

### Decision 8: `--force` 才能覆寫已存在的 `reviews/<period>/`

reviews/README.md §7 規定「review 內容**不可在事後修改**」。但 dev / debug 期需要重跑。對策：

- 預設：`reviews/<period>/` 已存在 → `typer.Exit(code=2)` + stderr `"review already exists, pass --force to overwrite"`
- `--force`：覆寫既有檔案，但**不**動 `_index.json` 既有 row（v0 不做去重 / merge；後續 change 處理）

`reviews/_index.json` append 之前先檢查同 `review_id` 是否已存在 — 已存在則 update in place（覆寫該筆 metric），不 append 新 row。

### Decision 9: 提案檔名衝突處理 — `-2 / -3` suffix

同一天可能產生多份提案 topic 不同（`vcp-volume-threshold` + `time-stop-extend-vcp`），檔名不衝突；但若同一 review 內 LLM 對同一 topic 出兩份 proposal（罕見但可能），filename 衝突 → 第二份自動加 `-2` 後綴（`2026-04-30-vcp-volume-threshold-2.md`）。

`proposal_writer` 會：
1. 構檔名 `<YYYY-MM-DD>-<topic>.md`
2. 若該檔已存在 → 試 `-2` `-3` ... 直到 `-99`
3. 若 `-99` 仍存在 → `RuntimeError("too many proposals with same topic on same date")`（極端情況；v0 fail-loud）

**替代方案（已否決）**：用 hash / UUID 後綴 — 檔名失去人類可讀性。

### Decision 10: LLM client 重用 `decider/node.py` 的 Anthropic 整合模式

`src/ohmystock/decider/node.py` 已有 `AnthropicPMConclusionNode` 模式：拿 `Settings.anthropic_api_key` + 同步 `anthropic.Anthropic.messages.create` + JSON parse + 寫 `llm_costs`。本 change 抄同一模式做 `AttributorNode` / `CriticNode` / `ProposerNode`，不引入新 client wrapper。

`src/ohmystock/review/llm_client.py` 提供統一 helper `call_llm(model, system, user, schema, review_id, expect_json=True)` 回傳 parsed pydantic + cost row 寫入。3 個 node 共用此 helper。

### Decision 11: 黃金檔測試策略

`tests/review/fixtures/sample_journal_2026-04.json` 放一份合成的 23 筆 entry + 8 筆 reject + 3 筆 expire 的 journal，加上對應 market_data fixture。`tests/review/test_pipeline_golden.py` 把 fake LLM mock 出固定 attribution / critique / proposer，跑全 pipeline 後**byte-compare** `metrics.json` + `data.json`。LLM 部分用 `fake://` model 走 `FakeLLMNode` 模式（同 decider 已有的）。

實際 LLM 跑出來的 `attribution.json` / `critique.md` / `proposer` 輸出**不**做 byte-compare（會漂），改檢查：
- `attribution.json` 的 `category` 欄位值是否屬於 6 類 Literal
- `critique.md` 是否包含 `metrics.json` JSON pointer 字串
- `proposer` 輸出是否每份都通過 `proposal_writer` 模板 schema 驗證

## Risks / Trade-offs

- **[Risk] LLM hallucinate evidence 不存在的事實（attributor 寫「外資連買 18 億」但實際只有 8 億）** → Mitigation: rubric §7 明訂「攻擊性檢查 — 每個批判 / 提案是否引用具體 metrics.json 路徑」；v0 在 `critic` 與 `proposer` 的 system prompt 強制要求引用 JSON pointer，但**不**在 v0 加自動驗證器（後續 `phase5-validation-gate` change 補）。v0 接受人工 review 提案時抓出明顯 hallucination。
- **[Risk] cheatsheet 全文 50K tokens 對 critic context 是壓力，且未來 cheatsheet 會增長** → Mitigation: 用 prompt caching 攤平單次 review 內 retry 成本；長期成長到 80K+ 才考慮切片。v0 在 `tests/review/test_critic_token_budget.py` 加一道斷言「critic input ≤ 80K tokens」，超過即 fail（提早警示）。
- **[Risk] `data_missing: true`（停牌 / 下市）的 trade 漏算 post-exit return，使 attributor 規則分類缺資料** → Mitigation: data_loader 對缺資料 trade 標 `data_missing: true`；attributor 對這類 trade 強制走 LLM fallback（不走規則），讓 LLM 自己判斷類別 + evidence 寫「資料缺漏，依 thesis 判斷」。
- **[Risk] 區間內 0 筆 trade（從沒進場）導致 aggregator 除零** → Mitigation: aggregator 對空 input 直接寫「all zero / NA」的 `metrics.json`，critic 看到 `total_trades=0` 跳過警示，proposer 直接 0 提案。整個 pipeline 不報錯但 `proposals_created.md` 寫「本期無提案」。
- **[Risk] 同一份 review 重跑覆寫掉人工修過的提案** → Mitigation: `proposals/<YYYY-MM-DD>-<topic>.md` 一旦寫出**永遠不覆寫** — 重跑時若檔已存在直接 skip 該提案 + 在 `proposals_created.md` 標 `[skipped: file exists]`。`reviews/<period>/` 內檔案受 `--force` 控制（Decision 8）。
- **[Risk] `_index.json` append 期間 crash 留半個 row** → Mitigation: 寫入用 `temp file + os.replace` atomic rename；append 之前先 read 既有 + 操作記憶體 list + 整檔重寫 + atomic replace。
- **[Trade-off] sequential pipeline 不能 resume 中段** → 每次 crash 要從 `data_loader` 整段重跑。代價：data_loader + market_data 那段最重（網路 I/O），重跑成本最高約 30 秒。可接受。`--resume-from <node>` 是後續 change 補。
- **[Trade-off] proposal status 只能是 `pending`，使 v0 提案在沒有後續 change 之前**永遠不會被合併** — 這是刻意的，v0 的價值在「打通 raw journal → 提案」這條路；自動驗證 + 人工合併是後續 change 的範圍。
- **[Trade-off] LLM cost 寫到既有 `llm_costs` 表共用，無 review 專用 cost view** — 月底想看「Phase 5 跑了多少錢」要 SQL `WHERE decision_id LIKE 'manual-%'`；可接受，不需新表。
