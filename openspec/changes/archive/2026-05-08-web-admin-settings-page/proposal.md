## Why

`/settings` is currently a `ComingSoon` stub. Cold-start scenario §10 (`docs/user-scenarios.md`) requires Mark to verify which API keys are loaded, which broker mode is active, and what `OHMYSTOCK_AUTO_EXECUTE` is set to before trusting that pre-market routine §1 will work. Today this requires `cat .env` on the host, which is friction and impossible from a remote browser session through the Cloudflare tunnel.

We ship a **read-only** v0 of `/settings` that surfaces the live loaded `Settings()` object with secrets masked. PUT is deliberately deferred — `OHMYSTOCK_AUTO_EXECUTE` and broker mode are safety-critical (`docs/safety-and-simulation.md` §2.9) and the existing `.env` + restart workflow is the correct place for them. Theme is also deferred (no theme-switch UI in this iteration per `docs/web-admin-page-designs.md` §16).

## What Changes

- New `GET /api/admin/settings` endpoint returning the redacted live `Settings` snapshot in 4 sections: `api_keys`, `theme`, `safety`, `breakers`. Secrets masked to `set` / `unset` booleans (never the value, never a prefix). Reuses existing Bearer auth dep + `{ok,data,error}` envelope.
- New `/settings` page renders the 4 sections per `docs/web-admin-page-designs.md` §16 wireframe, replacing the `SettingsPage` stub. All controls disabled with hint text "編輯 `.env` 並重啟以變更" — no PUT, no inline edit, no health-check calls.
- Safety section uses `--warning` Card border + `AlertTriangle` icon when `auto_execute=false`; switches to `--destructive` + `AlertCircle` + 「⚠ AUTO_EXECUTE 已啟用」 banner when `true`. Read-only either way.
- Page-design SSOT (`docs/web-admin-page-designs.md` §16) and CLAUDE.md §5 add a row pointing at the new spec + endpoint.

Out of scope (deferred, explicitly): PUT endpoint, `.env` writeback, theme switch UI, per-section validation/health-check calls, breaker form editing.

## Capabilities

### New Capabilities
- `admin-settings-endpoint`: `GET /api/admin/settings` — returns redacted live `Settings` snapshot under unified envelope, gated by Bearer auth.
- `web-admin-settings-page`: `/settings` route — renders 4-section read-only view with safety colour semantics and `.env`-edit hint.

### Modified Capabilities
- (none — this is a stub-replacement; no existing requirements change)

## Impact

- **Code**: new `src/ohmystock/api/routes/settings.py` + register in `api/app.py`; new `web-admin/src/pages/SettingsPage.tsx`; remove `SettingsPage` from `web-admin/src/pages/stubs.tsx` and update `router.tsx` import; extend `web-admin/src/lib/api.ts` with `getSettings()`; update `CLAUDE.md` §5 SSOT row.
- **APIs**: 1 new GET endpoint. No schema migrations. No SSE event types added.
- **Dependencies**: none.
- **Security**: redactor is the contract — must mask `anthropic_api_key`, `shioaji_api_key`, `shioaji_secret_key`, `shioaji_ca_passwd`, `shioaji_person_id`, `finmind_token`, `ohmystock_admin_token` to `bool` only. Endpoint inherits existing Bearer auth; no new auth surface.
- **Risk**: low. No write path, no breaker behaviour change, no broker change.
