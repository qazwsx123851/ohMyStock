## MODIFIED Requirements

### Requirement: `kind=entry` payload — pending_confirm 階段欄位形狀

當 `entry-decider` capability 在 `decide_entry(...)` 寫入 `kind=entry` 時，`payload_json` SHALL 含以下欄位（對齊 `docs/llm-decision-schema.md` §4.1）：

**LLM 來源欄位（全部必填，從 `DeciderOutput` 拷貝）**
- `llm_decision_id: str`
- `llm_model: str`
- `llm_confidence: float`
- `llm_reasoning: str`
- `cited_skills: list[str]`（非空）
- `must_have_check: list`（3 項）
- `bonus_score: int`、`bonus_breakdown: list`
- `proposed_sizing_pct: float`、`expected_holding_days: int`
- `risk_flags: list[str]`、`thesis_invalidation: list[str]`
- `entry_thesis: str`（取 `reasoning` 前 500 字當摘要，可被 FTS5 索引）
- `llm_input_tokens: int`、`llm_output_tokens: int`、`llm_cost_usd: float`
- **SEPA 五欄**：`stage` / `rs_percentile` / `trend_template_passed` / `vcp_quality` / `pivot_price`

**系統決策欄位（部分欄位的 nullability 依 lifecycle 階段而定）**
- `decision_status: "pending_confirm" | "confirmed" | "rejected" | "expired" | "closed"`（lifecycle enum，由 confirm-gate / exit-engine 翻轉；初始寫入時固定 `"pending_confirm"`）
- `final_sizing_pct: float`（暫等於 `proposed_sizing_pct`，後續 change 由 Sizing Service 改寫）
- `current_price: float`（從 `EntryDecisionInput.candidate.current_price` 快照而來；Confirm Gate 使用此值作為 `reference_price` 傳給 paper broker）
- `atr_14_pct: float`（從 `EntryDecisionInput.candidate.atr_14_pct` 快照而來；Confirm Gate 用此值乘 `actual_entry_price / 100` 算出 `atr_at_entry`）
- `risk_regime_at_entry: "risk_on" | "risk_off" | null`（本 change 一律 null，待 Risk Gate 計算）
- `auto_executed: false`（本 change 階段固定）
- `human_confirmed_by: str | null`（pending_confirm 階段為 null；confirm-gate `confirm()` 寫入呼叫者的 `user`）
- `human_confirmed_at: str | null`（pending_confirm 階段為 null；confirm-gate `confirm()` 寫入 ISO-8601 含 `+08:00` 時間戳）
- `actual_entry_price: float | null`（pending_confirm 階段為 null；confirm-gate `confirm()` 寫入 `Fill.fill_price`）
- `actual_qty: int | null`（pending_confirm 階段為 null；confirm-gate `confirm()` 寫入 `Fill.filled_qty`，必為 1000 的倍數）
- `atr_at_entry: float | null`（pending_confirm 階段為 null；**本 change 起**：confirm-gate `confirm()` 計算後寫入 `actual_entry_price * atr_14_pct / 100.0`）
- `stop_loss_price: float | null`（pending_confirm 階段為 null；**本 change 起**：confirm-gate `confirm()` 寫入 `max(actual_entry_price * 0.94, actual_entry_price - 2.0 * atr_at_entry)`，cheatsheet §6.6 normal-market case）

**Lifecycle 轉換規則：**
- `pending_confirm → confirmed`：confirm-gate `confirm()` UPDATE 同一 row，set `actual_entry_price` / `actual_qty` / `human_confirmed_by` / `human_confirmed_at` / `atr_at_entry` / `stop_loss_price` + `decision_status="confirmed"`。
- `pending_confirm → rejected`：confirm-gate `reject()` UPDATE 同一 row，set `decision_status="rejected"`，confirm 欄位仍為 null。
- `pending_confirm → expired`：confirm-gate `sweep_expired()` UPDATE 同一 row，set `decision_status="expired"`，confirm 欄位仍為 null。
- `confirmed → closed`：exit-engine `evaluate_open_positions()` UPDATE 同一 row，set `decision_status="closed"`（confirm 欄位保留不動；新增一筆 `kind=exit` row 紀錄出場資訊）。
- `rejected` / `expired` / `closed` 為終態，禁止再轉換。

