## Context

The FastAPI app exposes `/healthz`, `/api/admin/events` (SSE), and six admin write endpoints under `/api/admin/{screener,confirm-gate,exit-engine}/*`. All admin endpoints today are no-auth — both `server-action-endpoints` and `backend-api-and-eventbus` specs explicitly defer Bearer auth to **this** change. `docs/auth-and-mask.md` §2.2 already documents the chosen scheme: a single `OHMYSTOCK_ADMIN_TOKEN` stored as an env var, compared with `secrets.compare_digest`, fail-fast on startup if unset or shorter than 32 chars.

Current callers of admin routes: `tests/test_api_*.py` (TestClient, no auth header), the future `web-admin/` SPA (will read `VITE_ADMIN_TOKEN` from `.env.local`). No production caller exists today, so the breaking change is internal-only.

## Goals / Non-Goals

**Goals:**
- Single Bearer-token gate covers every `/api/admin/*` route — REST and SSE.
- Endpoint behavior (envelope, status mapping, redaction, per-request DB connection) stays identical for authorized callers.
- Startup validation makes "ran the API without setting the token" impossible to ship.
- Constant-time comparison (no timing oracle).
- 401 errors use the **same envelope** the rest of the admin routes already emit.
- Test infra layers cleanly: a single fixture mints a valid token + injects it.

