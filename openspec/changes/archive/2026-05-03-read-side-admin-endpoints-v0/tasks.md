## 1. Pydantic response models + shared helpers

- [x] 1.1 在 `src/ohmystock/api/routes/journal.py` 新增 module（含 `from __future__ import annotations`、模組 docstring 引用 `openspec/specs/admin-read-endpoints/spec.md`）。
- [x] 1.2 定義 Pydantic v2 `BaseModel`：`JournalRowItem`（id, decision_id, kind, symbol, created_at, payload: dict）、`JournalRowsData`（items, total, limit, offset, has_more）、`DecisionDetailData`（decision_id, rows: list[JournalRowItem]）。所有欄位皆顯式 type-annotated，`payload` 為 `dict[str, Any]`。
- [x] 1.3 在同檔案內新增 helper `_parse_payload(payload_json: str) -> dict[str, Any]`：以 `json.loads` 解析；解析失敗時 raise `ValueError(f"corrupt payload_json id={...}")`（落入 envelope 的 400 `invalid_input`）。
- [x] 1.4 在同檔案內新增 helper `_validate_kind(kind: str | None) -> str | None`：若 `kind not in {"entry","exit","reject","expire","auto_execute_audit"}` 且非 None → raise `ValueError("invalid kind")`。
- [x] 1.5 在同檔案內新增 helper `_validate_date(s: str | None, name: str) -> str | None`：以 `datetime.strptime(s, "%Y-%m-%d")` 嚴格驗證；不合法 → `ValueError(f"invalid {name}")`。
- [x] 1.6 新增 `tests/test_api_journal_endpoints.py`：先寫一個 import smoke test 確認 module 可被 import（防止打字錯）。

## 2. GET /api/admin/journal/rows

- [x] 2.1 在 `routes/journal.py` 建立 `router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])`。
- [x] 2.2 實作 `@router.get("/journal/rows")` handler，簽章接受 `kind, symbol, date_from, date_to, limit, offset` 全為 `Query(default=...)`。
- [x] 2.3 在 handler 內：呼叫 `_validate_kind`、`_validate_date(date_from, "date_from")`、`_validate_date(date_to, "date_to")`；若 `date_from is not None and date_to is not None and date_from > date_to` → `raise ValueError("date_from > date_to")`。
- [x] 2.4 處理 limit / offset：`limit <= 0` → `ValueError("limit must be positive")`；`offset < 0` → `ValueError("offset must be non-negative")`；`limit = min(limit, 500)`（silent clamp）。
- [x] 2.5 動態組裝 `WHERE` clause + parameter list（避免 string interpolation；只 append `kind = ?`、`symbol = ?`、`substr(created_at,1,10) >= ?`、`substr(created_at,1,10) <= ?`）。
- [x] 2.6 同 connection 執行 `COUNT(*)` 與 `SELECT ... ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?` 兩個查詢，組成 `JournalRowsData` 並回傳 `to_success(model.model_dump(mode="json"))`。
- [x] 2.7 包進統一 `try/except` → `map_exception_to_envelope`，與 `confirm_gate.py` 一致。
- [x] 2.8 在 `tests/test_api_journal_endpoints.py` 寫覆蓋以下 spec scenarios 的 8 個 test：空表回 items=[]、3 筆排序、kind 過濾、不合法 kind 400、limit>500 clamp、limit=0 → 400、offset 翻頁 + has_more、date_from>date_to → 400、payload 還原為 nested dict。

## 3. GET /api/admin/journal/decisions/{decision_id}

- [x] 3.1 在同 `routes/journal.py` 內 `@router.get("/journal/decisions/{decision_id}")` 接受 path param `decision_id: str`。
- [x] 3.2 實作 SQL `SELECT ... FROM journal_entries WHERE decision_id = ? ORDER BY created_at ASC, id ASC`，無 row → `JSONResponse(status_code=404, content=to_error("not_found", f"decision_id {decision_id} not found"))`。
- [x] 3.3 序列化為 `DecisionDetailData` 並回 `to_success(...)`。
- [x] 3.4 在 `tests/test_api_journal_endpoints.py` 加 3 個 scenarios：不存在的 id → 404、單一 entry rows 長度 1、entry+exit+audit 三筆按 ASC 排序。

## 4. GET /api/admin/positions/open

