## ADDED Requirements

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
- `decision_status: "pending_confirm"`（字面值，固定）
- `final_sizing_pct: float`（暫等於 `proposed_sizing_pct`，下一個 change 才會被 Sizing Service 改寫）
- `stop_loss_price: float | null`（本 change 一律 null，待 ATR Service 計算）
- `atr_at_entry: float | null`（同前）
- `risk_regime_at_entry: "risk_on" | "risk_off" | null`（本 change 一律 null，待 Risk Gate 計算）
- `auto_executed: false`（本 change 階段固定）
- `human_confirmed_by: null`（本 change 階段固定，Confirm Gate 改寫）
- `human_confirmed_at: null`（同前）

#### Scenario: enter payload 含全部 LLM 欄位
- **GIVEN** 一個 in-memory SQLite，跑 `init_schema(conn)` 後執行一次成功的 `decide_entry(...)` 走 enter 路徑
- **WHEN** 執行 `SELECT payload_json FROM journal_entries WHERE kind='entry' LIMIT 1`，並 `json.loads` 結果
- **THEN** dict SHALL 含 keys：`llm_model`、`llm_confidence`、`llm_reasoning`、`cited_skills`、`must_have_check`、`bonus_score`、`proposed_sizing_pct`、`expected_holding_days`、`stage`、`rs_percentile`、`trend_template_passed`、`vcp_quality`、`pivot_price`、`llm_input_tokens`、`llm_output_tokens`、`llm_cost_usd`、`entry_thesis`、`thesis_invalidation`

#### Scenario: pending_confirm 階段 stop_loss / atr / risk_regime 為 null
- **GIVEN** 同前 GIVEN
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.decision_status'), json_extract(payload_json, '$.stop_loss_price'), json_extract(payload_json, '$.atr_at_entry'), json_extract(payload_json, '$.risk_regime_at_entry') FROM journal_entries WHERE kind='entry'`
- **THEN** 結果為 `('pending_confirm', None, None, None)`

#### Scenario: auto_executed false / human_confirmed_by null
- **GIVEN** 同前 GIVEN
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.auto_executed'), json_extract(payload_json, '$.human_confirmed_by') FROM journal_entries WHERE kind='entry'`
- **THEN** 結果為 `(0, None)`（SQLite 將 boolean false 存為 0）

#### Scenario: entry_thesis 可被 FTS5 命中
- **GIVEN** `decide_entry(...)` 寫入一筆 `entry_thesis="VCP breakout 杯柄突破量能 1.74×"` 的 entry
- **WHEN** 執行 `SELECT rowid FROM journal_entries_fts WHERE journal_entries_fts MATCH '杯柄突破'`
- **THEN** 至少回傳一筆，rowid 對應該 entry

---

### Requirement: `kind=reject` payload — `reject_layer="llm"` 形狀

當 `entry-decider` capability 在 `decide_entry(...)` 寫入 `kind=reject` 且原因來自 LLM 路徑（含 LLM 自願 reject 與系統 §2.1 force_reject 與 JSON parse error）時，`payload_json` SHALL 含以下欄位（對齊 `docs/llm-decision-schema.md` §4.3）：

- `decision_status: "rejected"`（字面值，固定）
- `reject_layer: "llm"`（字面值，固定）
- `reject_reason: str`（非空；§2.1 reject 原因碼或 `json_parse_error: <截斷>`）
- `llm_model: str`（若 LLM 有回則填，parse error 時取 decider 設定的 model 名稱）
- `llm_confidence: float | null`（parse error 時為 null）
- `llm_input_tokens: int | null`、`llm_output_tokens: int | null`、`llm_cost_usd: float | null`（parse error 時若 usage 不可取得，可全為 null 或 0）
- 若是系統 force_reject：SHALL 額外含 `applied_overrides: list[str]`（從 `ValidationResult.applied_overrides` 拷貝）

#### Scenario: LLM 自願 reject (confidence < 0.6) 寫 reject_layer=llm
- **GIVEN** decide_entry 走 LLM 自願 reject 路徑（confidence=0.45）
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.reject_layer'), json_extract(payload_json, '$.reject_reason'), json_extract(payload_json, '$.decision_status') FROM journal_entries WHERE kind='reject'`
- **THEN** 結果為 `('llm', 'confidence_below_0_6', 'rejected')`

#### Scenario: 系統 force_reject (stage=4) 寫 reject_layer=llm + applied_overrides
- **GIVEN** decide_entry 走 force_reject 路徑（stage=4）
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.reject_reason'), json_extract(payload_json, '$.applied_overrides') FROM journal_entries WHERE kind='reject'`
- **THEN** 第一個值為 `'stage_4_excluded'`；第二個值為合法 JSON array 字串，包含 `'force_rejected:stage_4_excluded'`

#### Scenario: JSON parse error 寫 reject_reason 開頭為 json_parse_error
- **GIVEN** decide_entry 觸發 `DeciderOutputParseError`
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.reject_reason'), json_extract(payload_json, '$.reject_layer') FROM journal_entries WHERE kind='reject'`
- **THEN** 第一個值字串開頭為 `'json_parse_error:'`，第二個值為 `'llm'`

#### Scenario: parse error 時 llm_cost 欄位允許 null 或 0
- **GIVEN** decide_entry 觸發 parse error 且 usage 不可取得
- **WHEN** 執行 `SELECT json_extract(payload_json, '$.llm_input_tokens'), json_extract(payload_json, '$.llm_cost_usd') FROM journal_entries WHERE kind='reject'`
- **THEN** 兩個值皆為 `None` 或皆為 `0`（接受任一 sentinel）
