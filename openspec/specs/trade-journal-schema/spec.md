# trade-journal-schema Specification

## Purpose

定義 Trade Journal 在 SQLite 上的表 / 索引 / FTS5 / trigger schema，並以 `init_schema(conn)` 函式作為 idempotent migration 的唯一入口。本 capability 對齊 `docs/llm-decision-schema.md` §4 的 Trade Journal schema SSOT — 主表 `journal_entries` 紀錄 entry / exit / reject 三種事件，搭配 FTS5 全文索引（以 trigger 自動同步），以及 `llm_costs` 表記錄 LLM API 花費。本 capability 為 Phase 5 月度復盤五節點 swarm 的資料源。
## Requirements
### Requirement: 提供 init_schema(conn) idempotent migration

系統 SHALL 提供 `ohmystock.journal.schema.init_schema(conn: sqlite3.Connection) -> None` 函式，建立 Trade Journal 所有需要的表與索引。函式 SHALL idempotent — 在已建好的 DB 上重複呼叫 SHALL **不**拋例外、**不**改變既有資料。所有 DDL SHALL 使用 `IF NOT EXISTS` 子句。函式 SHALL 在同一個連線中以單一 transaction commit。

#### Scenario: 空 DB 上呼叫建出全部表
- **WHEN** 在空 SQLite DB（已啟用 FTS5）上執行 `init_schema(conn)`
- **THEN** `sqlite_master` 中 SHALL 出現 `journal_entries`、`journal_entries_fts`、`llm_costs` 三個 table 名稱

#### Scenario: 重複呼叫不拋例外
- **WHEN** 在已執行過 `init_schema(conn)` 的 DB 上再次呼叫 `init_schema(conn)`
- **THEN** 不拋例外；表結構與資料不變

#### Scenario: SQLite 缺 FTS5 時拋清楚錯誤
- **WHEN** 在不支援 FTS5 的 SQLite build 上執行 `init_schema(conn)`
- **THEN** 拋出 `RuntimeError`，message 包含 `"FTS5"` 字串

---

### Requirement: journal_entries 主表 schema

系統 SHALL 在 `init_schema()` 中建立 `journal_entries` 表，欄位至少包含：`id INTEGER PRIMARY KEY AUTOINCREMENT`、`decision_id TEXT NOT NULL`、`kind TEXT NOT NULL CHECK(kind IN ('entry','exit','reject','expire'))`、`symbol TEXT NOT NULL`、`created_at TEXT NOT NULL`（ISO-8601 字串含 `+08:00` 時區偏移）、`payload_json TEXT NOT NULL`（JSON 字串，存依 `kind` 變動的欄位如 `entry_price / atr_at_entry / sepa_*` 等）。`decision_id` SHALL 建 INDEX；`(kind, created_at)` SHALL 建複合 INDEX 以加速 Phase 5 復盤的時間範圍查詢。

#### Scenario: 主表欄位齊全
- **WHEN** 執行 `init_schema()` 後查詢 `PRAGMA table_info(journal_entries)`
- **THEN** 結果 SHALL 包含 `id`、`decision_id`、`kind`、`symbol`、`created_at`、`payload_json` 六個欄位名稱

#### Scenario: kind CHECK 阻擋非法值
- **WHEN** 嘗試 `INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) VALUES ('dec_x', 'partial_fill', '2330', '2026-04-29T11:00:00+08:00', '{}')`
- **THEN** SQLite 拋出 `IntegrityError`（CHECK constraint failed）

#### Scenario: expire kind is accepted
- **WHEN** 嘗試 `INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) VALUES ('dec_expired', 'expire', '2330', '2026-04-29T11:00:00+08:00', '{"expire_reason":"confirm timeout"}')`
- **THEN** INSERT 成功

#### Scenario: 索引存在
- **WHEN** 執行 `init_schema()` 後查詢 `sqlite_master` 中 type='index' 的列
- **THEN** 結果包含 `decision_id` 與 `(kind, created_at)` 對應的索引名（任意命名規則）

---

### Requirement: journal_entries_fts FTS5 索引以 trigger 同步

系統 SHALL 在 `init_schema()` 中建立 `journal_entries_fts` 為 FTS5 virtual table，採用「外部 content」模式（`content='journal_entries'`、`content_rowid='id'`），索引欄位為從 `payload_json` 抽出的 `entry_thesis`、`llm_reasoning`、`exit_reason` 三欄。系統 SHALL 同時建立 `journal_entries_ai`（AFTER INSERT）、`journal_entries_au`（AFTER UPDATE）、`journal_entries_ad`（AFTER DELETE）三個 trigger，使主表變動時 FTS5 索引自動同步。

#### Scenario: FTS5 表存在且為 fts5 模組
- **WHEN** 執行 `init_schema()` 後查詢 `sqlite_master` 中 `name='journal_entries_fts'` 的 row
- **THEN** 該 row 的 `sql` 欄位 SHALL 包含 `fts5` 字串

#### Scenario: 三個 trigger 存在
- **WHEN** 執行 `init_schema()` 後查詢 `sqlite_master WHERE type='trigger'`
- **THEN** 結果至少包含 `journal_entries_ai`、`journal_entries_au`、`journal_entries_ad` 三個 trigger 名稱

#### Scenario: MATCH 查詢可命中 entry_thesis
- **WHEN** 執行 `init_schema()` 後 INSERT 一筆 `payload_json = '{"entry_thesis": "VCP breakout with strong volume"}'`，再執行 `SELECT rowid FROM journal_entries_fts WHERE journal_entries_fts MATCH 'breakout'`
- **THEN** 結果 SHALL 至少回傳一筆，rowid 為剛才 INSERT 的 row

---

### Requirement: llm_costs 表 schema

系統 SHALL 在 `init_schema()` 中建立 `llm_costs` 表，欄位至少包含：`id INTEGER PRIMARY KEY AUTOINCREMENT`、`decision_id TEXT`（可為 NULL，因為非所有 LLM 呼叫都綁特定決策）、`model TEXT NOT NULL`、`input_tokens INTEGER NOT NULL`、`output_tokens INTEGER NOT NULL`、`cost_usd REAL NOT NULL`、`created_at TEXT NOT NULL`。`created_at` SHALL 建 INDEX 以加速月度聚合查詢。

#### Scenario: llm_costs 欄位齊全
- **WHEN** 執行 `init_schema()` 後查詢 `PRAGMA table_info(llm_costs)`
- **THEN** 結果 SHALL 包含 `id`、`decision_id`、`model`、`input_tokens`、`output_tokens`、`cost_usd`、`created_at` 七個欄位名稱

#### Scenario: created_at 索引存在
- **WHEN** 執行 `init_schema()` 後查詢 `sqlite_master` 中 type='index'、tbl_name='llm_costs' 的列
- **THEN** 結果至少含一個索引涵蓋 `created_at` 欄位

---

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

