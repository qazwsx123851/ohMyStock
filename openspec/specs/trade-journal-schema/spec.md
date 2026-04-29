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

系統 SHALL 在 `init_schema()` 中建立 `journal_entries` 表，欄位至少包含：`id INTEGER PRIMARY KEY AUTOINCREMENT`、`decision_id TEXT NOT NULL`、`kind TEXT NOT NULL CHECK(kind IN ('entry','exit','reject'))`、`symbol TEXT NOT NULL`、`created_at TEXT NOT NULL`（ISO-8601 字串含 `+08:00` 時區偏移）、`payload_json TEXT NOT NULL`（JSON 字串，存依 `kind` 變動的欄位如 `entry_price / atr_at_entry / sepa_*` 等）。`decision_id` SHALL 建 INDEX；`(kind, created_at)` SHALL 建複合 INDEX 以加速 Phase 5 復盤的時間範圍查詢。

#### Scenario: 主表欄位齊全
- **WHEN** 執行 `init_schema()` 後查詢 `PRAGMA table_info(journal_entries)`
- **THEN** 結果 SHALL 包含 `id`、`decision_id`、`kind`、`symbol`、`created_at`、`payload_json` 六個欄位名稱

#### Scenario: kind CHECK 阻擋非法值
- **WHEN** 嘗試 `INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) VALUES ('dec_x', 'partial_fill', '2330', '2026-04-29T11:00:00+08:00', '{}')`
- **THEN** SQLite 拋出 `IntegrityError`（CHECK constraint failed）

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
