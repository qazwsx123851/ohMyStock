## Why

Phase 2B 已能組裝 `EntryInput`（候選 + 市場狀態 + 規則摘要 + 工具/技能清單），但目前沒有任何模組會把它送進 LLM。Phase 3 的最小可運作切片是「PM 結論節點 + 系統驗證」：把 EntryInput 餵給 Claude Opus 4.7 → 拿到 v3.1 結構化 JSON → 用 `docs/llm-decision-schema.md` §2.1 的硬約束驗證 → 落 journal（`kind=entry` pending_confirm 或 `kind=reject` reject_layer=llm）+ `llm_costs`。先把這條最短路徑跑通，後續才能在上面疊 Sizing/ATR/Risk Gate（Phase 3 中段）和 Confirm Gate（Phase 3.5）。

## What Changes

- 新增 `ohmystock.decider` 模組：`PMConclusionNode` 介面 + 預設 Anthropic SDK 實作；可注入 fake decider 做測試。
- 新增 `DeciderOutput` Pydantic 模型，對應 `docs/llm-decision-schema.md` §2 v3.1 schema（含 5 個 SEPA 欄位）。
- 新增 `validate_decider_output(output, candidate)` 系統覆寫驗證器，實作 §2.1 全部硬約束：
  - `decision ∈ {enter, reject, reduce_size}`
  - `confidence < 0.6` → 強制 `reject`
  - `must_have_check` 必須 3 項且 name 為 v3.1 三柱（`trend_template_8_of_8` / `stage_2_confirmed` / `vcp_pivot_breakout_with_volume`）；任一 `pass=false` → 強制 `reject`
  - `bonus_score < 4` → 強制 `reject`
  - `proposed_sizing_pct ∉ [0, 25]` → reject
  - `reasoning` < 200 字 → reject
  - `cited_skills` 空陣列 → reject
  - `expected_holding_days ∉ [1, 30]` → reject
  - `stage == 4` → 強制 `reject`；`stage == 3` 時 `proposed_sizing_pct` 強制 cap 至 10%
  - `rs_percentile < 65` → must_have `trend_template_8_of_8` 自動 fail
  - `trend_template_passed < 8` → 同上自動 fail
  - `vcp_quality ∈ {none, forming}` → must_have `vcp_pivot_breakout_with_volume` 自動 fail
  - `pivot_price` 不變式：`vcp_quality ∈ {textbook, breakout}` ↔ `pivot_price > 0`，否則 `null`
- 新增 `decide_entry(entry_input)` 編排函式：
  1. 呼叫 `PMConclusionNode.decide(entry_input)` 取得 `(raw_output, usage)`，
  2. 跑 `validate_decider_output` 得到「LLM 原始 + 系統覆寫後」雙份結果，
  3. 寫一筆 `kind=entry`（`decision_status=pending_confirm`）或 `kind=reject`（`reject_layer=llm`）到 journal，
  4. 寫一筆 `llm_costs`（含 `decision_id`、model、input/output tokens、cost_usd）。
- 新增 CLI 命令 `ohmystock decide <symbol>`：用既有 live providers 組裝 EntryInput，呼叫 `decide_entry`，把 LLM 輸出 + 系統覆寫結果印到 stdout，並回傳 exit code（0 = entry pending_confirm；1 = LLM/系統 reject；其他 = error）。
- 新增 `OHMYSTOCK_DECIDER_MODEL` env var（預設 `claude-opus-4-7`），允許單元測試覆寫為 `fake://`。

**不在本次範圍**：
- entry_decision_team 多代理 swarm 的 specialist 節點（technical / chip / fundamental / sentiment 各自呼叫工具）— 留給後續 change。
- Confirm Gate（人工確認 / `OHMYSTOCK_AUTO_EXECUTE` 雙模式）— Phase 3.5。
- Sizing Service（Volatility Targeting）/ ATR Service / Risk Gate 的最終覆寫 — 其下一個 change。
- `kind=exit` / `kind=expire` 寫入 — Phase 4。

## Capabilities

### New Capabilities

- `entry-decider`: Phase 3 LLM PM 結論節點與 §2.1 系統覆寫驗證器 — 把 `EntryInput` 轉換成 `DeciderOutput` 並落 journal + llm_costs。

### Modified Capabilities

- `cli-and-config`: 新增 `ohmystock decide <symbol>` 命令；新增 `OHMYSTOCK_DECIDER_MODEL` 設定鍵。
- `trade-journal-schema`: 不改 DDL，但新增「`kind=entry` 在 `decision_status=pending_confirm` 階段寫入」的允許情境；以及 `kind=reject` 中 `reject_layer=llm` 的 payload 形狀（追加要求，向後相容）。

## Impact

- **新模組**：`src/ohmystock/decider/{__init__.py, node.py, validator.py, models.py, orchestrator.py}`。
- **新測試**：`tests/test_decider_validator.py` / `tests/test_decider_orchestrator.py` / `tests/test_cli_decide.py`。
- **改動**：
  - `src/ohmystock/cli/__init__.py` 新增 `decide` subcommand。
  - `src/ohmystock/config.py` 新增 `decider_model` 欄位。
  - `src/ohmystock/observability/cost_tracker.py` 可能補一個 `record_llm_cost(conn, decision_id, model, input_tokens, output_tokens, cost_usd)` helper（若尚未存在）。
- **依賴**：使用既有 `anthropic` SDK（cost-tracking spec 已引入）；不引入 LangChain / claude-agent-sdk 多代理 runtime（PM 單節點不需要）。
- **環境變數**：新增 `OHMYSTOCK_DECIDER_MODEL`（預設 `claude-opus-4-7`）；既有 `ANTHROPIC_API_KEY` 必須存在，否則 `decide_entry` raise `RuntimeError`。
- **DB**：使用既有 `journal_entries` / `llm_costs` 表，不需要 migration。
