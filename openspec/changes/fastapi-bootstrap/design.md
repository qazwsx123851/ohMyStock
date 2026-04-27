## Context

`cli-skeleton` archive 之後，repo 已有 typer CLI（5 stub 子命令）+ `pydantic-settings.Settings`，但 `src/ohmystock/api/`、`src/ohmystock/eventbus/` 仍是空殼 `__init__.py`。本 change 把 backend HTTP 層從「目錄存在、無 entry」推進到「`uv run ohmystock api` 啟得起來、`/healthz` 可 curl、SSE 心跳可訂閱、SQLite 可開檔」。`docs/backend-eventbus.md` §2.2 / §3.1 / §5 已拍板 EventBus、Event schema 與 SSE channel 介面（in-memory `asyncio.Queue` pub/sub、`Event` frozen slots dataclass、`/api/admin/events` SSE endpoint）；本 change 在這個介面上補實作骨架，但暫不接 auth、Mask、業務 emitter。

`CLAUDE.md` §3 技術棧已決定 FastAPI；§4 架構圖已決定 EventBus 是 admin/public 兩條 SSE channel 的共同上游。本 change 拍板的範圍是「FastAPI / SSE / SQLite / asyncio Queue 的具體 library 與最小 wiring」。

## Goals / Non-Goals

**Goals:**
- `uv run ohmystock api` 啟動 FastAPI（uvicorn dev mode），ctrl-C 可乾淨關閉
- `curl http://127.0.0.1:8000/healthz` exit 0 並回 `{"status":"ok","version":"<pkg version>"}`
- `curl -N http://127.0.0.1:8000/api/admin/events` 在 ≤ 16 秒內收到 ≥ 1 筆 SSE heartbeat（`event: heartbeat\ndata: {...}`）
- `from ohmystock.api.db import get_connection; conn = get_connection()` 取得啟用 WAL + foreign keys 的 SQLite connection；FTS5 缺失時 raise `RuntimeError`
- `from ohmystock.eventbus.bus import bus; from ohmystock.eventbus.events import Event` 可在 async context 完成 `subscribe → emit → 收到 Event → unsubscribe` 一輪
- `pytest -v` 通過原 7+ 條 + 本 change 新加的 5 條（共 12+ 條）
- `cli.py` 的根 help 列出 6 子命令（`api` 加在最後）

**Non-Goals:**
- Bearer token auth / `/api/admin/*` 真正鎖權限（留 `web-admin-bearer-auth`）
- `MaskedEventSerializer` / `/api/public/events`（留 `web-public-pixel-and-mask`）
- 14 個 event_type 的 emitter 實際接到 hooks / services（留後續 phase 1+ change）
- Trade Journal / FTS5 schema DDL（留 `external-connectors-and-cost`）
- Logging / structlog 設定（沿用 `print` / FastAPI default uvicorn log；後續 change 統一接）
- Production deployment（gunicorn / multi-worker）— v1 限制單 worker，多 worker 改 Redis（`docs/backend-eventbus.md` §10）
- Cloudflare Tunnel、Docker、CI/CD

## Decisions

### D1：採用 `fastapi` + `uvicorn[standard]` + `sse-starlette`
**選 `fastapi`**：
- `CLAUDE.md` §3 已指定 FastAPI
- 與 `pydantic v2` 原生整合，`Settings` 可直接 inject
- 同 tiangolo 生態（與 `cli-skeleton` 拍板的 typer 一致），維護一致性

**選 `uvicorn[standard]`**：FastAPI 標準 ASGI server，`[standard]` extra 拉 `httptools` / `watchfiles`（reload）/ `python-dotenv`；非 Windows 還有 `uvloop`。Windows 下 watchfiles 仍可工作

**選 `sse-starlette`**：
- 提供 `EventSourceResponse`，自動處理 `text/event-stream` headers、`keepalive`、`disconnect` 偵測
- 比手刻 `StreamingResponse` 少 ~30 行樣板（`yield f"data: {json}\n\n"` + retry 處理）
- `docs/backend-eventbus.md` §5 範例就是用這個 library

**Alt 1 starlette 直接寫 SSE**：少一個 dep，但要自己處理 keepalive、ping、disconnect cleanup
**Alt 2 WebSocket**：`docs/backend-eventbus.md` §FAQ 已決議用 SSE（單向 + 自動重連 + 走 HTTP 友善代理）

