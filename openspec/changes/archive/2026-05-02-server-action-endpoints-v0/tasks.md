## 1. Scaffold router package + shared envelope/deps

- [x] 1.1 Create `src/ohmystock/api/routes/__init__.py`（empty package marker）
- [x] 1.2 Create `src/ohmystock/api/routes/_envelope.py` exposing `to_success(data: dict) -> dict`、`to_error(code: str, message: str, **extra) -> dict`、`map_exception_to_envelope(exc: Exception) -> tuple[int, dict]`（per design.md Decision 2 mapping table）
- [x] 1.3 Write `tests/test_api_envelope.py` — unit tests covering all 10 mapping table rows + the "no stack trace / no abs path / no SQL" guarantees from spec §「端點不洩漏內部路徑或 settings 值」
- [x] 1.4 Create `src/ohmystock/api/routes/_deps.py` exposing `get_db()` FastAPI dependency that yields a `sqlite3.Connection` from `ohmystock.api.db.get_connection()` and closes in `finally`; also `get_settings()` returning `ohmystock.config.Settings()`
- [x] 1.5 Write `tests/test_api_deps.py` — verify `get_db` yields a fresh connection per call, closes on success, closes on handler raise

## 2. Screener endpoint

- [x] 2.1 Write `tests/test_api_screener_endpoint.py` covering all spec scenarios for `POST /api/admin/screener/run`:
  - success path (200 + asof_date_used + candidates + elapsed_ms)
  - invalid universe (400 invalid_input)
  - SSE consumer receives `screener_started` + `screener_completed`（reuse pattern from `tests/test_admin_sse_subscribes.py`）
  - no Authorization header still works
- [x] 2.2 Implement `src/ohmystock/api/routes/screener.py` — APIRouter with `POST /api/admin/screener/run`、Pydantic `ScreenerRunRequest` body model、call `screen_universe` and translate envelope via `_envelope.py`
- [x] 2.3 Wire router into `src/ohmystock/api/app.py` via `app.include_router(screener_router)`
- [x] 2.4 Run `pytest tests/test_api_screener_endpoint.py` — all green

## 3. Confirm-gate endpoints

- [x] 3.1 Write `tests/test_api_confirm_gate_endpoints.py` covering spec scenarios for all 4 endpoints:
  - `GET /api/admin/confirm-gate/pending`：empty list、one pending row serialized、`timeout_minutes=0` → 400
  - `POST .../confirm`：success（fill + qty）、not_found 404、not_pending 409、empty user 400、SSE `order_sent`、no Authorization header still works
  - `POST .../reject`：success（reject_row_id）、empty reason 400、not_pending 409
  - `POST .../sweep-expired`：no expired→empty list、one expired→swept、`timeout_minutes=-1` → 400
- [x] 3.2 Implement `src/ohmystock/api/routes/confirm_gate.py` — APIRouter with the 4 endpoints; inline Pydantic models for `ConfirmRequest`、`RejectRequest`、`SweepExpiredRequest`; constructs `FakePaperBroker(clock=system_clock)` inside `confirm` handler per design Decision 4; reads `ohmystock_default_capital_twd` / `ohmystock_confirm_timeout_minutes` from settings
- [x] 3.3 Wire router into `src/ohmystock/api/app.py`
- [x] 3.4 Run `pytest tests/test_api_confirm_gate_endpoints.py` — all green

## 4. Exit-engine endpoint

- [x] 4.1 Write `tests/test_api_exit_engine_endpoint.py` covering spec scenarios for `POST /api/admin/exit-engine/run`:
  - empty journal → evaluated_count=0
  - confirmed row hits stop_loss → closed + decision serialized
  - market_data missing → 503 + failed_symbols
  - invalid asof_date → 400
  - symbol filter limits scope
- [x] 4.2 Implement `src/ohmystock/api/routes/exit_engine.py` — APIRouter with `POST /api/admin/exit-engine/run`; inline Pydantic `ExitEngineRunRequest`；handler 構造 default `MarketDataLookup` 實作（v0：包既有 market data cache lookup function，可由 `Depends` override）; serializes `ExitResult` list to dicts
- [x] 4.3 Wire router into `src/ohmystock/api/app.py`
- [x] 4.4 Run `pytest tests/test_api_exit_engine_endpoint.py` — all green

## 5. Cross-cutting tests + docs

- [x] 5.1 Write `tests/test_api_envelope_security.py` — verify error responses across all endpoints don't leak abs paths（`/Users/`、`/home/`、`C:\\`）、SQL keywords（`SELECT`、`INSERT`）、tracebacks（`Traceback`、`File "`）；use monkeypatch to inject realistic failure modes
- [x] 5.2 Write `tests/test_api_no_auth.py` — for each of the 6 new endpoints, verify request without `Authorization` header returns non-401/403 status
- [x] 5.3 Update `docs/backend-eventbus.md` §5 SSE Endpoint API table — add a new sub-section listing the 6 admin action endpoints with method/path/body/responses
- [x] 5.4 Update `CLAUDE.md` §5 唯一權威表 — add row referencing `openspec/specs/server-action-endpoints/spec.md` (post-archive) + `src/ohmystock/api/routes/`
- [x] 5.5 Run full suite `pytest tests/test_api_*.py` — all green (73/73); full project suite green (807 passed). ruff/mypy not configured in this repo's pyproject.toml — skipped (separate tooling setup decision).

## 6. OpenSpec validation + archive prep

- [x] 6.1 Run `openspec validate server-action-endpoints-v0 --strict` — ensure proposal/design/specs/tasks parse and cross-reference correctly
- [x] 6.2 Confirm `openspec status --change server-action-endpoints-v0 --json` reports `isComplete: true` ready for `/opsx:archive`