**Non-Goals:**
- Multi-user auth, JWT, OAuth, RBAC, refresh tokens. Single user only (per v3 decision #6 + auth-and-mask.md §2.3 v2 path).
- Public endpoints (`/api/public/*`) — not in this capability.
- Mask serializer — handled by `web-public-mask-v0` later.
- Audit log of who-called-what — `auth_log` table deferred to v2.
- Changing CORS, rate limiting, or TLS termination.

## Decisions

### D1: Per-route `Depends(require_admin)` over global middleware

**Choice:** attach `Depends(require_admin)` to each admin router (`screener_router`, `confirm_gate_router`, `exit_engine_router`) and the SSE endpoint, **not** a global FastAPI middleware that filters by path prefix.

**Why:**
- `/healthz` is a sibling of `/api/admin/*`, not nested under it. A global middleware needs path-prefix logic; per-route deps need none.
- FastAPI's `dependencies=[Depends(require_admin)]` argument on `APIRouter` covers every route in that router with one line.
- Errors from `Depends` are raised **before** the handler opens the SQLite connection — clean separation from `_envelope.py`'s exception mapper.
- Easier to write a unit test that asserts every admin route has the dep attached (introspection on `app.routes`).

**Alternatives considered:**
- *Global ASGI middleware with prefix match*: simpler config, but harder to unit-test "every admin route is covered" and easier to bypass with a path-traversal mistake.
- *Decorator per handler*: more line noise, redundant with router-level `dependencies`.

### D2: 401 with the existing envelope, not FastAPI's default `{"detail": "..."}`

**Choice:** `require_admin` raises a custom exception (`AuthError`) that the existing exception handler in `_envelope.py` maps to `{"ok": false, "error": {"code": "auth_missing"|"auth_invalid", "message": "..."}}` with HTTP 401. Reuse the same handler that already converts `ConfirmGateError`, `ExitEngineError`, `ValueError`, etc.

**Why:**
- Spec invariant in `server-action-endpoints` requires the `{ok,error}` envelope for **all** error responses. A bare `{"detail": ...}` would violate it.
- One handler = one redaction surface; we already proved the redaction works in `test_api_envelope_security.py`.

**Alternatives considered:**
- *Raise `HTTPException(401, detail="...")`*: simpler but breaks envelope invariant.
- *Custom 401 builder inside `auth.py`*: duplicates exception mapping logic.

### D3: Two distinct error codes — `auth_missing` and `auth_invalid`

**Choice:**
- No `Authorization` header **or** header doesn't start with `Bearer ` → `auth_missing` / 401.
- Header is `Bearer <token>` but token doesn't match → `auth_invalid` / 401.

**Why:** lets the future admin SPA distinguish "you forgot to log in" (redirect to login) from "your token is wrong" (show error + clear token). Both stay 401 (not 403) because there is no concept of "authenticated but unauthorized" in single-user mode.

**Alternatives considered:**
- *Single `auth_failed` code*: smaller surface but worse client UX.

### D4: Constant-time comparison via `secrets.compare_digest`

**Choice:** `secrets.compare_digest(provided, expected)` over `==`.

**Why:** even though we're single-user and admin-only, leaking timing info via `==` short-circuit on the first wrong byte is a 2-line bug we shouldn't ship. Library function, no perf cost.

### D5: Startup validation in `create_app()`, not on first request

**Choice:** `create_app()` reads `Settings().ohmystock_admin_token` and raises `RuntimeError("OHMYSTOCK_ADMIN_TOKEN must be set and at least 32 characters")` if `None` or `len(token) < 32`.

**Why:**
- Fails the API process at boot — Docker, CI, and `uvicorn` all surface the error immediately rather than hiding it until the first 401.
- Mirrors `auth-and-mask.md` §2.4 ("Backend 啟動時若 `OHMYSTOCK_ADMIN_TOKEN` 未設或長度 < 32 → 拒絕啟動").

**Alternatives considered:**
- *Lazy validation on first request*: lets bad deploys boot and only fail under load — bad UX.
- *Pydantic validator on `Settings`*: tempting, but `Settings` is also imported by tests and CLI tools that don't need the token. Validation belongs at the app boundary.

### D6: 32-character minimum, not 32-byte URL-safe minimum

**Choice:** `len(token) < 32` rejects on raw string length. `secrets.token_urlsafe(32)` returns ~43 chars (32 bytes base64-url-encoded), well above the threshold.

**Why:** simple, matches the documented generator (`token_urlsafe(32)`), and forgiving of users who paste a hex token instead.

### D7: Test fixture injects token; no production token in tests

**Choice:** add a `pytest` fixture (likely `valid_admin_token` + an `auth_client` `TestClient` wrapper) in `tests/conftest.py` that monkeypatches `OHMYSTOCK_ADMIN_TOKEN` to a known synthetic value (e.g., `"test-token-32-characters-or-more-xxx"`) and returns a `TestClient` whose default headers include `Authorization: Bearer <token>`.

**Why:** every existing route test gets auth coverage with a one-line fixture swap. No real token leaks into VCS.

### D8: `test_api_no_auth.py` is repurposed, not deleted

The current `test_api_no_auth.py` asserts the *absence* of auth. After this change, it is renamed/rewritten to assert auth is *enforced*: missing token → 401, invalid token → 401, wrong scheme (`Basic ...`) → 401, valid token → 200.

## Risks / Trade-offs

- **[Risk] Admin token in `.env` files leaks via `git add .`.** → Mitigation: `.env` is already in `.gitignore`; `.env.example` ships with `OHMYSTOCK_ADMIN_TOKEN=` (empty). Doc adds a one-liner for `secrets.token_urlsafe(32)`.
- **[Risk] SSE long-lived connection holds a stale token after rotation.** → Mitigation: out of scope for v0 (single user, manual restart). Documented in v2 path (auth-and-mask.md §2.3).
- **[Risk] Tests forget to use the fixture and hit 401.** → Mitigation: auto-use fixture (`autouse=True` scoped to `tests/`) sets the env var; route tests opt-in to the `auth_client`.
- **[Risk] Browsers can't add `Authorization` header to native `EventSource`.** → Mitigation: web-admin uses `fetch` + a polyfill (or `@microsoft/fetch-event-source`). Documented in `docs/auth-and-mask.md` §2.2 already; not a backend concern.
- **[Trade-off] Fail-fast on short token can break dev loops if someone leaves their `.env` empty.** → Acceptable: error message says exactly what to do (`OHMYSTOCK_ADMIN_TOKEN must be set and at least 32 characters; generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'`).

## Migration Plan

1. Land this change behind a feature flag? **No** — single-user dev environment, no production. Hard cut.
2. Sequence:
   a. Add `ohmystock_admin_token` to `Settings`.
   b. Add `src/ohmystock/api/auth.py` (dep + validator + `AuthError`).
   c. Wire `_envelope.py` exception handler to map `AuthError`.
   d. Attach `Depends(require_admin)` to all three routers + `/api/admin/events`.
   e. Call `_validate_admin_token()` in `create_app()`.
   f. Update `tests/conftest.py` with `valid_admin_token` + `auth_client` fixtures.
   g. Update existing route tests to use `auth_client`.
   h. Rewrite `tests/test_api_no_auth.py` → `tests/test_api_auth.py`.
   i. Update `.env.example`.
   j. Add row to `CLAUDE.md` §5 SSOT table.
3. Rollback: revert the commit; `OHMYSTOCK_ADMIN_TOKEN` env var becomes inert.

## Open Questions

- **Should `/healthz` be allowed inside `/api/admin/*`?** No — keep at root `/healthz`. Already there. (Deployment uptime probes shouldn't need a token.)
- **Should we add an `auth_log` SQLite table now?** No — defer to v2 per auth-and-mask.md §2.3.
- **Should we expose `GET /api/admin/whoami`?** Not needed for v0 (single user, no display name). Skip.