#### Scenario: enter payload 含全部 LLM 欄位
- **GIVEN** 一個 in-memory SQLite，跑 `init_schema(conn)` 後執行一次成功的 `decide_entry(...)` 走 enter 路徑
- **WHEN** 執行 `SELECT payload_json FROM journal_entries WHERE kind='entry' LIMIT 1`，並 `json.loads` 結果
- **THEN** dict SHALL 含 keys：`llm_model`、`llm_confidence`、`llm_reasoning`、`cited_skills`、`must_have_check`、`bonus_score`、`proposed_sizing_pct`、`expected_holding_days`、`stage`、`rs_percentile`、`trend_template_passed`、`vcp_quality`、`pivot_price`、`llm_input_tokens`、`llm_output_tokens`、`llm_cost_usd`、`entry_thesis`、`thesis_invalidation`、`current_price`、`atr_14_pct`

#### Scenario: pending_confirm 階段 stop_loss / atr / risk_regime / actual_* 為 null
- **GIVEN** 同前 GIVEN
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.decision_status'), json_extract(payload_json, '$.stop_loss_price'), json_extract(payload_json, '$.atr_at_entry'), json_extract(payload_json, '$.risk_regime_at_entry'), json_extract(payload_json, '$.actual_entry_price'), json_extract(payload_json, '$.actual_qty') FROM journal_entries WHERE kind='entry'`
- **THEN** 結果為 `('pending_confirm', None, None, None, None, None)`

#### Scenario: auto_executed false / human_confirmed_by null
- **GIVEN** 同前 GIVEN
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.auto_executed'), json_extract(payload_json, '$.human_confirmed_by'), json_extract(payload_json, '$.human_confirmed_at') FROM journal_entries WHERE kind='entry'`
- **THEN** 結果為 `(0, None, None)`（SQLite 將 boolean false 存為 0）

#### Scenario: entry_thesis 可被 FTS5 命中
- **GIVEN** `decide_entry(...)` 寫入一筆 `entry_thesis="VCP breakout 杯柄突破量能 1.74×"` 的 entry
- **WHEN** 執行 `SELECT rowid FROM journal_entries_fts WHERE journal_entries_fts MATCH '杯柄突破'`
- **THEN** 至少回傳一筆，rowid 對應該 entry

#### Scenario: confirm 後 lifecycle 欄位被填入（含 atr_at_entry / stop_loss_price）
- **GIVEN** 一筆 pending_confirm entry（`current_price=832.0`、`atr_14_pct=2.85`）經 `confirm-gate.confirm(...)` 處理成功
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.decision_status'), json_extract(payload_json, '$.actual_entry_price'), json_extract(payload_json, '$.actual_qty'), json_extract(payload_json, '$.atr_at_entry'), json_extract(payload_json, '$.stop_loss_price'), json_extract(payload_json, '$.human_confirmed_by'), json_extract(payload_json, '$.human_confirmed_at') FROM journal_entries WHERE kind='entry'`
- **THEN** 結果為 `('confirmed', 832.0, 1000, ≈23.712, ≈784.576, 'mark@local', '2026-05-02T10:15:00+08:00')`

#### Scenario: reject 後 lifecycle status 翻為 rejected 但 confirm 欄位仍 null
- **GIVEN** 一筆 pending_confirm entry 經 `confirm-gate.reject(...)` 處理成功
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.decision_status'), json_extract(payload_json, '$.actual_entry_price'), json_extract(payload_json, '$.human_confirmed_by') FROM journal_entries WHERE kind='entry'`
- **THEN** 結果為 `('rejected', None, None)`

#### Scenario: expire 後 lifecycle status 翻為 expired
- **GIVEN** 一筆 pending_confirm entry 經 `confirm-gate.sweep_expired(...)` 處理成功
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.decision_status') FROM journal_entries WHERE kind='entry'`
- **THEN** 結果為 `'expired'`

#### Scenario: closed 後 lifecycle status 翻為 closed 但 confirm 欄位保留
- **GIVEN** 一筆 confirmed entry 經 `exit-engine.evaluate_open_positions(...)` 處理為 hit_t1
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.decision_status'), json_extract(payload_json, '$.actual_entry_price'), json_extract(payload_json, '$.actual_qty') FROM journal_entries WHERE kind='entry'`
- **THEN** 結果為 `('closed', 832.0, 1000)`（confirm 欄位保留，僅 status 翻 closed）

---

## ADDED Requirements

### Requirement: `kind=exit` payload — exit-engine v0 三標籤形狀

當 `exit-engine` capability 在 `evaluate_open_positions(...)` 寫入 `kind=exit` 時，`payload_json` SHALL 含以下欄位（對齊 `docs/llm-decision-schema.md` §4.2 + cheatsheet §6.6 exit_tag 列表）：

