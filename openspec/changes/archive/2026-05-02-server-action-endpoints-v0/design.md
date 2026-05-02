## Context

`backend-api-and-eventbus` capability 已備齊 FastAPI app factory（`api/app.py`）、SSE 通道（`/api/admin/events`）、SQLite 連線工廠（`api/db.get_connection()`）、EventBus 與 emitter（screener / decider / confirm-gate / journal / auto-execute 共 9 個 event_type）。但所有可被「觸發」的核心動作（screener、confirm、reject、sweep、exit）目前只有 Python API 與 CLI 入口。

Web-admin（Phase 4，預計 2026-08-11）的 18 頁工作台需要 React 端能直接呼叫這些動作。本 change 是把已存在的 Python 函式接成第一批 admin 端點，**不**改任何業務邏輯。

關鍵約束：

- Phase 1 不接 Bearer auth（`docs/auth-and-mask.md` 對 admin auth 的設計留給後續 change `web-admin-bearer-auth`）
- v0 broker 走 `FakePaperBroker`（Shioaji 模擬倉接入是 Phase 2 後續 change）
- SQLite WAL 已啟用，per-request connection 開關足以避免 lock 競爭
- 既有 `screen_universe()` 已自帶 ok/error envelope（與 `live-providers/spec.md` 對齊）；confirm-gate 與 exit-engine 走 raise/return 模式，本 change 在 router 層轉成統一 envelope

## Goals / Non-Goals

**Goals:**

- 6 個 admin write 端點 ship：`POST /api/admin/screener/run`、`GET /api/admin/confirm-gate/pending`、`POST /api/admin/confirm-gate/{confirm,reject,sweep-expired}`、`POST /api/admin/exit-engine/run`
- 統一 JSON 契約：所有 endpoint 回 `{ok: true, data: ...}` 或 `{ok: false, error: {code, message}}`，配合既有 SSE 廣播
- 每個 endpoint 自開自關 `sqlite3.Connection`（透過 `Depends(get_db)` 或 try/finally）
- 端點呼叫的核心函式 SHALL 與 CLI / 測試使用的同一函式（單一實作來源），不另寫 router-only 邏輯
- HTTP status code mapping：成功 200；input 驗證失敗 400；資源不存在 404；business rule 違反（not_pending / payload_invalid）409；上游 / DB 錯誤 5xx
- 既有 EventBus emitter 不需動：`screen_universe` / `confirm` / `reject` / `sweep_expired` 內已 `safe_emit`，路由層只負責 HTTP wrap
- 100% 端點測試覆蓋（pytest + `httpx.AsyncClient` / `TestClient`）

**Non-Goals:**

- Bearer token auth（→ `web-admin-bearer-auth`）
- Public masked SSE / 公網 endpoints（→ `web-public-pixel-mvp`）
- 觸發 decider entry pipeline（POST /api/admin/decider/decide）— decider 需 `EntryDecisionInput` payload，依賴 Phase 2B swarm wiring，獨立 change 處理
- 直接觸發 auto-execute（auto-execute 由 decider pipeline 內呼叫，UI 不該繞過 confirm gate）
- Journal 全表查詢、FTS5 search、分頁（→ `journal-query-endpoints`）
- WebSocket / RPC / GraphQL；只用 REST + SSE
- Rate limiting / quota / 同 user 防雙擊（v0 假設 single-user localhost，Phase 4.5 之前不需要）
- Idempotency keys（同上）

## Decisions

### Decision 1：每個 endpoint 自開自關 `sqlite3.Connection`，不共享 module-level conn

採 FastAPI dependency `get_db()` 模式，handler 內 `with closing(get_connection()) as conn:` 或等價 try/finally。

**Why：**
- SQLite WAL 允許多 readers + 1 writer；per-request 開連線最安全、最簡單，避免 thread-local / async-local 的 connection 共享坑
- 連線開銷 < 1 ms；admin endpoint 流量極低（單人本機），不需要 connection pool
- 與既有 CLI `_open_db()` / 既有 `evaluate_open_positions` 測試慣例一致

**Alternative considered：** Module-level singleton conn — 拒絕，因為 SQLite connection 不是 thread-safe，FastAPI 的 ASGI worker 在不同 task 裡共用會踩雷。

### Decision 2：統一 success / error envelope 為 `{ok, data, error}`

```jsonc
// success
{"ok": true, "data": {...}}

// error
{"ok": false, "error": {"code": "<machine_code>", "message": "<human msg>"}}
```

對應 `screen_universe` 既有 envelope（已含 `ok / data / error`），confirm-gate / exit-engine 在 router 層 catch → 轉。

**Mapping：**

| Source | code 來源 | HTTP status |
|---|---|---|
| screener `code=invalid_input` | 既有 envelope | 400 |
| screener `code=data_unavailable` | 既有 envelope | 503 |
| screener `code=upstream_error` | 既有 envelope | 502 |
| `ConfirmGateError("not_found", ...)` | `exc.code` | 404 |
| `ConfirmGateError("not_pending", ...)` | `exc.code` | 409 |
| `ConfirmGateError("payload_invalid", ...)` | `exc.code` | 409 |
| `ConfirmGateError("broker_failed", ...)` | `exc.code` | 502 |
| `ExitEngineError("market_data_unavailable", ...)` | `exc.code` | 503 |
| `ValueError`（input 驗證）| `"invalid_input"` | 400 |
| 任何 `Exception`（fallback）| `"internal_error"` | 500 |

