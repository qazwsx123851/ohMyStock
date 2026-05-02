## Why

到目前為止 FastAPI app 只有 `GET /healthz` 與 `GET /api/admin/events`（SSE）；admin UI 要觸發任何「動作」（跑 screener、confirm 一筆 pending、跑出場評估）只能透過 CLI 或直接 import Python 函式。Phase 4 的 web-admin（18 頁工作台）需要一組可從 React 直接呼叫的 HTTP write 端點，否則整個 admin UI 無法啟動。

本次目標是把已存在的核心動作（`screen_universe` / `list_pending` / `confirm` / `reject` / `sweep_expired` / `evaluate_open_positions`）一次包成 v0 admin action endpoints，把 EventBus emitters 已就位的 read-side 補上對應的 write-side。

## What Changes

- 新增 `POST /api/admin/screener/run` — 包 `screener.universe.screen_universe()`，body 直接帶 `universe / custom_symbols / filters / asof_date`
- 新增 `GET /api/admin/confirm-gate/pending` — 包 `safety.confirm_gate.list_pending()`，回傳所有 pending_confirm 加 TTL 資訊
- 新增 `POST /api/admin/confirm-gate/confirm` — 包 `safety.confirm_gate.confirm()`，使用 `FakePaperBroker` + `Settings.ohmystock_default_capital_twd`（v0 不接 Shioaji）
- 新增 `POST /api/admin/confirm-gate/reject` — 包 `safety.confirm_gate.reject()`
- 新增 `POST /api/admin/confirm-gate/sweep-expired` — 包 `safety.confirm_gate.sweep_expired()`，timeout 預設讀 `Settings.ohmystock_confirm_timeout_minutes`
- 新增 `POST /api/admin/exit-engine/run` — 包 `exit_engine.evaluator.evaluate_open_positions()`，body 帶 `asof_date?` 與 `symbol?`
- 統一 error envelope（`{"ok": false, "error": {"code", "message"}}`），把 `ConfirmGateError.code` / `ExitEngineError.code` / `screener` 自有 envelope 一致化
- 每個請求 SHALL 自開自關 `sqlite3.Connection`（透過 `api.db.get_connection()`），不共享 process-wide connection
- 全部端點維持**無認證**（Bearer auth 由後續 change `web-admin-bearer-auth` 在 Phase 4 後段補上）

## Capabilities

### New Capabilities

- `server-action-endpoints`: Admin UI write-side HTTP 端點 — wraps screener / confirm-gate / exit-engine 的核心函式，提供 v0 JSON 契約、統一 error envelope、per-request DB 連線生命週期。

### Modified Capabilities

（無需修改既有 capability。`backend-api-and-eventbus` 只負責 app factory / SSE / DB / EventBus 骨架；本 change 屬全新 capability，不動既有 Requirements。）

## Impact

- **Code**：`src/ohmystock/api/app.py` 註冊 6 個新 route；新增 `src/ohmystock/api/routes/screener.py`、`api/routes/confirm_gate.py`、`api/routes/exit_engine.py`（每個 router 一檔）
- **Schema**：新增 Pydantic request/response models（`api/routes/_schemas.py` 或同檔內 inline）；不改 SQLite schema
- **Tests**：新增 `tests/test_api_screener_endpoint.py`、`tests/test_api_confirm_gate_endpoints.py`、`tests/test_api_exit_engine_endpoint.py`，沿用既有 `TestClient` 模式
- **Dependencies**：無新增；FastAPI / pydantic / sqlite3 / sse-starlette 都已在
- **Docs**：`docs/backend-eventbus.md` §5 加 endpoint 表；`CLAUDE.md` §5 唯一權威表加一列指向新 spec
- **Out of scope（明確留給後續 change）**：
  - Bearer auth（→ `web-admin-bearer-auth`，Phase 4 後段）
  - `/api/public/*` masked endpoints（→ `web-public-pixel-mvp`，Phase 4.5）
  - 觸發 decider entry 的端點（需 swarm wiring，→ Phase 2B/3 後續 change）
  - Auto-execute 觸發端點（auto-execute 由 decider pipeline 內部呼叫，UI 不直接觸發）
  - Journal 全表查詢 / 分頁 / FTS5 search（→ 獨立 change `journal-query-endpoints`）
