## ADDED Requirements

### Requirement: Trade Journal schema 由 init_schema(conn) 提供 idempotent migration

系統 SHALL 提供 `ohmystock.journal.schema.init_schema(conn)` 作為 Trade Journal 全部 SQLite 物件（表、索引、FTS5 virtual table、trigger）的唯一建立入口。`get_connection()`（位於 `ohmystock.api.db`）的回傳連線 SHALL 可直接傳入 `init_schema()` 而不需任何前置設定。本 Requirement **不**規定 FastAPI app 必須在 startup 自動呼叫 `init_schema()`（留給後續 change 視 endpoint 需求決定）；但 SHALL 保證一旦呼叫即可建出全部 Trade Journal 物件。

#### Scenario: get_connection() 回傳的連線可餵 init_schema()
- **WHEN** 執行 `from ohmystock.api.db import get_connection; from ohmystock.journal.schema import init_schema; conn = get_connection(); init_schema(conn)`（在乾淨 DB path）
- **THEN** 不拋例外；`conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()` 結果包含 `journal_entries` 與 `llm_costs`

#### Scenario: 兩個模組之間無循環引用
- **WHEN** 執行 `python -c "import ohmystock.api.db; import ohmystock.journal.schema"`
- **THEN** 不拋 `ImportError`、`CircularImportError`，且兩個模組可任意順序 import

---

### Requirement: 三方 client 與 cost tracker 不依賴 FastAPI runtime

系統 SHALL 確保 `ohmystock.data.finmind_client`、`ohmystock.paper.shioaji_client`、`ohmystock.observability.cost_tracker`、`ohmystock.journal.schema` 四個模組可在**未啟動 FastAPI app** 的情境下被 import 與使用（CLI smoke-test、pytest、未來離線批次任務皆需要）。這些模組 SHALL **不**從 `ohmystock.api.app` 反向 import，避免 FastAPI 變成 hard dependency。

#### Scenario: CLI 場景（無 FastAPI）可使用三方 client
- **WHEN** 在子程序執行 `python -c "from ohmystock.data.finmind_client import FinMindClient; from ohmystock.paper.shioaji_client import ShioajiPaperClient; from ohmystock.observability.cost_tracker import track_llm_cost; from ohmystock.journal.schema import init_schema"`
- **THEN** 不拋例外，且**不**載入 `fastapi` / `uvicorn` / `starlette` 任一模組（可透過 `sys.modules` 檢查）

#### Scenario: 反向 import 禁令
- **WHEN** 用 grep 檢查上述四個模組的 source
- **THEN** 任一模組 SHALL **不**包含 `from ohmystock.api` / `import ohmystock.api` 字樣（避免反向依賴）
