## 1. Backend — SymbolMaskTable

- [x] 1.1 Add `src/ohmystock/eventbus/mask_table.py` with `SymbolMaskTable` (constructor takes `industry_lookup: dict[str, str]`; methods `mask`, `industry_of`; base-26 `_next_label`).
- [x] 1.2 Add `tests/eventbus/test_mask_table.py` covering: STK-A/B/C ordering, idempotent same-symbol, STK-AA rollover at 27, industry fallthrough to "其他", two-instance independence.
- [x] 1.3 Run `uv run pytest tests/eventbus/test_mask_table.py -x` and confirm green.

## 2. Backend — MaskedEventSerializer + PUBLIC_WHITELIST + DENYLIST_FIELDS

- [x] 2.1 Extend `src/ohmystock/eventbus/serializers.py` with `PUBLIC_WHITELIST` (16 keys per `docs/backend-eventbus.md` §4.2), `DENYLIST_FIELDS` (13 names), `TWSE_CODE_RE`, and `MaskedEventSerializer` class taking a `SymbolMaskTable`.
- [x] 2.2 Export `MaskedEventSerializer`, `SymbolMaskTable`, `PUBLIC_WHITELIST`, `DENYLIST_FIELDS` from `src/ohmystock/eventbus/__init__.py`.
- [x] 2.3 Add `tests/eventbus/test_public_serializer.py`: parametric fat-payload DENYLIST test over all 16 event types; symbol-replacement scenario; reasoning regex (real TWSE code, year `2026`, non-4-digit numbers); empty payload for unknown event_type; envelope shape equality with `AdminEventSerializer.serialize`.
- [x] 2.4 Run `uv run pytest tests/eventbus/ -x` and confirm green.

## 3. Backend — /api/public/events SSE route

- [x] 3.1 Add `src/ohmystock/api/routes/public_events.py` with `router = APIRouter(prefix="/api/public")`, module-level `_mask_table` and `_serializer` set during `set_mask_table()` helper, plus `_public_event_stream()` generator mirroring `_admin_event_stream` (subscribe / unsubscribe / 15 s keepalive). No `auth` import.
- [x] 3.2 Confirm via grep `grep -i "auth" src/ohmystock/api/routes/public_events.py` returns zero matches; add `tests/api/test_public_events_route.py::test_no_auth_import` as static-text guard.
- [x] 3.3 Wire `set_mask_table(...)` from `api/app.py:_lifespan` after the existing `set_universe_closes_loader` call: SELECT industry rows from `universe_daily` if the column exists; empty dict otherwise; construct one `SymbolMaskTable` + one `MaskedEventSerializer`; pass into route module. In `finally`, call `clear_mask_table()` to null the module globals.
- [x] 3.4 `app.include_router(public_events_router)` in `api/app.py:create_app`.
- [x] 3.5 Add `tests/api/test_public_events_route.py` integration: route registered, masked-symbol frame on emit, no raw `2330` substring, unsubscribe on disconnect, keepalive on idle, RuntimeError when mask table not installed.
- [x] 3.6 Add path-scoped `_PublicCORSMiddleware` so only `/api/public/*` returns ACAO for `http://localhost:5173` / `:5174`; admin routes unchanged. Tests cover preflight from 5173 / 5174 / unknown origin and admin-leak negative case.
- [x] 3.7 Run `uv run pytest tests/api/test_public_events_route.py -x` — 10 passed.

## 4. Frontend — web-public/ scaffold

- [x] 4.1 Create `web-public/` with `package.json` (react 19, react-dom 19, typescript 6.0.2, vite 8, tailwindcss 4, @types/react, @types/react-dom), `tsconfig.json` + `tsconfig.app.json` + `tsconfig.node.json`, `vite.config.ts` (port 5173, proxy `/api` → `http://localhost:8000`), `index.html`, `src/main.tsx`, `src/index.css`.
- [x] 4.2 Minimal design tokens in `src/index.css` (warning amber + zinc neutrals). No `packages/` workspace.
- [x] 4.3 Add `web-public/public/robots.txt` with the 3-line content from spec; verified copied into `dist/robots.txt` by `npm run build`.

