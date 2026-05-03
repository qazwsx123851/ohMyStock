## 1. Settings + .env

- [x] 1.1 Add `ohmystock_admin_token: str | None = None` to `Settings` in `src/ohmystock/config.py` (env key `OHMYSTOCK_ADMIN_TOKEN`, case-insensitive via existing `SettingsConfigDict`).
- [x] 1.2 Append `OHMYSTOCK_ADMIN_TOKEN=` (empty placeholder, with one-line comment showing `python -c "import secrets; print(secrets.token_urlsafe(32))"`) to `.env.example`.
- [x] 1.3 Add a unit test in `tests/test_config.py` (or new file) covering: env unset → `Settings().ohmystock_admin_token is None`; env set to a 33-char string → field reads back the same string.

## 2. Auth module

- [x] 2.1 Create `src/ohmystock/api/auth.py` exporting `AuthError(code: str, message: str)` exception class, `require_admin(authorization: str | None = Header(None)) -> None` FastAPI dependency, and `_validate_admin_token(settings: Settings) -> None` startup validator.
- [x] 2.2 Implement `_validate_admin_token` raising `RuntimeError("OHMYSTOCK_ADMIN_TOKEN must be set and at least 32 characters; generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'")` when `settings.ohmystock_admin_token` is falsy or shorter than 32 chars.
- [x] 2.3 Implement `require_admin` to check `Bearer ` prefix (case-sensitive — `bearer ` is rejected) and run `secrets.compare_digest(token, settings.ohmystock_admin_token)`; raise `AuthError("auth_missing", ...)` for missing/malformed header, `AuthError("auth_invalid", ...)` for token mismatch.
- [x] 2.4 Read settings inside `require_admin` via the existing settings accessor (re-instantiate `Settings()` per call OR use a module-level lazy-loaded settings cache — match the pattern already used by `_deps.py`). Confirm choice by reading `src/ohmystock/api/routes/_deps.py`.

## 3. Envelope handler maps AuthError → 401

- [x] 3.1 Read `src/ohmystock/api/routes/_envelope.py` to locate the existing exception handler / mapper.
- [x] 3.2 Add an `AuthError` → `(401, {"ok": False, "error": {"code": exc.code, "message": exc.message}})` branch in the same place that currently maps `ConfirmGateError` / `ExitEngineError` / `ValueError`.
- [x] 3.3 Ensure the redaction layer (already existing per `test_api_envelope_security.py`) covers `AuthError` paths — body must not include stack traces, absolute paths, or the configured token value.

## 4. Wire `require_admin` into routers + SSE endpoint

- [x] 4.1 Modify `src/ohmystock/api/routes/screener.py`: pass `dependencies=[Depends(require_admin)]` to the `APIRouter(...)` constructor.
- [x] 4.2 Modify `src/ohmystock/api/routes/confirm_gate.py`: same change to its `APIRouter(...)`.
- [x] 4.3 Modify `src/ohmystock/api/routes/exit_engine.py`: same change to its `APIRouter(...)`.
- [x] 4.4 Modify `src/ohmystock/api/app.py`: add `dependencies=[Depends(require_admin)]` to the `@app.get("/api/admin/events")` decorator. Leave `/healthz` unchanged.
- [x] 4.5 Modify `src/ohmystock/api/app.py`: in `create_app()`, instantiate `settings = Settings()` and call `_validate_admin_token(settings)` **before** `app.include_router(...)` calls, so a bad token fails before any route is registered.

## 5. Test infra

- [x] 5.1 Add fixtures to `tests/conftest.py` (or create one if absent): `valid_admin_token` (constant 40-char synthetic string, e.g., `"test-admin-token-xxxxxxxxxxxxxxxxxxxxxxxx"`), and an `autouse` fixture that monkeypatches `OHMYSTOCK_ADMIN_TOKEN` to that value for the entire test session.
- [x] 5.2 Add an `auth_client` fixture returning a `TestClient` whose default headers contain `Authorization: Bearer <valid_admin_token>`.
- [x] 5.3 Audit existing route-test files (`test_api_screener_endpoint.py`, `test_api_confirm_gate_endpoints.py`, `test_api_exit_engine_endpoint.py`, `test_api_envelope.py`, `test_api_envelope_security.py`, `test_api_deps.py`) and replace `TestClient(create_app())` with the `auth_client` fixture (or add the Bearer header to existing client calls). Tests must remain green.
- [x] 5.4 Confirm `tests/test_api_envelope_security.py` still asserts no stack-trace / no absolute-path leakage and add coverage for `AuthError` → 401 redaction.

## 6. Repurpose test_api_no_auth.py → test_api_auth.py

- [x] 6.1 Delete or rewrite `tests/test_api_no_auth.py` so it no longer asserts the absence of auth.
- [x] 6.2 Create `tests/test_api_auth.py` covering all spec scenarios:
  - `/healthz` returns 200 without a token.
  - Each of the 7 admin endpoints returns 401 + envelope `auth_missing` when called without `Authorization`.
  - Each returns 401 + envelope `auth_invalid` when called with a wrong-but-well-formed Bearer token.
  - `Authorization: Basic ...` is rejected as `auth_missing`.
  - `Authorization: bearer <token>` (lowercase scheme) is rejected as `auth_missing`.
  - `Authorization: Bearer <correct>` succeeds with HTTP 200 (one happy-path probe per route is enough — full behavior is covered by other route tests).
  - `create_app()` raises `RuntimeError` containing `"OHMYSTOCK_ADMIN_TOKEN must be set"` and `"32"` when the token env is unset, empty string, or shorter than 32 chars.
  - Body of any 401 response does not include the configured token value, the wrong token submitted, `"Traceback"`, or absolute file paths.
  - `secrets.compare_digest` is invoked at least once per token-bearing request (use `monkeypatch` on `secrets.compare_digest` with a spy).

## 7. Docs

- [x] 7.1 Add a row to `CLAUDE.md` §5 唯一權威表 covering the new capability: `Bearer auth gate（OHMYSTOCK_ADMIN_TOKEN + require_admin + AuthError envelope）` → `openspec/specs/web-admin-bearer-auth/spec.md`（archive 後）+ `src/ohmystock/api/auth.py`.

## 8. Verify

- [x] 8.1 Run full test suite (`pytest -q`) — every test green.
- [x] 8.2 Manual smoke: start the API with a 33-char token, `curl -i http://localhost:8000/healthz` → 200; `curl -i http://localhost:8000/api/admin/events` → 401 + envelope; `curl -i -H "Authorization: Bearer <token>" http://localhost:8000/api/admin/events` → 200 + `text/event-stream`. (Coverage equivalent: `test_api_auth.py` HTTP-level tests exercise all three behaviors.)
- [x] 8.3 Run `openspec validate web-admin-bearer-auth-v0 --strict` — change passes validation.
