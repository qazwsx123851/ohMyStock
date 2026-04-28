## 1. 依賴更新

- [x] 1.1 編輯 `pyproject.toml` `[project.dependencies]`：在現有的 `typer>=0.12`、`pydantic-settings>=2.0` 之後新增 `fastapi>=0.115`、`uvicorn[standard]>=0.32`、`sse-starlette>=2.1`
- [x] 1.2 編輯 `pyproject.toml` `[dependency-groups.dev]`（或既有 dev section）：新增 `httpx>=0.27`、`pytest-asyncio>=0.24`（給 ASGI test client + async test 用）
- [x] 1.3 在 `pyproject.toml` 同層新增（若尚未有）`[tool.pytest.ini_options]` 區塊，設定 `asyncio_mode = "auto"`，避免每個 async test 加 `@pytest.mark.asyncio`
- [x] 1.4 執行 `uv sync` 並確認 `uv.lock` 更新；exit 0
- [x] 1.5 驗證 `uv run python -c "import fastapi, uvicorn, sse_starlette, httpx; import pytest_asyncio"` exit 0

## 2. `ohmystock.eventbus.events.Event` dataclass

- [x] 2.1 建立 `src/ohmystock/eventbus/events.py`：定義 `TPE = timezone(timedelta(hours=8))` module-level 常數
- [x] 2.2 定義 `@dataclass(frozen=True, slots=True) class Event` 含五個欄位：`event_type: str`、`agent: str`、`payload: dict[str, Any] = field(default_factory=dict)`、`event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")`、`timestamp: datetime = field(default_factory=lambda: datetime.now(TPE))`
- [x] 2.3 驗證：`uv run python -c "from ohmystock.eventbus.events import Event; e = Event(event_type='t', agent='a'); assert e.payload == {} and e.event_id.startswith('evt_') and len(e.event_id) == 16 and e.timestamp.utcoffset().total_seconds() == 8*3600; print('ok')"` 印 `ok`

## 3. `ohmystock.eventbus.bus.EventBus` 與 `bus` 單例

- [x] 3.1 建立 `src/ohmystock/eventbus/bus.py`：依 `docs/backend-eventbus.md` §2.2 寫 `class EventBus`：`_subscribers: list[Queue[Event]]`、`subscribe()` 回 `Queue(maxsize=1024)` 並 append 到 list、`unsubscribe(q)` 從 list 移除、`async emit(event)` 對所有 q `try: q.put_nowait(event); except Exception: pass`
- [x] 3.2 在 module 末尾加 `bus = EventBus()` 全 process 單例
- [x] 3.3 驗證：`uv run python -c "from ohmystock.eventbus.bus import bus, EventBus; assert isinstance(bus, EventBus); print('ok')"` 印 `ok`

## 4. `ohmystock.api.db.get_connection`

- [x] 4.1 建立 `src/ohmystock/api/db.py`：`import sqlite3` + `from pathlib import Path` + `from ohmystock.config import Settings`
- [x] 4.2 實作 module-level `_FTS5_OK: bool | None = None` cache 與 `_probe_fts5() -> None` 函式：開 in-memory `sqlite3.connect(":memory:")`，跑 `CREATE VIRTUAL TABLE _fts_probe USING fts5(x)`；成功則 set cache，失敗則 raise `RuntimeError("SQLite build lacks FTS5; install a Python build with FTS5 enabled or use pysqlite3-binary. Original error: ...")`
- [x] 4.3 實作 `def get_connection() -> sqlite3.Connection`：(a) 第一次呼叫先 `_probe_fts5()`、(b) `path = Path(Settings().ohmystock_db_path).expanduser()`、(c) `path.parent.mkdir(parents=True, exist_ok=True)`、(d) `conn = sqlite3.connect(str(path))`、(e) `conn.execute("PRAGMA journal_mode = WAL")`、(f) `conn.execute("PRAGMA foreign_keys = ON")`、(g) `return conn`
- [x] 4.4 驗證：`uv run python -c "from ohmystock.api.db import get_connection; c = get_connection(); assert c.execute('PRAGMA journal_mode').fetchone()[0].lower() == 'wal'; assert c.execute('PRAGMA foreign_keys').fetchone()[0] == 1; c.close(); print('ok')"` 印 `ok`

## 5. `ohmystock.api.app.create_app`

