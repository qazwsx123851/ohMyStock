## Why

The admin backend (`/api/admin/*` routes + SSE `/api/admin/events`) is currently no-auth by design — `server-action-endpoints` and `backend-api-and-eventbus` both explicitly defer auth to a follow-up. Phase 4 (web-admin UI, target 2026-08-11) cannot ship to even a Cloudflare Tunnel without a Bearer gate, and any future `/api/admin/*` endpoints (read endpoints, settings, audit) inherit the same hole if we don't close it now. This change layers the gate on once, before the surface area grows.

## What Changes

- Add a Bearer-token middleware that gates every `/api/admin/*` route (REST + SSE) against `OHMYSTOCK_ADMIN_TOKEN` from `Settings`.
- Leave `GET /healthz` open (liveness probe must work without a token).
- Use `secrets.compare_digest` for constant-time comparison.
- Reject missing / malformed / wrong tokens with HTTP 401 in the existing `{"ok": false, "error": {"code", "message"}}` envelope (codes: `auth_missing`, `auth_invalid`).
- **Fail-fast on startup**: if `OHMYSTOCK_ADMIN_TOKEN` is unset or shorter than 32 chars, `create_app()` raises and the process refuses to start (per `docs/auth-and-mask.md` §2.4).
- **BREAKING (spec-level)**: flip the existing "no auth" requirements in `server-action-endpoints` and `backend-api-and-eventbus`. Endpoint behavior is otherwise unchanged.
- Add `OHMYSTOCK_ADMIN_TOKEN` to `Settings` and `.env.example`.

## Capabilities

### New Capabilities
- `web-admin-bearer-auth`: Bearer token gate for `/api/admin/*` (REST + SSE), startup token validation, 401 envelope shape, and the `require_admin` FastAPI dependency that downstream admin endpoints attach to.

### Modified Capabilities
- `server-action-endpoints`: replace the "全部端點維持無認證（v0 no Bearer）" requirement — endpoints now require Bearer auth via the new capability's gate. The envelope, status mapping, redaction, and per-request connection requirements are unchanged.
- `backend-api-and-eventbus`: replace the "`/api/admin/events` SHALL 仍為無認證" clause — the SSE endpoint now requires Bearer auth. `/healthz` remains no-auth.

## Impact

- **Code**:
  - New: `src/ohmystock/api/auth.py` (`require_admin` dependency, `_validate_admin_token` startup check).
  - Modified: `src/ohmystock/api/app.py` (wire dependency to admin routes; call validator in `create_app()`).
  - Modified: `src/ohmystock/api/routes/_envelope.py` or each router (attach `Depends(require_admin)` to admin routes; not to `/healthz`).
  - Modified: `src/ohmystock/config.py` (+`ohmystock_admin_token: str | None`).
  - Modified: `.env.example` (+`OHMYSTOCK_ADMIN_TOKEN=`).
- **Tests**:
  - New: `tests/test_api_auth.py` covering 401 paths, valid-token success, SSE auth, startup fail-fast, timing-safe comparison.
  - Updated: existing route tests (`test_api_screener_endpoint.py`, `test_api_confirm_gate_endpoints.py`, `test_api_exit_engine_endpoint.py`, `test_api_envelope_security.py`, `test_api_no_auth.py`) inject a valid token via fixture; `test_api_no_auth.py` is repurposed/renamed to assert auth is now enforced.
- **Docs**: `CLAUDE.md` §5 SSOT table gets a row for the new capability spec.
- **Ops**: Devs must set `OHMYSTOCK_ADMIN_TOKEN` (32+ chars) in `.env` before starting the API. `python -c "import secrets; print(secrets.token_urlsafe(32))"` is the documented generator.
- **No data migrations**, **no broker behavior change**, **no LLM cost change**.
