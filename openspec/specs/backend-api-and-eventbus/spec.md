# backend-api-and-eventbus Specification

## Purpose

定義 FastAPI backend、SSE event 通道、SQLite 連線初始化，與 in-process EventBus pub/sub 骨架。本 capability 對應 `docs/backend-eventbus.md` 的執行面：API 端點 / SSE 廣播 / DB 初始化 / EventBus 介面。實際 emitter 與 14 個 event_type 字串、auth、masked serializer、Trade Journal 表 schema 由後續 change 補完。

## Requirements

### Requirement: FastAPI app factory 與健康檢查端點

系統 SHALL 提供 `ohmystock.api.app.create_app()` 函式，回傳一個 `FastAPI` 實例。該實例 SHALL 至少註冊 `GET /healthz` 端點，回傳 JSON `{"status": "ok", "version": "<package version>"}`，HTTP 200。`version` 欄位的值 SHALL 來自套件 metadata（如 `importlib.metadata.version("ohmystock")`），允許後續 change 升級套件版本時自動反映。本 change 階段 `/healthz` SHALL 為同步、無認證、不查任何下游子系統（DB / EventBus）。

#### Scenario: `create_app` 回傳 FastAPI 實例
- **WHEN** 在 Python 內執行 `from ohmystock.api.app import create_app; app = create_app()`
- **THEN** import 成功，`app` 為 `fastapi.FastAPI` 的實例，無例外拋出

#### Scenario: `/healthz` 回 200 + JSON
- **WHEN** 對 `create_app()` 結果發起 `GET /healthz`（透過 ASGI test client 或 uvicorn）
- **THEN** HTTP 狀態碼為 200，response body 為 JSON，包含 key `"status"`（值為 `"ok"`）與 key `"version"`（值為非空字串，等於 `importlib.metadata.version("ohmystock")` 的回傳）

#### Scenario: `/healthz` 不要求認證
- **WHEN** 對 `/healthz` 發起 `GET` 不帶任何 `Authorization` header
- **THEN** HTTP 狀態碼仍為 200（不為 401 / 403）

---

### Requirement: Admin SSE 心跳通道

系統 SHALL 提供 `GET /api/admin/events` 端點，回傳 `Content-Type: text/event-stream`（SSE）的長連線回應。本 change 階段該通道 SHALL 為 stub heartbeat：以最多 15 秒一次的頻率送出至少 1 筆 SSE message（可為 `event: heartbeat` 或預設 `: keepalive` ping，由 `sse-starlette` 提供），確保前端能驗證通道存活。本 change 不接 `EventBus` 的真實 event 廣播；該整合留給後續 change（`web-admin-bearer-auth` 起接 EventBus subscribe + auth）。

依 `docs/backend-eventbus.md` §5（SSE Endpoint API）規格，本 change 只實作 admin channel 骨架；`/api/public/events` 不在本 change 範圍。

#### Scenario: `/api/admin/events` 回 200 + SSE content-type
- **WHEN** 對 `/api/admin/events` 發起 `GET` 並讀取 response headers
- **THEN** HTTP 狀態碼為 200，response header `content-type` 開頭為 `text/event-stream`

#### Scenario: 通道在合理時間內送出至少 1 筆 message
- **WHEN** 對 `/api/admin/events` 開啟 SSE 連線並讀取 stream，等待至多 16 秒
- **THEN** 收到至少 1 筆 SSE message（line 開頭為 `data:`、`event:` 或 `:` 任一），客戶端隨後可主動 close connection 而不引發 server error

---

### Requirement: SQLite 連線初始化（WAL + foreign keys + FTS5 探測）

系統 SHALL 提供 `ohmystock.api.db.get_connection()` 函式，回傳一個 `sqlite3.Connection`。該 function SHALL：(a) 從 `Settings.ohmystock_db_path` 解析資料庫檔路徑（呼叫 `Path.expanduser()`）、(b) 自動建立父目錄（`mkdir(parents=True, exist_ok=True)`）、(c) 對 connection 執行 `PRAGMA journal_mode = WAL` 與 `PRAGMA foreign_keys = ON`、(d) 在首次呼叫時驗證 SQLite build 是否含 FTS5（嘗試在 in-memory connection 建立 `CREATE VIRTUAL TABLE _fts_probe USING fts5(x)`），若失敗 SHALL raise `RuntimeError`，錯誤訊息 SHALL 包含關鍵字 `FTS5` 與修補建議。

依 `docs/design-zh-TW.md` §4 對 SQLite + FTS5 的選用，與 `llm-decision-schema.md` §4 對 Trade Journal FTS5 的依賴；本 change 只建立連線骨架，實際表 schema 由 `external-connectors-and-cost` 寫入。

