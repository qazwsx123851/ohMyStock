## MODIFIED Requirements

### Requirement: `kind=entry` payload — pending_confirm 階段欄位形狀

當 `entry-decider` capability 在 `decide_entry(...)` 寫入 `kind=entry` 時，`payload_json` SHALL 含以下欄位（對齊 `docs/llm-decision-schema.md` §4.1，但因 Sizing/ATR/Risk Gate 尚未實作，部分欄位允許為 null）：

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

**系統決策欄位（pending_confirm 階段允許部分為 null）**
- `decision_status: "pending_confirm" | "confirmed" | "rejected" | "expired"`（lifecycle enum，由 confirm-gate 翻轉；初始寫入時固定 `"pending_confirm"`）
- `final_sizing_pct: float`（暫等於 `proposed_sizing_pct`，下一個 change 才會被 Sizing Service 改寫）
- `current_price: float`（從 `EntryDecisionInput.candidate.current_price` 快照而來；Confirm Gate 使用此值作為 `reference_price` 傳給 paper broker）
- `stop_loss_price: float | null`（本 change 一律 null，待 ATR Service 計算）
- `atr_at_entry: float | null`（同前）
- `risk_regime_at_entry: "risk_on" | "risk_off" | null`（本 change 一律 null，待 Risk Gate 計算）
- `auto_executed: false`（本 change 階段固定）
- `human_confirmed_by: str | null`（pending_confirm 階段為 null；confirm-gate `confirm()` 寫入呼叫者的 `user`）
- `human_confirmed_at: str | null`（pending_confirm 階段為 null；confirm-gate `confirm()` 寫入 ISO-8601 含 `+08:00` 時間戳）
- `actual_entry_price: float | null`（pending_confirm 階段為 null；confirm-gate `confirm()` 寫入 `Fill.fill_price`）
- `actual_qty: int | null`（pending_confirm 階段為 null；confirm-gate `confirm()` 寫入 `Fill.filled_qty`，必為 1000 的倍數）

**Lifecycle 轉換規則：**
- `pending_confirm → confirmed`：confirm-gate `confirm()` UPDATE 同一 row，set 上述四個 confirm 欄位 + `decision_status="confirmed"`。
- `pending_confirm → rejected`：confirm-gate `reject()` UPDATE 同一 row，set `decision_status="rejected"`，confirm 欄位仍為 null（rejected 不 fill）。
- `pending_confirm → expired`：confirm-gate `sweep_expired()` UPDATE 同一 row，set `decision_status="expired"`，confirm 欄位仍為 null。
- `confirmed`/`rejected`/`expired` 為終態，禁止再轉換（confirm-gate 函式以 `not_pending` error 阻擋）。

#### Scenario: enter payload 含全部 LLM 欄位
- **GIVEN** 一個 in-memory SQLite，跑 `init_schema(conn)` 後執行一次成功的 `decide_entry(...)` 走 enter 路徑
- **WHEN** 執行 `SELECT payload_json FROM journal_entries WHERE kind='entry' LIMIT 1`，並 `json.loads` 結果
- **THEN** dict SHALL 含 keys：`llm_model`、`llm_confidence`、`llm_reasoning`、`cited_skills`、`must_have_check`、`bonus_score`、`proposed_sizing_pct`、`expected_holding_days`、`stage`、`rs_percentile`、`trend_template_passed`、`vcp_quality`、`pivot_price`、`llm_input_tokens`、`llm_output_tokens`、`llm_cost_usd`、`entry_thesis`、`thesis_invalidation`、`current_price`

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

#### Scenario: confirm 後 lifecycle 欄位被填入
- **GIVEN** 一筆 pending_confirm entry 經 `confirm-gate.confirm(...)` 處理成功（user="mark@local"，clock 回 "2026-05-02T10:15:00+08:00"，FakePaperBroker 在 reference_price=832.0 上 fill 1000 股）
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.decision_status'), json_extract(payload_json, '$.actual_entry_price'), json_extract(payload_json, '$.actual_qty'), json_extract(payload_json, '$.human_confirmed_by'), json_extract(payload_json, '$.human_confirmed_at') FROM journal_entries WHERE kind='entry'`
- **THEN** 結果為 `('confirmed', 832.0, 1000, 'mark@local', '2026-05-02T10:15:00+08:00')`

#### Scenario: reject 後 lifecycle status 翻為 rejected 但 confirm 欄位仍 null
- **GIVEN** 一筆 pending_confirm entry 經 `confirm-gate.reject(...)` 處理成功
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.decision_status'), json_extract(payload_json, '$.actual_entry_price'), json_extract(payload_json, '$.human_confirmed_by') FROM journal_entries WHERE kind='entry'`
- **THEN** 結果為 `('rejected', None, None)`

#### Scenario: expire 後 lifecycle status 翻為 expired
- **GIVEN** 一筆 pending_confirm entry 經 `confirm-gate.sweep_expired(...)` 處理成功
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.decision_status') FROM journal_entries WHERE kind='entry'`
- **THEN** 結果為 `'expired'`