**Why：** 與 `live-providers/spec.md` 的 retriable code 哲學一致；admin UI 拿 `error.code` 做 banner 文案 / retry 邏輯，不依賴 message text。

**Alternative considered：** RFC 7807 Problem Details — 拒絕，screener 既有 envelope 已落地、改寫成本不值得。

### Decision 3：每個 sub-domain 一個 router 檔，最後在 `app.py` `include_router`

```
src/ohmystock/api/
├── app.py                # create_app() 註冊全部
├── db.py                 # 既有
├── routes/
│   ├── __init__.py
│   ├── _envelope.py      # to_error_envelope(exc) / to_success_envelope(data)
│   ├── _deps.py          # Depends(get_db) / get_settings
│   ├── screener.py       # POST /api/admin/screener/run
│   ├── confirm_gate.py   # GET /pending + 3 POST
│   └── exit_engine.py    # POST /api/admin/exit-engine/run
```

**Why：** 既有 `app.py` 已 100 lines，再塞 6 個 endpoint 會破 500 lines。User CLAUDE.md 規則「單檔 200–400 lines 典型」也吻合。

**Alternative considered：** 全部塞 `app.py` — 拒絕，難測試、難讀。

### Decision 4：Confirm endpoint 在 router 內構造 `FakePaperBroker`，不從 settings 注入

```python
# routes/confirm_gate.py
@router.post("/api/admin/confirm-gate/confirm")
def confirm_endpoint(req: ConfirmRequest, conn = Depends(get_db), settings = Depends(get_settings)):
    broker = FakePaperBroker(clock=system_clock)
    result = confirm(conn, decision_id=req.decision_id, broker=broker, ...)
```

**Why：** v0 不接 Shioaji；FakePaperBroker 是 deterministic、無外部依賴。Phase 2 接 Shioaji 時再改 router 為 `Depends(get_broker)` 並由 settings 切換。

**Alternative considered：** Module-level broker singleton — 拒絕，後續難換實作；本 change 範圍內不引入。

### Decision 5：Pydantic v2 request models，inline 定義在 router 檔

各 router 檔頂部定義 `class ScreenerRunRequest(BaseModel)` 等；不集中到 `_schemas.py`，避免 cross-router 耦合。Response 用 `dict[str, Any]`（envelope 不適合做 strict response model，因為 `data` shape 隨 endpoint 變）。

**Why：** Pydantic 已是 FastAPI 的內建依賴。Inline 模型 < 30 行，不值得抽公用檔。

### Decision 6：Sweep / list-pending 的 `timeout_minutes` 預設讀 settings

若 request 沒帶 `timeout_minutes`，從 `Settings.ohmystock_confirm_timeout_minutes`（預設 30 分）取值。

**Why：** CLI 既有行為一致；UI 通常不該知道 timeout 數字，由後端提供 default。

### Decision 7：Exit-engine endpoint 走同步、回傳全部 `ExitResult` list

Body：`{asof_date?: "YYYY-MM-DD", symbol?: "2330"}`；省略 `asof_date` 預設 today (TPE)；省略 `symbol` 評估全部 confirmed。回 `{ok: true, data: {results: [...], evaluated_count: int, closed_count: int, held_count: int}}`。失敗 symbol 走 `ExitEngineError("market_data_unavailable")` → 503，但 envelope 含 `failed_symbols` 細節。

**Why：** 與 `evaluate_open_positions` 既有契約 1:1 對齊；admin UI 一次拿到全部結果即可，不需要分批。

### Decision 8：所有 endpoint 維持無認證（no Bearer）

每個 endpoint scenario SHALL 明確驗證「不帶 Authorization header 仍 200/4xx/5xx」，避免後續 auth change 不小心把 v0 端點全部破壞。

**Why：** 與 `backend-api-and-eventbus` 對 `/healthz` 與 `/api/admin/events` 的處理一致；Bearer auth 是獨立 capability，不混在本 change。

## Risks / Trade-offs

- **[Risk] FakePaperBroker fill 是 deterministic，confirm 端點回的 fill price 只是 entry payload `current_price`，不會反映真實滑價** → Mitigation：v0 文件清楚標示「paper, fake broker」；Phase 2 接 Shioaji 時換 broker 不換契約。
- **[Risk] 沒 auth 期間 admin endpoint 公開於本機 0.0.0.0** → Mitigation：本 change 只支援 `localhost` / `127.0.0.1` 綁定（uvicorn 啟動 flag 由 README / docs 規定）；`web-admin-bearer-auth` change 上線前不開 LAN / Cloudflare Tunnel。已在 proposal Out of scope 註明。
- **[Risk] Per-request `get_connection()` 重新探測 FTS5 → 性能** → Mitigation：FTS5 探測只在「首次呼叫」做，已有 module-level cache；per-request 只是新開 sqlite3 connection（< 1 ms）。
- **[Risk] Sweep 或 exit-engine 跑久阻塞 event loop** → Mitigation：兩者都跑 SQLite read-write，現實規模 << 1 s（pending 數量單位數、open positions 個位數至兩位數）。若實測超 500 ms，後續 change 改 `run_in_threadpool`。本 change 不預先優化。
- **[Risk] Endpoint route 跟未來 `/api/public/*` 命名混淆** → Mitigation：本 change 只用 `/api/admin/*` 前綴；公網端點完全 disjoint，spec 內顯式禁止 router 跨命名。
- **[Trade-off] 不接 idempotency / 雙擊保護** → 接受。單人本機，confirm 同一筆會撞 `not_pending` raise → 409，UI 看到後 refresh pending list 即可。