- [x] 4.1 新增 `src/ohmystock/api/routes/positions.py` module（含 docstring + `from __future__ import annotations`）。
- [x] 4.2 定義 Pydantic `PositionItem`（decision_id, symbol, sector, entry_price, qty_lots, entry_ts, hold_days, stop_loss: float | None, t1_target: float | None, time_stop_date: str | None）+ `PositionsOpenData`（items, asof_iso, count）。
- [x] 4.3 建立 `router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])`、`@router.get("/positions/open")` handler。
- [x] 4.4 在 handler 內：取 `tpe = ZoneInfo("Asia/Taipei")`、`now = datetime.now(tpe)`、`now_iso = now.isoformat()`、`today = now.date()`。
- [x] 4.5 呼叫 `from ohmystock.journal.repository import open_positions` 並執行 `open_positions(conn, asof=now_iso)` 拿 `list[OpenPosition]`。
- [x] 4.6 若 candidates 非空：bulk fetch payloads — `placeholders = ",".join("?" * len(decision_ids))`、`SELECT decision_id, payload_json FROM journal_entries WHERE kind='entry' AND decision_id IN ({placeholders})`，將結果 `parse → dict` 並 keyed 在 `dict[decision_id]`。
- [x] 4.7 把每筆 `OpenPosition` 序列化：`hold_days = max(0, (today - date.fromisoformat(p.entry_ts[:10])).days)`、payload dict `.get(...)` 取 `stop_loss / t1_target / time_stop_date`，缺則 None。
- [x] 4.8 回 `to_success(PositionsOpenData(items=..., asof_iso=now_iso, count=len(items)).model_dump(mode="json"))`。
- [x] 4.9 包 `try/except` → `map_exception_to_envelope`。
- [x] 4.10 新增 `tests/test_api_positions_endpoint.py` 覆蓋 5 個 scenarios：empty → items=[]；filled+open → 含 stop_loss/t1_target；payload 缺 stop_loss → null；exit 後不列為 open；pending_confirm 不列為 open。
- [x] 4.11 在 `app.py` `include_router(positions_router)`。

## 5. GET /api/admin/stats/today

- [x] 5.1 新增 `src/ohmystock/api/routes/stats.py`（docstring + `from __future__ import annotations`）。
- [x] 5.2 定義 Pydantic `StatsTodayData`（asof_date, decisions_made, entries_pending, entries_filled, rejects, expires, auto_execute_audits — 全為 int）。
- [x] 5.3 建立 `router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])`、`@router.get("/stats/today")` handler。
- [x] 5.4 在 handler 內取 `today_str = datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()`。
- [x] 5.5 執行單一 SQL：6 個 `COALESCE(SUM(CASE WHEN ...), 0)` 配 `WHERE substr(created_at,1,10) = ?`（design Decision 6 的範本）。
- [x] 5.6 序列化為 `StatsTodayData` 並 `to_success(model.model_dump(mode="json"))`。
- [x] 5.7 包 `try/except` → `map_exception_to_envelope`。
- [x] 5.8 新增 `tests/test_api_stats_endpoint.py` 覆蓋 5 個 scenarios：空表全 0、1 pending+1 filled+1 reject、昨日 row 不計、跨午夜邊界、auto_execute_audit 計入專屬計數器。
- [x] 5.9 在 `app.py` `include_router(stats_router)`。

## 6. App 整合與跨端點測試

- [x] 6.1 在 `src/ohmystock/api/app.py` `include_router(journal_router)`、`include_router(positions_router)`、`include_router(stats_router)`（已於 4.11 / 5.9 部分完成；本步驟確認三者都加入並排序在既有 router 之後）。
- [x] 6.2 在 `tests/test_api_journal_endpoints.py` 加跨端點 scenario：缺 Authorization → 401 `auth_missing`（覆蓋 spec §1）對所有 4 個 path（含 `decisions/x`）。
- [x] 6.3 在 `tests/test_api_positions_endpoint.py` 加 scenario：spy on `ohmystock.api.db.get_connection`，連續兩次呼叫拿到不同 connection 物件（覆蓋 spec §1 per-request connection 不變式）。
- [x] 6.4 在 `tests/test_api_stats_endpoint.py` 加 scenario：monkeypatch handler raise `RuntimeError("/Users/secret SELECT")`、spy on `Connection.close`，驗證 500 `internal_error`、message 不含 `/Users/` 與 `SELECT`、close 被呼叫至少 1 次（覆蓋 spec §1 redaction + close-on-raise）。
- [x] 6.5 加 smoke scenario：對全部 4 個 path（journal/rows、journal/decisions/x、positions/open、stats/today）發 GET request，確認 status code 不是 FastAPI default route-not-found 404；body 是合法 JSON 並含 `"ok"` key（覆蓋 spec §「4 個 router 註冊」requirement）。

## 7. 文件與 commit

- [x] 7.1 跑 `pytest tests/test_api_journal_endpoints.py tests/test_api_positions_endpoint.py tests/test_api_stats_endpoint.py -q` 全部通過、無 warning。
- [x] 7.2 跑全套 `pytest -q` 確認無 regression（既有 6 個寫端點測試與 auth/eventbus/journal 測試應全綠）。
- [x] 7.3 跑 `openspec validate read-side-admin-endpoints-v0 --strict`，無錯。
- [x] 7.4 在 `CLAUDE.md` §5「公式 / Schema 唯一權威表」附近新增一列指向新 capability：`admin-read-endpoints — 4 個 GET 端點（journal/rows、journal/decisions/{id}、positions/open、stats/today）` → `openspec/specs/admin-read-endpoints/spec.md`（archive 後）+ `src/ohmystock/api/routes/{journal,positions,stats}.py`。
- [x] 7.5 git commit、訊息格式 `feat(api): admin read endpoints v0 — journal rows/decisions, positions/open, stats/today`，body 列出 4 個端點與 spec 路徑，**不**push（僅 commit；push 由使用者決定）。