---

## ADDED Requirements

### Requirement: `kind=reject` payload — `reject_layer="human"` 形狀

當 `confirm-gate` capability 在 `reject(...)` 寫入 `kind=reject` 且原因來自人工拒絕路徑時，`payload_json` SHALL 含以下欄位（對齊 `docs/llm-decision-schema.md` §4.3 的 `reject_layer="human"` 取值）：

- `decision_status: "rejected"`（字面值，固定）
- `reject_layer: "human"`（字面值，固定）
- `reject_reason: str`（非空字串；CLI `--reason` 旗標填入或預設 `"human rejected via confirm gate"`）
- `rejected_by: str`（呼叫者傳入的 `user`，例如 `"mark@local"`）
- `rejected_at: str`（ISO-8601 含 `+08:00`，等於 row 的 `created_at`）

人工 reject 路徑 **不** 含 LLM cost 欄位（`llm_input_tokens` / `llm_output_tokens` / `llm_cost_usd`）— 該決策的 LLM 成本已在原始 `kind=entry` row 中記錄，且 `llm_costs` 表已有對應 row（由 `decide_entry` 寫入）。重複寫會導致月度成本聚合 double-count。

#### Scenario: 人工 reject 寫 reject_layer=human + rejected_by/at
- **GIVEN** 一筆 pending entry，`confirm-gate.reject(conn, decision_id="dec_X", reason="盤勢不對", user="mark@local", clock=FakeClock("2026-05-02T10:20:00+08:00"))`
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.reject_layer'), json_extract(payload_json, '$.reject_reason'), json_extract(payload_json, '$.rejected_by'), json_extract(payload_json, '$.rejected_at'), json_extract(payload_json, '$.decision_status') FROM journal_entries WHERE decision_id='dec_X' AND kind='reject'`
- **THEN** 結果為 `('human', '盤勢不對', 'mark@local', '2026-05-02T10:20:00+08:00', 'rejected')`

#### Scenario: 人工 reject 不含 LLM cost 欄位
- **GIVEN** 同前 GIVEN
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.llm_input_tokens'), json_extract(payload_json, '$.llm_cost_usd') FROM journal_entries WHERE kind='reject' AND json_extract(payload_json, '$.reject_layer')='human'`
- **THEN** 兩個值皆為 `None`（`json_extract` 對缺鍵回 NULL）

#### Scenario: 同一 decision_id 可同時有 LLM reject 與 human reject
- **GIVEN** 一個 decision_id 先因為 LLM `decide_entry` parse error 寫了 `reject_layer="llm"`（這在實務上不會發生，因為 LLM reject 後沒有 pending entry 可被 human reject；但 schema 不阻擋）
- **WHEN** 查 `SELECT COUNT(*) FROM journal_entries WHERE decision_id=? AND kind='reject'`
- **THEN** schema CHECK 不阻擋 — 計入兩筆（schema 對同 decision_id 多筆 reject row 不設唯一性限制）

---

### Requirement: `kind=expire` payload — Confirm Gate timeout 形狀

當 `confirm-gate` capability 在 `sweep_expired(...)` 寫入 `kind=expire` 時，`payload_json` SHALL 含以下欄位（對齊 `docs/llm-decision-schema.md` §4.4）：

- `decision_status: "expired"`（字面值，固定）
- `expire_reason: str`（非空字串，預設 `"confirm timeout after <N> minutes"`，N 為 `timeout_minutes`）
- `expired_at: str`（ISO-8601 含 `+08:00`，等於 row 的 `created_at`）

`kind=expire` row 不含任何 LLM 欄位（同 human reject 的理由：成本已在原始 entry row + `llm_costs` 表中）。一個 `decision_id` 至多對應一筆 `kind=expire`（由 sweep 邏輯保證：sweep 只挑 `decision_status="pending_confirm"` 的 row，UPDATE 後就不再被選中）。

#### Scenario: expire payload 形狀
- **GIVEN** sweep_expired 處理一筆過期 entry，`timeout_minutes=30`，`clock.now()=="2026-05-02T10:35:00+08:00"`
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.decision_status'), json_extract(payload_json, '$.expire_reason'), json_extract(payload_json, '$.expired_at') FROM journal_entries WHERE kind='expire'`
- **THEN** 結果為 `('expired', 'confirm timeout after 30 minutes', '2026-05-02T10:35:00+08:00')`

#### Scenario: expire row 不含 LLM cost 欄位
- **GIVEN** 同前 GIVEN
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.llm_cost_usd'), json_extract(payload_json, '$.llm_input_tokens') FROM journal_entries WHERE kind='expire'`
- **THEN** 兩個值皆為 `None`

#### Scenario: 同一 decision_id 至多一筆 expire row
- **GIVEN** 同一筆 pending entry，連跑兩次 `sweep_expired(...)`（第二次是 no-op，因為第一次已將 entry 翻成 expired）
- **WHEN** 執行 `SELECT COUNT(*) FROM journal_entries WHERE decision_id=? AND kind='expire'`
- **THEN** 結果為 `1`
