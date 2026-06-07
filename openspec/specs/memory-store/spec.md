# memory-store Specification

## Purpose
TBD - created by archiving change web-admin-memory-page-and-store. Update Purpose after archive.
## Requirements
### Requirement: `MemoryRow` model 與 frozen 不變式

系統 SHALL 在 `src/ohmystock/memory/store.py` 定義 `MemoryRow`（pydantic `BaseModel`，`model_config = ConfigDict(frozen=True, extra="forbid")`），欄位恰為：

- `id: int` — auto-increment 主鍵
- `kind: MemoryKind` — 取自 `Literal["note", "lesson", "proposal", "review_summary"]`
- `content: str` — 原始全文（可含 Markdown，但本 capability 不解析）
- `tags: list[str]` — 已從 JSON 陣列字串解碼（可空 list `[]` 但 SHALL 存在）
- `source: str | None` — 來源標記（例如 `"phase5-review:dec_X"`、`"manual"`），可為 `None`
- `created_at: str` — ISO-8601 含 `+08:00` 時區偏移

`MemoryRow` SHALL NOT 暴露其他欄位（無 `updated_at`、無 `body_html`、無 `bm25_score`）。

#### Scenario: frozen 不變式
- **GIVEN** 一個合法 `MemoryRow(id=1, kind="note", content="x", tags=[], source=None, created_at="2026-05-09T10:00:00+08:00")`
- **WHEN** 嘗試 `r.kind = "lesson"`
- **THEN** SHALL 拋 pydantic ValidationError（frozen attempt）

#### Scenario: 不允許 unknown 欄位
- **WHEN** `MemoryRow(id=1, kind="note", content="x", tags=[], source=None, created_at="2026-05-09T10:00:00+08:00", extra="boom")` 被呼叫
- **THEN** SHALL 拋 ValidationError，message 提示 `extra` 不被允許

#### Scenario: kind 限定四值
- **WHEN** `MemoryRow(id=1, kind="random", content="x", tags=[], source=None, created_at="2026-05-09T10:00:00+08:00")` 被呼叫
- **THEN** SHALL 拋 ValidationError，message 提到允許的 kind 值

---

### Requirement: 公開 API（`__init__.py`）

`src/ohmystock/memory/__init__.py` SHALL 公開且僅公開以下名稱：`MemoryRow`、`MemoryKind`、`MemoryStore`、`MemoryStoreError`、`init_schema`。其他模組內部實作（私有 helper、SQL 字串常數等）SHALL NOT 出現在 `__init__.py` 的 `__all__` 或 re-export 列表內。

#### Scenario: 公開符號齊全
- **WHEN** `import ohmystock.memory as m`
- **THEN** `m.MemoryRow`、`m.MemoryKind`、`m.MemoryStore`、`m.MemoryStoreError`、`m.init_schema` SHALL 皆存在
- **AND** `m.__all__` SHALL 等於這五個名稱（順序不限）

---

### Requirement: `init_schema(conn)` idempotent migration

系統 SHALL 提供 `ohmystock.memory.init_schema(conn: sqlite3.Connection) -> None` 函式，建立以下物件：

- `memory_rows` 主表（欄位：`id INTEGER PRIMARY KEY AUTOINCREMENT`、`kind TEXT NOT NULL CHECK(kind IN ('note','lesson','proposal','review_summary'))`、`content TEXT NOT NULL`、`tags TEXT NOT NULL DEFAULT '[]'`、`source TEXT`、`created_at TEXT NOT NULL`）。
- 索引 `idx_memory_rows_kind_created_at` over `(kind, created_at)`。
- 索引 `idx_memory_rows_created_at` over `(created_at)`。
- FTS5 virtual table `memory_rows_fts` 採用 `content='memory_rows'` + `content_rowid='id'`，索引欄位僅一個：`content`。
- AFTER INSERT trigger `memory_rows_ai`、AFTER UPDATE trigger `memory_rows_au`、AFTER DELETE trigger `memory_rows_ad`，使主表變動時 FTS5 索引自動同步（與 `journal_entries_fts` 三 trigger 同形）。

