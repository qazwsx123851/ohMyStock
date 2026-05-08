## 1. Backend — `admin-settings-endpoint`

- [x] 1.1 Add `src/ohmystock/api/routes/settings.py` with FastAPI `APIRouter`, `GET /api/admin/settings` handler, and a private `_redact(settings: Settings) -> dict` helper that whitelists exactly the fields listed in spec §"回應 schema" (no `dict()` dump). Helper SHALL return `{api_keys, theme, safety, breakers}`.
- [x] 1.2 Implement secret detection: each of `anthropic`, `finmind`, `shioaji` is `bool((value or "").strip())`; `shioaji` requires both `shioaji_api_key` and `shioaji_secret_key` non-empty after strip.
- [x] 1.3 Map `safety.{auto_execute, broker}` and 7 `breakers.*` fields directly from `Settings` with no clamp / rounding.
- [x] 1.4 Wire the handler through `_envelope.to_success`; let exceptions fall to `_envelope.map_exception_to_envelope`.
- [x] 1.5 Register the router in `src/ohmystock/api/app.py` with `dependencies=[Depends(require_admin)]`, matching the mounting pattern used by `market`, `backtest`, `journal`, `positions`, `stats`.
- [x] 1.6 Add `tests/api/test_settings_endpoint.py` covering: 401 missing token, 401 wrong token, 200 default Settings, 200 with all keys set, 200 with shioaji half-set, 200 with whitespace-only key, leak assertion (raw secret string MUST NOT appear anywhere in serialized response), 405 on PUT.
- [x] 1.7 Run backend test suite (`pytest tests/api/test_settings_endpoint.py -v`); fix any failures.

## 2. Frontend — `getSettings()` API client

- [x] 2.1 Add `SettingsPayload` TS type to `web-admin/src/lib/api.ts` matching the response schema exactly (4 sections, 7 breakers, 3 api_keys booleans).
- [x] 2.2 Add `getSettings(): Promise<SettingsPayload>` using existing `apiFetch`; return `data` (not the envelope).
- [x] 2.3 Add `web-admin/src/lib/__tests__/api.test.ts` cases: success path resolves to `data`; `ok=false` rejects with `error.code` propagated; 401 triggers existing 401-abort flow.

## 3. Frontend — `SettingsPage`

- [x] 3.1 Create `web-admin/src/pages/SettingsPage.tsx` with a single `useEffect`-driven fetch + 3-state render (`loading` skeletons / `error` retry banner / `success` 4 Cards).
- [x] 3.2 Render API keys Card: 3 rows, each row `[name] [Badge "已設定" or "未設定"]`. No mask dots. Disabled hint footer "編輯 `.env` 並重啟以變更".
- [x] 3.3 Render Theme Card: disabled `<select>` showing "跟隨系統"; hint footer "此版本未提供主題切換 UI".
- [x] 3.4 Render Safety Card: branch on `data.safety.auto_execute`. False → `border-warning` + `<AlertTriangle/>` + "AUTO_EXECUTE 關閉（人工 Confirm Gate）" + broker line. True → `border-destructive` + `<AlertCircle/>` + "⚠ AUTO_EXECUTE 已啟用" banner + broker line. Both states paired colour + icon.
- [x] 3.5 Render Breakers Card: 7 disabled `<input type="number">` with formatted display (percent inputs show as `25` for `0.25`; `account_equity_twd` shows `1,000,000` thousands separator). Hint footer same as 3.2. *(Note: implementation uses `type="text" inputMode="numeric"` because `type="number"` strips comma thousand-separators; spec scenario updated to match.)*
- [x] 3.6 Update `web-admin/src/router.tsx`: import `SettingsPage` from `@/pages/SettingsPage`; remove `SettingsPage` from the `stubs` import list. Update `web-admin/src/pages/stubs.tsx` to drop the `SettingsPage` export.
- [x] 3.7 Add `web-admin/src/pages/__tests__/SettingsPage.test.tsx`: loading state shows 4 skeletons no save buttons; success default renders 3 "未設定" badges + warning border + AlertTriangle; success with `auto_execute=true` renders destructive border + AlertCircle + "AUTO_EXECUTE 已啟用"; 401 triggers redirect; 5xx shows retry button; DOM never contains "儲存" / "啟用" / "我已了解風險" / "PUT".
- [x] 3.8 Update `web-admin/src/__tests__/router-smoke.test.tsx` so `/settings` is no longer asserted as `ComingSoon`.

## 4. Docs / SSOT

- [x] 4.1 Update `CLAUDE.md` §5 SSOT table — add a row for `web-admin Settings page (read-only v0)` pointing at `openspec/specs/web-admin-settings-page/spec.md` (post-archive), `openspec/specs/admin-settings-endpoint/spec.md` (post-archive), `src/ohmystock/api/routes/settings.py`, `web-admin/src/pages/SettingsPage.tsx`, and `web-admin/src/lib/api.ts` (`getSettings`).
- [x] 4.2 Update `docs/web-admin-page-designs.md` §16 「後端狀態」 line from `❌` to `✅（read-only v0；GET /api/admin/settings）` and tighten the wireframe to match the read-only rendering (no "更新" / "儲存" buttons, no "我已了解風險，啟用" button).

## 5. Verification

- [x] 5.1 Run full backend test suite (`pytest`); ensure no regression in existing admin endpoint tests. *(974/974 passing.)*
- [x] 5.2 Run full frontend test suite (`npm test --prefix web-admin -- --run`). *(155/155 passing across 16 files.)*
- [ ] 5.3 Manual smoke: start API + admin dev server, log in, navigate to `/settings`, confirm 4 sections render, all controls disabled, page passes red/green dual-encoding visual check (icon + colour both present). *(Deferred — requires user to run dev server. Automated DOM tests in `SettingsPage.test.tsx` cover the disabled-state, 4-section layout, and warning/destructive icon+border invariants.)*
- [ ] 5.4 Manual leak check: with a real-looking `ANTHROPIC_API_KEY=sk-ant-XXXX` set, GET `/api/admin/settings` and grep response body — confirm `sk-ant` and `XXXX` substring not present. *(Deferred — requires user to run live API. `tests/api/test_settings_endpoint.py::test_raw_secret_does_not_appear_in_response` and `::test_response_does_not_leak_raw_settings_field_names` automate the equivalent assertions.)*
- [x] 5.5 `openspec validate web-admin-settings-page --strict`. *(Passing.)*