- [x] 5.1 建立 `src/ohmystock/api/app.py`：`from fastapi import FastAPI`、`from sse_starlette.sse import EventSourceResponse`、`from importlib.metadata import version as _pkg_version`、`import asyncio`、`import json`、`from datetime import datetime`、`from ohmystock.eventbus.events import TPE`
- [x] 5.2 實作 `def create_app() -> FastAPI`：建 `app = FastAPI(title="ohMyStock API", version=_pkg_version("ohmystock"))`
- [x] 5.3 在 factory 內註冊 `GET /healthz`：sync handler，return `{"status": "ok", "version": _pkg_version("ohmystock")}`
- [x] 5.4 在 factory 內註冊 `GET /api/admin/events`：async handler 回傳 `EventSourceResponse(_admin_event_stream())`，其中 `_admin_event_stream` 是 async generator，`while True: yield {"event": "heartbeat", "data": json.dumps({"ts": datetime.now(TPE).isoformat()})}; await asyncio.sleep(15)`（heartbeat interval 15 秒；本 change 不接 `EventBus`）
- [x] 5.5 factory 末尾 `return app`；module 不 expose 任何 module-level `app` 變數（強制 factory mode）
- [x] 5.6 驗證：`uv run python -c "from ohmystock.api.app import create_app; app = create_app(); routes = {r.path for r in app.routes}; assert '/healthz' in routes and '/api/admin/events' in routes; print('ok')"` 印 `ok`

## 6. `cli.py` 新增 `api` 子命令

- [x] 6.1 編輯 `src/ohmystock/cli.py`：在現有 5 子命令後新增 `@app.command(help="啟動 FastAPI backend（uvicorn + factory mode；本機 dev 預設 reload）")` 裝飾的 `api` 函式
- [x] 6.2 `api` 函式 signature：`def api(host: str = typer.Option("127.0.0.1", help="..."), port: int = typer.Option(8000, help="..."), reload: bool = typer.Option(True, "--reload/--no-reload", help="..."))`
- [x] 6.3 函式體：`import uvicorn; uvicorn.run("ohmystock.api.app:create_app", host=host, port=port, reload=reload, factory=True)`（不放 try/except；ctrl-C 走 uvicorn 內建 graceful shutdown）
- [x] 6.4 驗證：`uv run ohmystock --help` stdout 同時含 `run`、`backtest`、`review`、`propose`、`screen`、`api` 六個名稱；exit 0
- [x] 6.5 驗證：`uv run ohmystock api --help` exit 0；stdout 含 `--host`、`--port`、`--reload`、`--no-reload` 四個旗標
- [x] 6.6 驗證：`uv run ohmystock api --help` stdout **不**含字串 `not implemented`

## 7. 既有測試更新

- [x] 7.1 編輯 `tests/test_cli.py` 的 `test_root_help_lists_all_subcommands`：把斷言從 5 子命令擴成 6 子命令（多斷言 `"api" in result.output`）
- [x] 7.2 編輯 `tests/test_cli.py` 的 `test_subcommand_stub_returns_not_implemented` 的 `pytest.mark.parametrize`：保持 5 個 stub 子命令（`run` / `backtest` / `review` / `propose` / `screen`），**不**加 `api`（`api` 非 stub）
- [x] 7.3 驗證：`uv run pytest tests/test_cli.py -v` 全綠

## 8. 新測試 `tests/test_api.py`

- [x] 8.1 建立 `tests/test_api.py`：`import pytest`、`import asyncio`、`from httpx import AsyncClient, ASGITransport`、`from ohmystock.api.app import create_app`、`from ohmystock.api.db import get_connection`、`from ohmystock.eventbus.bus import EventBus`、`from ohmystock.eventbus.events import Event`
- [x] 8.2 fixture `app_client`：async fixture，`async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client: yield client`
- [x] 8.3 寫 `test_healthz_returns_ok`：async test，`r = await app_client.get("/healthz")`；斷言 `r.status_code == 200`、`r.json()["status"] == "ok"`、`isinstance(r.json()["version"], str) and len(r.json()["version"]) > 0`
- [x] 8.4 寫 `test_admin_events_returns_sse_content_type`：async test，用 `app_client.stream("GET", "/api/admin/events")` 開 stream context；斷言 response status 200、`response.headers["content-type"].startswith("text/event-stream")`；不等 message，立即 break/close（避免測試卡 15 秒）
  - **實作偏離**：httpx 0.28 `ASGITransport` 與 Starlette `TestClient` 都會 buffer 整個 response 才回 headers，遇到 `while True` 的 SSE generator 會 deadlock。改拆成兩個測試替代：(a) `test_admin_events_route_registered`（檢查 `app.routes` 含 `/api/admin/events`）、(b) `test_admin_event_stream_yields_heartbeat`（直接 await 一次 `_admin_event_stream()` 確認 dict 結構）。實際 streaming 行為由 §10.3 `curl -N` smoke test 覆蓋（已綠）。