函式 SHALL idempotent — 在已建好的 DB 上重複呼叫 SHALL **不**拋例外、**不**改變既有資料。所有 DDL SHALL 使用 `IF NOT EXISTS` 子句。函式 SHALL 在同一個連線中以單一 transaction commit。

若 SQLite build 不支援 FTS5，函式 SHALL 拋出 `RuntimeError`，message 包含 `"FTS5"` 字串(與 `journal/schema.py::_probe_fts5` 同邏輯）。

#### Scenario: 空 DB 上呼叫建出全部物件
- **WHEN** 在空 SQLite DB（已啟用 FTS5）上執行 `init_schema(conn)`
- **THEN** `sqlite_master` SHALL 出現 `memory_rows`、`memory_rows_fts` 兩個 table 名稱
- **AND** `sqlite_master WHERE type='trigger'` 結果包含 `memory_rows_ai`、`memory_rows_au`、`memory_rows_ad`
- **AND** `sqlite_master WHERE type='index'` 結果包含 `idx_memory_rows_kind_created_at` 與 `idx_memory_rows_created_at`

#### Scenario: 重複呼叫不拋例外
- **WHEN** 在已執行過 `init_schema(conn)` 的 DB 上再次呼叫 `init_schema(conn)`
- **THEN** SHALL NOT 拋例外
- **AND** 表結構與資料 SHALL 不變

#### Scenario: SQLite 缺 FTS5 時拋清楚錯誤
- **WHEN** 在不支援 FTS5 的 SQLite build 上執行 `init_schema(conn)`
- **THEN** SHALL 拋出 `RuntimeError`，message 包含 `"FTS5"` 字串

#### Scenario: kind CHECK 阻擋非法值
- **WHEN** 在 `init_schema` 後嘗試 `INSERT INTO memory_rows(kind, content, tags, source, created_at) VALUES ('random', 'x', '[]', NULL, '2026-05-09T10:00:00+08:00')`
- **THEN** SQLite SHALL 拋 `IntegrityError`（CHECK constraint failed）

#### Scenario: tags 預設空 JSON 陣列
- **WHEN** 在 `init_schema` 後執行 `INSERT INTO memory_rows(kind, content, created_at) VALUES ('note', 'x', '2026-05-09T10:00:00+08:00')`（不帶 tags 欄位）
- **THEN** INSERT SHALL 成功
- **AND** `SELECT tags FROM memory_rows WHERE id = last_insert_rowid()` SHALL 回傳 `'[]'`

#### Scenario: FTS5 trigger 自動同步 INSERT
- **GIVEN** 在 `init_schema` 後 INSERT 一筆 `content='VCP breakout 杯柄突破'` 的 row
- **WHEN** 執行 `SELECT rowid FROM memory_rows_fts WHERE memory_rows_fts MATCH 'breakout'`
- **THEN** 結果 SHALL 至少回傳一筆，rowid 為剛才 INSERT 的 row

#### Scenario: FTS5 trigger 自動同步 UPDATE
- **GIVEN** 一筆 `content='foo'` 的 row（rowid=10）
- **WHEN** UPDATE 其 content 為 `'bar'`，再 `SELECT rowid FROM memory_rows_fts WHERE memory_rows_fts MATCH 'bar'`
- **THEN** 結果 SHALL 含 rowid=10
- **AND** `MATCH 'foo'` SHALL NOT 命中該 rowid

#### Scenario: FTS5 trigger 自動同步 DELETE
- **GIVEN** 一筆 `content='zzz'` 的 row 已被 FTS5 索引
- **WHEN** DELETE 該 row，再 `SELECT rowid FROM memory_rows_fts WHERE memory_rows_fts MATCH 'zzz'`
- **THEN** 結果 SHALL 為空

---

### Requirement: `MemoryStore.list(...)` 分頁 + 篩選

系統 SHALL 在 `src/ohmystock/memory/store.py` 提供 `MemoryStore`，建構子簽名為 `MemoryStore(conn: sqlite3.Connection)`，並提供 `list` 方法：

```
list(
    *,
    kind: MemoryKind | None = None,
    tag: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ListResult
```

`ListResult` SHALL 為 pydantic `BaseModel`（`frozen=True`、`extra="forbid"`），欄位：`items: list[MemoryRow]`、`total: int`、`limit: int`、`offset: int`、`has_more: bool`。

行為：

- 排序 SHALL 為 `created_at DESC, id DESC`（最新在前）。
- `limit` 超過 200 時 store SHALL 自動 clamp 為 200，回傳的 `ListResult.limit` SHALL 反映 clamp 後的值。`limit <= 0` SHALL 拋 `MemoryStoreError("invalid_input")`。
- `offset < 0` SHALL 拋 `MemoryStoreError("invalid_input")`。
- `kind` 若非 `None` 必須是合法 `MemoryKind`；非法值（包含空字串）SHALL 拋 `MemoryStoreError("invalid_input")`。
- `tag` 為 exact match：使用 SQLite `EXISTS (SELECT 1 FROM json_each(memory_rows.tags) WHERE value = ?)` 子句，參數綁定，無 string concat。
- `total` SHALL 為符合條件（含 `kind`/`tag` 篩選）的總筆數。
- `has_more` SHALL 為 `offset + len(items) < total`。

#### Scenario: 空 DB 回傳空 ListResult
- **GIVEN** 空 `memory_rows` 表
- **WHEN** `MemoryStore(conn).list()` 被呼叫
- **THEN** SHALL 回傳 `ListResult(items=[], total=0, limit=50, offset=0, has_more=False)`

#### Scenario: 排序 created_at DESC, id DESC
- **GIVEN** 三筆 row：`(id=1, created_at='2026-05-09T10:00:00+08:00')`、`(id=2, created_at='2026-05-09T11:00:00+08:00')`、`(id=3, created_at='2026-05-09T11:00:00+08:00')`
- **WHEN** `list(limit=10)` 被呼叫
- **THEN** `items[*].id` SHALL 為 `[3, 2, 1]`

#### Scenario: kind 篩選
- **GIVEN** rows 中混合 `kind='note'` 與 `kind='lesson'`
- **WHEN** `list(kind='lesson')` 被呼叫
- **THEN** `items` SHALL 全部 `kind='lesson'`
- **AND** `total` SHALL 等於 `lesson` row 的總數

#### Scenario: tag 篩選 exact match
- **GIVEN** rows：`(id=1, tags=['vcp', 'breakout'])`、`(id=2, tags=['vcp'])`、`(id=3, tags=['breakout'])`、`(id=4, tags=[])`
- **WHEN** `list(tag='vcp')` 被呼叫
- **THEN** `items[*].id` SHALL 等於 `{1, 2}`（順序由 created_at DESC 決定）

#### Scenario: kind + tag 同時生效
- **GIVEN** rows 中只有 `(id=1, kind='lesson', tags=['vcp'])` 同時符合
- **WHEN** `list(kind='lesson', tag='vcp')` 被呼叫
- **THEN** `items` SHALL 為長度 1 且 `id=1`
- **AND** `total` SHALL 等於 1

#### Scenario: limit clamp 至 200
- **GIVEN** 表中有 300 筆 row
- **WHEN** `list(limit=999)` 被呼叫
- **THEN** `len(items)` SHALL ≤ 200
- **AND** 回傳的 `ListResult.limit` SHALL 為 200
- **AND** `total` SHALL 為 300
- **AND** `has_more` SHALL 為 `True`

#### Scenario: offset 分頁
- **GIVEN** 100 筆 row
- **WHEN** `list(limit=50, offset=50)` 被呼叫
- **THEN** `len(items)` SHALL 為 50
- **AND** `offset` 回傳值 SHALL 為 50
- **AND** `has_more` SHALL 為 `False`

#### Scenario: limit <= 0 拋 invalid_input
- **WHEN** `list(limit=0)` 被呼叫
- **THEN** SHALL 拋 `MemoryStoreError`，`code` 屬性等於 `"invalid_input"`

#### Scenario: offset < 0 拋 invalid_input
- **WHEN** `list(offset=-1)` 被呼叫
- **THEN** SHALL 拋 `MemoryStoreError("invalid_input")`

#### Scenario: 非法 kind 拋 invalid_input
- **WHEN** `list(kind='garbage')` 被呼叫
- **THEN** SHALL 拋 `MemoryStoreError("invalid_input")`，message 提到允許的 kind 值

---

### Requirement: `MemoryStore.search(...)` FTS5 BM25 排名

系統 SHALL 提供 `MemoryStore.search(*, q: str, limit: int = 50, offset: int = 0) -> ListResult`：

- `q` SHALL 經以下處理：去除前後空白、剝除 ASCII 控制字元（`\x00`–`\x1F` 與 `\x7F`）。
- 處理後若為空字串，SHALL 拋 `MemoryStoreError("invalid_input")`。
- 處理後的 `q` SHALL 直接以參數綁定方式傳入 `SELECT ... FROM memory_rows_fts WHERE memory_rows_fts MATCH ? ORDER BY bm25(memory_rows_fts) ASC, rowid ASC LIMIT ? OFFSET ?` — 不做 token 拆解、不加引號、不轉義。
- FTS5 語法錯誤（`sqlite3.OperationalError` 含 `fts5` 或 `syntax error` 字樣）SHALL 被捕捉並 remap 為 `MemoryStoreError("invalid_query")`；原始 SQLite 錯誤訊息 SHALL NOT 出現在 `MemoryStoreError` 的 message 中。
- 結果集 join 回 `memory_rows` 取得完整欄位後組成 `MemoryRow`；`ListResult` 同 list 回傳。
- 排序 SHALL 為 BM25 ASC（分數越低越相關），相同分數時依 `rowid ASC` tie-break。
- 不接受 `kind` / `tag` 篩選參數（v0 範圍）。
- `limit` clamp 規則同 `list`（≤ 200，`<= 0` 拋 `invalid_input`）。
- `offset < 0` 拋 `invalid_input`。
- `total` SHALL 為符合 `MATCH` 條件的總命中筆數（不受 limit/offset 影響）。

#### Scenario: 命中與排序
- **GIVEN** rows：`(id=1, content='breakout breakout breakout')`、`(id=2, content='breakout once')`、`(id=3, content='unrelated')`
- **WHEN** `search(q='breakout')` 被呼叫
- **THEN** `items[*].id` 前兩筆 SHALL 為 `[1, 2]`（id=1 詞頻較高 → BM25 較低 → 排在前）
- **AND** id=3 SHALL NOT 出現
- **AND** `total` SHALL 等於 2

#### Scenario: 空 q 拋 invalid_input
- **WHEN** `search(q='')` 被呼叫
- **THEN** SHALL 拋 `MemoryStoreError("invalid_input")`

#### Scenario: 純空白 q 拋 invalid_input
- **WHEN** `search(q='   \t\n')` 被呼叫
- **THEN** SHALL 拋 `MemoryStoreError("invalid_input")`

#### Scenario: 控制字元被剝除後仍合法
- **GIVEN** row `(id=5, content='hello world')`
- **WHEN** `search(q='hello\x00 world')` 被呼叫
- **THEN** SHALL NOT 拋例外
- **AND** `items[*].id` SHALL 含 5

#### Scenario: FTS5 語法錯誤 remap
- **WHEN** `search(q='foo OR')` 被呼叫（FTS5 trailing operator）
- **THEN** SHALL 拋 `MemoryStoreError`，`code == "invalid_query"`
- **AND** message SHALL NOT 包含原始 `sqlite3.OperationalError` 文字（不出現 `"fts5: syntax error"` 字樣）

#### Scenario: 高階 FTS5 表達式可用
- **GIVEN** rows：`(id=1, content='VCP breakout')`、`(id=2, content='VCP only')`、`(id=3, content='breakout only')`
- **WHEN** `search(q='VCP AND breakout')` 被呼叫
- **THEN** `items[*].id` SHALL 等於 `[1]`
- **AND** `total` SHALL 為 1

#### Scenario: 無命中回傳空 list
- **GIVEN** 表中無 row 含 `'zzzzzzzz'`
- **WHEN** `search(q='zzzzzzzz')` 被呼叫
- **THEN** SHALL 回傳 `ListResult(items=[], total=0, limit=50, offset=0, has_more=False)`

#### Scenario: limit clamp 至 200
- **GIVEN** 1000 筆 row 全都命中 `'common'`
- **WHEN** `search(q='common', limit=999)` 被呼叫
- **THEN** `len(items)` SHALL ≤ 200
- **AND** 回傳的 `ListResult.limit` SHALL 為 200
- **AND** `total` SHALL 為 1000
- **AND** `has_more` SHALL 為 `True`

---

### Requirement: `MemoryStoreError` 形狀

系統 SHALL 在 `src/ohmystock/memory/store.py` 定義 `class MemoryStoreError(Exception)`，建構子接受 `code: str` 與選擇性 `message: str | None = None`。`code` 屬性 SHALL 暴露為 `error.code`，`__str__` SHALL 回傳 `f"{code}: {message}"`（若 message 為 None 則回傳 `code`）。

允許的 `code` 值（v0）：`"invalid_input"`、`"invalid_query"`。新增其他 code SHALL 透過後續 change，本 capability 範圍內 store 不應拋出超出此集合的 code。

#### Scenario: 例外 code 屬性可讀取
- **WHEN** 拋出 `MemoryStoreError("invalid_input", "limit must be positive")`
- **THEN** `error.code` SHALL 為 `"invalid_input"`
- **AND** `str(error)` SHALL 包含 `"invalid_input"` 與 `"limit must be positive"`

#### Scenario: code 唯一允許集合
- **WHEN** 跑完整 store unit test suite 後檢查所有拋出的 `MemoryStoreError.code` 值
- **THEN** 集合 SHALL 為 `{"invalid_input", "invalid_query"}` 的子集

---

### Requirement: 不暴露寫入 API

`MemoryStore` SHALL NOT 提供 `add(...)`、`update(...)`、`delete(...)` 或任何修改 `memory_rows` 的方法。`__init__.py` 公開符號中 SHALL NOT 含 writer 函式名稱。

#### Scenario: 公開符號中無 writer
- **WHEN** `import ohmystock.memory as m`
- **THEN** `hasattr(m.MemoryStore, "add")` SHALL 為 `False`
- **AND** `hasattr(m.MemoryStore, "update")` SHALL 為 `False`
- **AND** `hasattr(m.MemoryStore, "delete")` SHALL 為 `False`

---

### Requirement: Memory 寫入（insert）

MemoryStore SHALL 提供 insert 路徑，寫入一筆 memory（kind/content/tags/source），並透過既有 FTS5 INSERT 觸發器同步索引。schema 不變。

#### Scenario: insert 後可檢索

- **WHEN** 透過 store insert 一筆 memory
- **THEN** 該筆可由 list 取得，且其 content 可由 FTS5 search 命中

#### Scenario: insert 寫入 created_at

- **WHEN** insert 一筆 memory
- **THEN** 該筆帶有 created_at（ISO 8601，含時區）
