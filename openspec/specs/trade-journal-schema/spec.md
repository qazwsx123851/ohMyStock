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
