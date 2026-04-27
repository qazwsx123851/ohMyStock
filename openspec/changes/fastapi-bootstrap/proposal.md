## Why

`cli-skeleton`（已 archived 為 `2026-04-27-cli-skeleton`）已上線 `ohmystock --help` 與 5 個子命令 stub，但尚無 FastAPI app 與 EventBus 通道；CLAUDE.md §4 架構圖中的「UI ↔ Backend EventBus ↔ Agent 核心」中段在 repo 內仍是空殼（`src/ohmystock/api/` 與 `src/ohmystock/eventbus/` 只有 `__init__.py`）。本 change 補上 FastAPI app、`/healthz` 健康檢查、最小 SSE 心跳通道、SQLite 初始化與 EventBus pub/sub 骨架，作為後續 `external-connectors-and-cost`（Phase 0d）寫 Trade Journal、`web-admin-bearer-auth`（Phase 4）接 admin 18 頁、`web-public-pixel-and-mask`（Phase 4.5）接 public pixel 的著陸點。對應 milestone Phase 0c（`docs/v3-decisions.md` §5、`C:\Users\Oolong\.claude\plans\sdd-distributed-pretzel.md` §2.2 Change 3）。

## What Changes

- **新增** `src/ohmystock/api/app.py`：`FastAPI` app factory `create_app()`，註冊 `/healthz`（同步 GET，回 `{"status": "ok", "version": <pkg version>}`）與 `/api/admin/events`（SSE，先 stub 每 15 秒 heartbeat event）兩個 route；不接 auth、不接 Mask serializer
- **新增** `src/ohmystock/api/db.py`：`get_connection()` 開啟 SQLite，啟用 `PRAGMA journal_mode=WAL` 與 `PRAGMA foreign_keys=ON`，並驗證 SQLite build 是否含 FTS5（建立暫存 FTS5 virtual table 探測，缺 FTS5 時 raise `RuntimeError` 帶清楚訊息）；資料庫路徑取自 `Settings.ohmystock_db_path`，自動 `mkdir parents=True, exist_ok=True`
- **新增** `src/ohmystock/eventbus/bus.py`：`EventBus` class（`subscribe()` 回 `asyncio.Queue[Event](maxsize=1024)`、`unsubscribe()`、`async emit()` 對所有 subscriber `put_nowait` 失敗即跳過），module-level `bus = EventBus()` 全 process 單例；依 `docs/backend-eventbus.md` §2.2 介面規格
- **新增** `src/ohmystock/eventbus/events.py`：`Event` `@dataclass(frozen=True, slots=True)`，欄位 `event_type / agent / payload / event_id / timestamp`（台北時區 UTC+8）；`event_id` 預設 `f"evt_{uuid4().hex[:12]}"`；本 change 不定義 14 個 event_type 常數，留給後續 change
- **新增** `cli.py` 的 `api` 子命令：`@app.command` 起 `uvicorn` 跑 `ohmystock.api.app:create_app`，預設 `--host 127.0.0.1 --port 8000 --reload/--no-reload`（dev 預設 `--reload`）；CLI 子命令清單擴充為 6（`run` / `backtest` / `review` / `propose` / `screen` / `api`）
- **修改** `pyproject.toml`：`[project.dependencies]` 新增 `fastapi>=0.115`、`uvicorn[standard]>=0.32`、`sse-starlette>=2.1`；不引入 `pydantic` 直接版本（已由 `pydantic-settings` 拉入）
- **新增** `tests/test_api.py`：4 個最小測試（`/healthz` 回 200 + JSON、`/api/admin/events` 開連線後可收到至少 1 筆 SSE heartbeat、`get_connection()` 建出可 `SELECT 1` 的 SQLite 且 FTS5 探測通過、`bus.subscribe / emit / unsubscribe` round-trip 一筆 Event 成功）
- **新增** `tests/test_cli_api.py`：1 個測試（`ohmystock api --help` 列出 host/port/reload 旗標，exit 0）
- **不做**：admin Bearer auth（留給 `web-admin-bearer-auth`）、`MaskedEventSerializer`（留給 `web-public-pixel-and-mask`）、14 個 event_type 真實 emitter、Trade Journal SQLite schema（留給 `external-connectors-and-cost`）、`/api/public/events` route、Cloudflare Tunnel 配置、Docker compose

## Capabilities

### New Capabilities

- `backend-api-and-eventbus`：FastAPI app（`/healthz` 健康檢查、`/api/admin/events` SSE 心跳通道）、SQLite 連線初始化（WAL + FTS5 探測）、in-memory EventBus pub/sub 骨架（`asyncio.Queue` based、`Event` dataclass 含台北時區 timestamp）；不含 auth、Mask、業務 endpoint，這些留給後續 change

### Modified Capabilities

- `cli-and-config`：新增 `api` 子命令（從 5 子命令擴充為 6），spec delta 採 ADDED「`api` 子命令啟動 FastAPI」一條 Requirement；既有「CLI 子命令骨架」Requirement 須 MODIFIED 把子命令清單從 5 個更新為 6 個（`run` / `backtest` / `review` / `propose` / `screen` / `api`），且 `api` **非** stub（會真正啟 server，與其他 5 個 `not implemented` 行為不同）

## Impact

- **新增依賴**：`fastapi>=0.115`（含 transitive `starlette`、`pydantic v2`）、`uvicorn[standard]>=0.32`（含 `httptools`、`uvloop` 在 non-Windows / `watchfiles` reload）、`sse-starlette>=2.1`（提供 `EventSourceResponse`）。`uv sync` 之後 `uv.lock` 會更新
- **新增檔案**：`src/ohmystock/api/app.py`、`src/ohmystock/api/db.py`、`src/ohmystock/eventbus/bus.py`、`src/ohmystock/eventbus/events.py`、`tests/test_api.py`、`tests/test_cli_api.py`
- **修改檔案**：`pyproject.toml`（新增 3 個 deps）、`uv.lock`（rerun `uv sync` 後）、`src/ohmystock/cli.py`（新增 `api` 子命令）、`tests/test_cli.py`（更新 `test_root_help_lists_all_subcommands` 把斷言從 5 子命令擴成 6 子命令、`test_subcommand_stub_returns_not_implemented` 的 parametrize 不含 `api`）
- **不影響**：`docs/`（不修改任何設計文件，需要的 schema 與架構規格皆 reference 自 `docs/backend-eventbus.md`）、`.env.example`（沿用既有 `OHMYSTOCK_DB_PATH`）、其他 16 個子模組目錄
- **後續 unblock**：`external-connectors-and-cost`（Phase 0d）— 將在 `src/ohmystock/journal/schema.py` 寫入第一張表，並用 `get_connection()` 開檔；`web-admin-bearer-auth`（Phase 4）— 在 `app.py` 套 Bearer middleware、把 `/api/admin/events` 從 stub heartbeat 換成 real EventBus subscribe；`web-public-pixel-and-mask`（Phase 4.5）— 新增 `/api/public/events` 並接 `MaskedEventSerializer`