### D2：app factory pattern `create_app()` 而非 module-level `app = FastAPI()`
**選 factory**：
- 測試可在 fixture 內每測重建（避免 route 累積污染、event loop 跨測殘留 subscriber）
- uvicorn `--factory` 旗標支援；`ohmystock api` 子命令傳 `--factory ohmystock.api.app:create_app`
- 後續 change 加 middleware（auth）時可把參數傳進 factory（如 `create_app(auth_required=False)`）

**Alt** module-level：簡單但 reload + test isolation 較痛

### D3：SQLite 連線採 `sqlite3` 標準庫 + `PRAGMA` 觸發於 `get_connection()`，**不**引入 SQLAlchemy / aiosqlite
**選標準庫**：
- v1 階段只開單檔 SQLite，沒必要 ORM
- WAL + foreign keys 是 PRAGMA 兩行，無 ORM 也清楚
- FTS5 目前 Python 標準庫的 `sqlite3` 在 Windows / Linux 預編譯版本通常有支援；FTS5 探測即時失敗比安裝期失敗好排查
- 後續若需 async（FastAPI route 內查 DB），再評估 `aiosqlite`；目前 SSE heartbeat 不查 DB，`/healthz` 可 sync，YAGNI

**Alt 1 SQLAlchemy**：太重，schema 還沒長出來
**Alt 2 aiosqlite**：純 async 但 v1 只有 stub 不需要

### D4：FTS5 探測採「建臨時 in-memory FTS5 table」而非 `sqlite3.sqlite_version_info` 檢查
**選功能性探測**：
- Python 的 `sqlite3.sqlite_version_info` 顯示 SQLite 版本，但**不**告訴你 build 時有沒有 enable FTS5（Windows / 部分 distro 預編譯版本可能沒開）
- 在 in-memory connection 跑 `CREATE VIRTUAL TABLE _fts_probe USING fts5(x)` 失敗即 raise `RuntimeError("SQLite build lacks FTS5 ...")`
- 探測只跑一次（module-level cache 或 `get_connection` 第一次呼叫時）

**Alt** 跳過 FTS5 探測：等到 `external-connectors-and-cost` 寫 Trade Journal schema 才炸；本 change 提早 fail-fast

### D5：EventBus 實作 1:1 對齊 `docs/backend-eventbus.md` §2.2，不擴張介面
- `subscribe()` / `unsubscribe()` / `async emit()` 三方法
- `_subscribers: list[Queue[Event]]` 用 list 而非 set（`Queue` 不 hashable）
- `emit` 內 `put_nowait` 失敗時 silent skip（單一 subscriber 滿了不影響其他人，避免級聯阻塞）
- `bus = EventBus()` module-level 單例；後續 change 不另起實例（單例約定靠 import 約束）

**Alt 1 用 `anyio.create_memory_object_stream`**：可選但會綁 anyio，且 docs 已指定 `asyncio.Queue`
**Alt 2 用 redis pub/sub**：v1 限制 in-memory + 單 worker，redis 留 v2

### D6：`Event` dataclass 用 `frozen=True, slots=True`，timestamp 預設 TPE（UTC+8）
- `frozen=True`：emit 之後 subscriber 不能 mutate（避免一個 subscriber 修改後影響其他人）
- `slots=True`：每 event 內存 / 構造速度（高頻 emit 場景，雖然 v1 不會碰到）
- TPE timezone：`docs/backend-eventbus.md` §3.1 已固定台北時區；`datetime.now(TPE)` 不用 UTC 轉換，前端直接顯示

### D7：`/api/admin/events` 本 change 暫時 stub heartbeat 而**不**接 EventBus
**選暫時 stub**：
- EventBus 單例已存在，但本 change 不引入任何「真實」event 來源（沒有 hooks、沒有 services emit）
- 若直接接 EventBus，`curl /api/admin/events` 會永遠空白，無法驗收 SSE 通道存活
- heartbeat 是 SSE library 預設行為（`sse-starlette` 的 `ping=15`），把這個當作 stub 既驗證通道又無需自寫

**Alt** 接 EventBus 並在測試裡 emit：可行但 `tests/test_api.py` 需要跑 async client + 同時 emit；複雜度上升而本 change 只要驗收「通道有東西流」

### D8：`api` 子命令的旗標
- `--host` 預設 `127.0.0.1`（不是 `0.0.0.0`，避免本機 dev 暴露 LAN）
- `--port` 預設 `8000`
- `--reload / --no-reload`：dev 預設開 reload；明確 `--no-reload` 給 prod-like 跑
- 不加 `--workers`（單 worker v1 限制）