## 5. Frontend — components and pages

- [x] 5.1 `web-public/src/components/DisclaimerBanner.tsx` — verbatim zh-TW from `docs/auth-and-mask.md` §4.3, `sticky top-0 z-50`, no dismiss control.
- [x] 5.2 `web-public/src/components/MaskedEventsFeed.tsx` — EventSource subscriber, dedupe by `event_id`, 50-cap with oldest-eviction (drops from both list and seen-id set), client-side DENYLIST filter, TPE timestamp formatting via `Intl.DateTimeFormat`.
- [x] 5.3 `web-public/src/pages/NotFoundPage.tsx` — h1 404 + back-link `<a href="/">回首頁</a>`. DisclaimerBanner is mounted at App level so it shows on 404 automatically.
- [x] 5.4 `App.tsx` wires DisclaimerBanner + `<Outlet />` + footer; `router.tsx` defines `/` → HomePage, `*` → NotFoundPage.
- [x] 5.5 `npm install && npm run build` (pnpm not on this machine — npm is the available manager); build succeeded, `dist/index.html` + `dist/robots.txt` + `dist/assets/index-*.js` (92 KB gzip) present.

## 6. Frontend — component unit tests

- [x] 6.1 `vitest.config.ts` mergeConfig over vite config (jsdom env, globals on, setup file); `src/test/setup.ts` imports `@testing-library/jest-dom/vitest`.
- [x] 6.2 `src/__tests__/DisclaimerBanner.test.tsx` — 3 tests: verbatim substrings, no dismiss control, role=alert.
- [x] 6.3 `src/__tests__/MaskedEventsFeed.test.tsx` — 6 tests using a `FakeEventSource` (idle render, prepend, 50-cap eviction, dedup, client-side DENYLIST strip with synthetic 2330, EventSource close on unmount).
- [x] 6.4 `npm test -- --run` — 2 files, 9 tests, all passing in 3.41 s.

## 7. E2E — Playwright mask penetration test

- [x] 7.1 `e2e/playwright.config.ts` (port 5173 baseURL) + `e2e/fixtures/twse_top50_names.json` (50 public TWSE company names).
- [x] 7.2 `e2e/test_public_mask.spec.ts` — 30 s `page.evaluate` capture, three assertion blocks (no DENYLIST key tokens; no 4-digit codes outside ISO-shaped substrings; no top-50 name). Manual run (not in CI): `npx playwright install chromium && npm run e2e` with backend + dev server up.
- [x] 7.3 `web-public/README.md` documents the dev / test / E2E invocation including the explicit `npx playwright install chromium` first-run step.

## 8. Wiring + smoke

- [x] 8.1 `uv run pytest tests/` — 1469 passing, 3 pre-existing `.env`-leak tests deselected (`test_validate_admin_token_rejects_none`, `test_create_app_refuses_to_start_without_token`, `test_admin_token_defaults_to_none_when_unset` — all stem from real `OHMYSTOCK_ADMIN_TOKEN` in repo `.env` surviving `monkeypatch.delenv`; not caused by this change).
- [x] 8.2 Programmatic smoke via `scripts/smoke_public_events.py` — emit `decision_made` for symbol `2330`, observe `masked_symbol: STK-A`, `reasoning_summary: STK-? 突破 20MA`, `raw 2330 in frame text: False`, `raw symbol key in payload: False`. (Two-terminal browser smoke skipped — same code path is exercised by integration tests + this script.)
- [x] 8.3 Admin SSE behaviour unchanged: covered by pre-existing `tests/test_admin_sse_subscribes.py` (4 tests passing in the 1469 above) which asserts raw `symbol`/`reasoning` still flow on `/api/admin/events`.

## 9. Docs and spec sync

- [x] 9.1 `CLAUDE.md` §5 SSOT row added covering all three new capabilities, lists every new source file + the three post-archive spec paths.
- [x] 9.2 `openspec status --change web-public-shell-and-mask` — 4/4 artifacts complete (proposal, design, specs, tasks).