#### Scenario: `get_connection()` 回傳啟用 WAL 的 connection
- **WHEN** 在乾淨環境執行 `from ohmystock.api.db import get_connection; conn = get_connection(); cur = conn.execute("PRAGMA journal_mode")`
- **THEN** `cur.fetchone()[0]` 等於 `"wal"`（不分大小寫）

#### Scenario: foreign_keys 已啟用
- **WHEN** 執行 `conn = get_connection(); cur = conn.execute("PRAGMA foreign_keys")`
- **THEN** `cur.fetchone()[0]` 等於 `1`

#### Scenario: 父目錄自動建立
- **WHEN** `Settings.ohmystock_db_path` 指向不存在的子目錄路徑（如 `<tmp>/nested/dir/journal.db`），執行 `get_connection()`
- **THEN** 命令成功完成；該子目錄被建立；DB 檔案存在於指定路徑

#### Scenario: FTS5 缺失時 fail-fast
- **WHEN** 在無 FTS5 的 SQLite build 環境執行 `get_connection()`（或內部 FTS5 探測）
- **THEN** 拋出 `RuntimeError`，例外訊息 SHALL 包含字串 `FTS5`

---

### Requirement: EventBus pub/sub 骨架

系統 SHALL 提供 `ohmystock.eventbus.bus.EventBus` class 與 module-level 單例 `bus = EventBus()`，介面規格 1:1 對齊 `docs/backend-eventbus.md` §2.2：

- `subscribe() -> asyncio.Queue[Event]`：建立並回傳一個 `maxsize=1024` 的 queue，並把該 queue 加入內部 subscriber list
- `unsubscribe(q: asyncio.Queue[Event]) -> None`：從 subscriber list 移除指定 queue
- `async emit(event: Event) -> None`：對所有 subscriber `put_nowait(event)`，個別 queue 滿時 SHALL silently skip 而不阻塞或拋例外（避免級聯阻塞）

`bus` SHALL 為全 process 唯一實例（module-level，import 即取得）。本 change 不實際從任何 hook / service emit；emitter 由後續 change 補。

#### Scenario: subscribe → emit → 收到 event
- **WHEN** 在 async context 執行 `q = bus.subscribe(); await bus.emit(Event(event_type="test", agent="t")); ev = await asyncio.wait_for(q.get(), timeout=1.0); bus.unsubscribe(q)`
- **THEN** `ev.event_type == "test"`，`ev.agent == "t"`，無例外或 timeout

#### Scenario: 多 subscriber 廣播
- **WHEN** 兩個 subscriber 同時訂閱，emit 一筆 event
- **THEN** 兩個 queue 各自能取出該 event（同一個物件 reference 或等價內容）

#### Scenario: queue 滿時不阻塞
- **WHEN** 一個 subscriber queue 已塞滿（達到 `maxsize=1024`），emit 第 1025 筆 event
- **THEN** `emit` 不拋例外、不阻塞；其他未滿的 subscriber 仍正常收到該 event

#### Scenario: `bus` 為 module-level 單例
- **WHEN** 在不同模組分別執行 `from ohmystock.eventbus.bus import bus`
- **THEN** 兩處取到的 `bus` 為同一物件（`is` 比較為 `True`）

---

### Requirement: Event dataclass schema

系統 SHALL 提供 `ohmystock.eventbus.events.Event` `@dataclass(frozen=True, slots=True)`，包含五個欄位（依 `docs/backend-eventbus.md` §3.1）：

- `event_type: str`（必填）
- `agent: str`（必填）
- `payload: dict[str, Any]`（預設 `{}`）
- `event_id: str`（預設 `f"evt_{uuid4().hex[:12]}"`）
- `timestamp: datetime`（預設 `datetime.now(TPE)`，其中 `TPE = timezone(timedelta(hours=8))`）

本 change **不**定義 14 個 event_type 字串常數（如 `"screener_started"`），這些由後續 change（emitter 接入時）逐項補上。

#### Scenario: Event 必填欄位與預設值
- **WHEN** 執行 `Event(event_type="screener_started", agent="scanner")`
- **THEN** 物件建立成功；`payload == {}`、`event_id` 開頭為 `"evt_"` 且 ASCII 長度為 `4 + 12`、`timestamp.utcoffset() == timedelta(hours=8)`

#### Scenario: Event 為不可變
- **WHEN** 對已建立的 `Event` 實例嘗試 `ev.event_type = "x"`
- **THEN** 拋出 `dataclasses.FrozenInstanceError`（或 `AttributeError`）

#### Scenario: event_id 唯一性（best-effort）
- **WHEN** 連續建立 1000 個 `Event` 實例
- **THEN** 1000 個 `event_id` 兩兩不同（碰撞機率 < 1e-9，視為唯一）