**Alt** `--host 0.0.0.0`：v1 是 localhost-only，預設綁 loopback；用戶要 LAN access 自行 `--host 0.0.0.0`

### D9：測試使用 `httpx.AsyncClient` + `ASGITransport(app=create_app())`，避免起真 uvicorn
- `pytest-asyncio` 加進 `[dependency-groups.dev]`（與既有 pytest 同層）
- `httpx` 由 fastapi 拉作 transitive，但顯式列為 dev dep 較穩
- SSE 測試 monkeypatch ping interval 為 ≤ 1 秒以加速；client 收到 1 筆 message 即 break

## Risks / Trade-offs

- **[Risk]** Windows 預編譯 Python 的 `sqlite3` 模組可能沒開 FTS5 → **Mitigation**：D4 的 FTS5 探測在啟動時 fail-fast；錯誤訊息提示用戶安裝有 FTS5 的 Python build（如 conda 版本），或改用 `pysqlite3-binary`
- **[Risk]** uvicorn `--reload` 在 Windows 下 `watchfiles` 可能 race condition → **Mitigation**：dev 預設開 reload，遇 race 再 `--no-reload`；不影響非 dev 路徑
- **[Risk]** `sse-starlette` keepalive 與測試斷言時序 → **Mitigation**：測試 monkeypatch 預設 ping interval 為 1 秒（fixture），且 client 收到 1 筆 message 即 break
- **[Risk]** `bus = EventBus()` module-level 單例 + pytest 多 test 共用 → **Mitigation**：`tests/test_api.py` 用 fixture 每測 `bus._subscribers.clear()`（或在 `test_eventbus.py` 內把測試聚焦在 round-trip 而非並發）
- **[Risk]** `frozen=True` Event 在 emit 後若 payload 含 mutable dict，subscriber 仍可 mutate dict 內容（dataclass frozen 不深凍） → **Mitigation**：本 change 接受此限制；後續 change 若需深 immutable 再改用 `MappingProxyType` wrap
- **[Trade-off]** 本 change 的 SSE 是 stub heartbeat，無法驗收「真實 event 從 emit 流到前端」 → 接受；該驗收屬於 Phase 1+ 的 change（有 emitter 後）；本 change 只驗收「通道存活」
- **[Trade-off]** `tests/test_api.py` 用 ASGITransport 不啟真 uvicorn → 不驗證 entrypoint 黏合（`ohmystock api` 真的能跑），靠 `tests/test_cli_api.py` 驗 CLI 旗標、靠人工 smoke test（task 5.x）驗 server 啟動

## Migration Plan

不適用（增量擴充，無 rollback target）。若整張 change 想撤銷：
1. 刪除 `src/ohmystock/api/app.py`、`src/ohmystock/api/db.py`、`src/ohmystock/eventbus/bus.py`、`src/ohmystock/eventbus/events.py`、`tests/test_api.py`、`tests/test_cli_api.py`
2. 從 `src/ohmystock/cli.py` 刪除 `api` 子命令
3. `tests/test_cli.py` 把斷言從 6 子命令改回 5 子命令
4. 從 `pyproject.toml` 刪除 `fastapi` / `uvicorn[standard]` / `sse-starlette`（與 dev `httpx` / `pytest-asyncio` 若於本 change 加）
5. `uv sync` 重整 lock
即可恢復 cli-skeleton 末態。

## Open Questions

- 是否要把 `OHMYSTOCK_DB_PATH` 在 `Settings` 從 `str` 窄化為 `Path`？→ 暫不；本 change `db.py` 內自行 `Path(settings.ohmystock_db_path).expanduser()`，型別窄化由實際使用面 change 決定
- SSE heartbeat interval 要不要做成 env var？→ 暫不；hard-code 15 秒，後續 `web-admin-bearer-auth` 若要調整再開 env
- 是否要在本 change 同時把 `web-admin/` 與 `web-public/` 目錄與 `packages/` 占位起來？→ 不；frontend repo 結構由 `web-admin-bearer-auth` 一次起齊（v3 #13 monorepo 決策），避免本 change scope creep
- `/healthz` 是否要 expose DB / EventBus 子系統狀態（如 `{"db":"ok","bus":"ok"}`）？→ 本 change 只回 `{"status":"ok","version":...}`；子系統狀態留給 `web-admin-bearer-auth` 加 `/healthz/full`