- `exit_tag: "hit_stop_loss" | "hit_t1" | "time_stop"`（v0 三選一；其他 cheatsheet 列舉的標籤 `hit_t1_5` / `chandelier` / `thesis_invalid` / `discretionary` 為未來 change 預留，本 capability 不寫入）
- `exit_reason: str`（非空字串；engine 自動填如 `"close 780.0 ≤ stop_loss 784.58"` / `"close 900.0 ≥ T1 881.92"` / `"hold_days 20 ≥ 16"`）
- `actual_exit_price: float`（評估當下的收盤價，`close_price_evaluated`；v0 不模擬 slippage）
- `pnl_pct: float`（`(actual_exit_price - actual_entry_price) / actual_entry_price * 100`，正負皆可）
- `hold_days: int`（從 `human_confirmed_at` 日期到 `asof_date` 的天數差，≥ 0）
- `exited_at: str`（ISO-8601 含 `+08:00`，等於 row 的 `created_at`）
- `close_price_evaluated: float`（與 `actual_exit_price` 相等；保留為獨立欄位以便未來 change 引入 slippage 時 `actual_exit_price ≠ close_price_evaluated`）

`kind=exit` row 不含任何 LLM 欄位（同 `kind=expire` 與 human reject 的理由：成本已在原始 entry row + `llm_costs` 表中）。一個 `decision_id` 至多對應一筆 `kind=exit`（由 evaluator 邏輯保證：只挑 `decision_status="confirmed"` 的 entry，UPDATE 後就不再被選中）。

#### Scenario: hit_t1 exit payload 形狀
- **GIVEN** evaluate_open_positions 處理一筆 confirmed entry（`actual_entry_price=832.0`、`stop_loss_price=784.58`、`expected_holding_days=8`、`human_confirmed_at="2026-05-02T10:15:00+08:00"`），`market_data.get_close("2330", date(2026,5,7)) == 900.0`，clock 回 `"2026-05-07T13:30:00+08:00"`
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.exit_tag'), json_extract(payload_json, '$.actual_exit_price'), json_extract(payload_json, '$.pnl_pct'), json_extract(payload_json, '$.hold_days'), json_extract(payload_json, '$.exited_at'), json_extract(payload_json, '$.close_price_evaluated') FROM journal_entries WHERE kind='exit'`
- **THEN** 結果為 `('hit_t1', 900.0, ≈8.17, 5, '2026-05-07T13:30:00+08:00', 900.0)`

#### Scenario: hit_stop_loss exit payload 形狀
- **GIVEN** 同 entry，`market_data.get_close == 780.0`，asof=date(2026,5,5)，clock 回 `"2026-05-05T13:30:00+08:00"`
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.exit_tag'), json_extract(payload_json, '$.actual_exit_price'), json_extract(payload_json, '$.pnl_pct'), json_extract(payload_json, '$.hold_days') FROM journal_entries WHERE kind='exit'`
- **THEN** 結果為 `('hit_stop_loss', 780.0, ≈-6.25, 3)`

#### Scenario: time_stop exit payload 形狀
- **GIVEN** 同 entry，`market_data.get_close == 850.0`（未觸 stop 也未觸 T1），asof=date(2026,5,22)（hold_days=20 ≥ 16），clock 回 `"2026-05-22T13:30:00+08:00"`
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.exit_tag'), json_extract(payload_json, '$.hold_days'), json_extract(payload_json, '$.actual_exit_price') FROM journal_entries WHERE kind='exit'`
- **THEN** 結果為 `('time_stop', 20, 850.0)`

#### Scenario: exit row 不含 LLM cost 欄位
- **GIVEN** 同前 hit_t1 GIVEN
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.llm_cost_usd'), json_extract(payload_json, '$.llm_input_tokens') FROM journal_entries WHERE kind='exit'`
- **THEN** 兩個值皆為 `None`

#### Scenario: 同一 decision_id 至多一筆 kind=exit row
- **GIVEN** 一筆 confirmed entry，連跑兩次 `evaluate_open_positions(...)`（第一次 hit_t1，第二次因 entry 已 closed 跳過）
- **WHEN** 執行 `SELECT COUNT(*) FROM journal_entries WHERE decision_id=? AND kind='exit'`
- **THEN** 結果為 `1`

#### Scenario: exit row 與 entry row 透過 decision_id 對應
- **GIVEN** evaluate 寫入 hit_t1 exit
- **WHEN** 執行 `SELECT entry.symbol, exit.symbol FROM journal_entries entry JOIN journal_entries exit ON entry.decision_id=exit.decision_id WHERE entry.kind='entry' AND exit.kind='exit'`
- **THEN** 兩個 symbol 相等