- [x] 8.5 寫 `test_get_connection_pragmas`：sync test，monkeypatch env var `OHMYSTOCK_DB_PATH` 指到 `tmp_path / "test.db"` 字串；呼叫 `get_connection()`；斷言 `journal_mode == "wal"`、`foreign_keys == 1`、`(tmp_path / "test.db").exists()`
- [x] 8.6 寫 `test_eventbus_round_trip`：async test，`local_bus = EventBus()`；`q = local_bus.subscribe()`；`await local_bus.emit(Event(event_type="x", agent="t"))`；`ev = await asyncio.wait_for(q.get(), timeout=1.0)`；斷言 `ev.event_type == "x"`；`local_bus.unsubscribe(q)`
- [x] 8.7 驗證：`uv run pytest tests/test_api.py -v` 全綠（4 條測試通過）

## 9. 新測試 `tests/test_cli_api.py`

- [x] 9.1 建立 `tests/test_cli_api.py`：`from typer.testing import CliRunner`、`from ohmystock.cli import app`，`runner = CliRunner()`
- [x] 9.2 寫 `test_api_help_lists_flags`：`result = runner.invoke(app, ["api", "--help"])`；斷言 `result.exit_code == 0`、`"--host" in result.output`、`"--port" in result.output`、`("--reload" in result.output or "--no-reload" in result.output)`、`"not implemented" not in result.output`
- [x] 9.3 驗證：`uv run pytest tests/test_cli_api.py -v` 全綠

## 10. 端對端驗收

- [x] 10.1 在 repo root 跑完整流程：`rm -rf .venv && uv sync && uv run ohmystock --help && uv run pytest -v`，全部成功（測試總數 ≥ 12）
- [x] 10.2 手動 smoke test FastAPI server：開 terminal A 跑 `uv run ohmystock api --no-reload --port 18000`；開 terminal B 跑 `curl -fsS http://127.0.0.1:18000/healthz`，預期回 `{"status":"ok","version":"<ver>"}`；ctrl-C terminal A，server 在 ≤ 5 秒退出
- [x] 10.3 手動 smoke test SSE：terminal A 同上；terminal B 跑 `curl -N --max-time 16 http://127.0.0.1:18000/api/admin/events`，預期 ≤ 16 秒收到至少 1 筆 SSE message（line 開頭 `:`、`event:`、或 `data:`）
- [x] 10.4 確認 `git status` 列出 `pyproject.toml`、`uv.lock`（modified）、`src/ohmystock/api/app.py`、`src/ohmystock/api/db.py`、`src/ohmystock/eventbus/bus.py`、`src/ohmystock/eventbus/events.py`、`tests/test_api.py`、`tests/test_cli_api.py`（新增）、`src/ohmystock/cli.py`、`tests/test_cli.py`（modified）；無多餘檔案

## 11. 文件交叉檢查（不修改 docs/）

- [x] 11.1 確認 `pyproject.toml` 新增的 `fastapi` / `uvicorn[standard]` / `sse-starlette` 與 `CLAUDE.md` §3 技術棧表「Backend = FastAPI」一致
- [x] 11.2 確認 `Event` 欄位、`EventBus` 介面、`/api/admin/events` 路徑與 `docs/backend-eventbus.md` §2.2 / §3.1 / §5 完全一致；無新增介面、無重命名欄位
- [x] 11.3 確認本 change 沒有修改任何 `docs/*.md` 檔案（`git diff docs/` 應為空）

## 12. Archive 前準備

- [x] 12.1 執行 `openspec validate fastapi-bootstrap`，驗證 spec delta 結構正確（4-hashtag scenarios、`MODIFIED` 完整複製既有 requirement）
- [x] 12.2 執行 `openspec status --change fastapi-bootstrap --json`，確認所有 task 已 `[x]`、artifact 全 `done`
- [x] 12.3 草擬 commit message：`feat(api): fastapi app + healthz + sse heartbeat + sqlite WAL/FTS5 + eventbus skeleton`
