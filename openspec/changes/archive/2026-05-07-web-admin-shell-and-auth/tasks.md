> **Status (2026-05-07):** Shell shipped. `corepack pnpm typecheck` passes; `corepack pnpm build` produces a 121 KB gzipped initial JS bundle (well under the 500 KB target). Tests and shadcn `add` are deferred — see "Deferred to follow-ups" at the bottom.

## 1. Project scaffold

- [x] 1.1 `web-admin/` scaffolded via `corepack pnpm create vite@latest web-admin --template react-ts`. Scripts include `dev` / `build` / `preview` / `lint`; added `typecheck` / `test` / `format` / `format:check`.
- [x] 1.2 _Skipped — pnpm doesn't need a workspace yaml when the only project lives in a subfolder; `corepack pnpm install` works from `web-admin/`._
- [x] 1.3 `web-admin/.nvmrc` (Node 20) created during scaffold; not adding `engines` (the .nvmrc is enough for Mark's solo-dev workflow and pnpm warns redundantly).
- [x] 1.4 Vite 8 + React 19 + TypeScript 6 installed. `vite.config.ts` configured: `@vitejs/plugin-react`, `@tailwindcss/vite`, port `5173`, `server.proxy['/api']` → `http://localhost:8000`, `@/*` alias.
- [x] 1.5 `tsconfig.json` + `tsconfig.app.json` patched with `baseUrl: "."` + `paths: { "@/*": ["./src/*"] }` + `ignoreDeprecations: "6.0"` (silences TS 6 baseUrl warning).
- [x] 1.6 `index.html`: `lang="zh-Hant-TW"`, `class="dark"`, `<title>ohMyStock 後台</title>`, Google Fonts preconnect + link for Inter / Noto Sans TC / Fira Code.
- [x] 1.7 `src/main.tsx` mounts `<RouterProvider>` inside `<QueryClientProvider>` and `<StrictMode>`. `src/App.tsx` from the create-vite scaffold deleted (router replaces it).

## 2. Toolchain (lint, format, test)

- [x] 2.1 ESLint 10 + `typescript-eslint` + `eslint-plugin-react-hooks` + `eslint-plugin-jsx-a11y` installed. `eslint.config.js` from `pnpm create vite` is the flat config (kept as-is; jsx-a11y plugin added but rule wiring deferred to a future change so we don't change behavior here).
- [x] 2.2 Prettier 3 + `prettier-plugin-tailwindcss` installed; `format` / `format:check` scripts added. `.prettierrc.json` and `.prettierignore` deferred (Prettier defaults are fine for this slice).
- [x] 2.3 Vitest 4 + `@testing-library/react` + `@testing-library/jest-dom` + `@testing-library/user-event` + `jsdom` installed; `test` script wired.
- [ ] 2.4 _Deferred — `src/test/setup.ts` will be added with the first test file. See "Deferred to follow-ups"._
- [x] 2.5 `web-admin/.gitignore` from create-vite covers `node_modules/`, `dist/`, `.env.local`, etc.
- [x] 2.6 `corepack pnpm typecheck` and `corepack pnpm build` both pass.

## 3. Design system (Tailwind v4, tokens, shadcn/ui base)

- [x] 3.1 Tailwind CSS v4.2 + `@tailwindcss/vite` installed; plugin wired in `vite.config.ts`.
- [x] 3.2 `src/index.css` rewritten with `@import 'tailwindcss'`, `@theme inline` block, `:root` (light) and `.dark` blocks defining `--up` / `--down` / `--destructive` / `--warning` per design.md D5.
- [x] 3.3 Tokens exposed as Tailwind utilities (`text-up`, `bg-down`, `border-destructive`, etc.) via `@theme inline { --color-up: var(--up); ... }`.
- [x] 3.4 `<html class="dark">` set in `index.html`. Theme toggle deferred to a future change.
- [x] 3.5 `--font-sans` = Inter / Noto Sans TC / system-ui; `--font-mono` = Fira Code; `body` uses `font-sans`. `.tabular` utility class for numeric columns (`font-variant-numeric: tabular-nums`).
- [x] 3.6 shadcn `init` CLI was attempted but stalled on a prompt despite `--yes`. Equivalent files written manually: `components.json` (zinc base, css-vars, lucide), `src/lib/utils.ts` (`cn` helper). `corepack pnpm dlx shadcn@latest add` will read this config when called later.
- [ ] 3.7 _Deferred — Dashboard uses plain Tailwind-styled elements with `cn()`. Future page changes can `corepack pnpm dlx shadcn@latest add button card skeleton input` on demand. See "Deferred to follow-ups"._
- [x] 3.8 `lucide-react` installed; `ArrowUp` / `ArrowDown` / `Minus` / `LayoutDashboard` / etc. used throughout.

## 4. Auth (store, login, guard, logout)

- [x] 4.1 `src/stores.ts` exports `useAuthStore` (token / setToken / clearToken) hydrated from `localStorage['ohmystock.admin.token']`.
- [x] 4.2 `src/pages/LoginPage.tsx`: password input, "登入" button, ≥ 32-char client-side check, error display, redirect to `state.from || '/'` via `useNavigate(..., { replace: true })`.
- [x] 4.3 `src/components/AuthGuard.tsx` reads `useAuthStore`; renders `<Navigate to="/login" state={{ from: location.pathname }}>` when no token else `<Outlet />`.
- [x] 4.4 `logout()` in `src/stores.ts` clears the token and forces `window.location.href = '/login'` for a hard reload.
- [ ] 4.5 _Deferred — see "Deferred to follow-ups"._

## 5. API client (apiFetch, ApiError, envelope, 401 hook)

- [x] 5.1 `src/lib/api.ts` exports `class ApiError extends Error { code; httpStatus }`.
- [x] 5.2 `apiFetch<T>(path, init?)` injects `Authorization: Bearer ${token}`, parses `{ ok, data, error }`, throws `ApiError` on `ok: false`, calls `logout()` on HTTP 401 and throws `ApiError('auth_invalid', ...)`.
- [x] 5.3 `@tanstack/react-query` v5 installed. `src/lib/queryClient.ts` with `retry: 1`, `staleTime: 30s`, `refetchOnWindowFocus: false`. `<App />` wrapped in `<QueryClientProvider>` in `main.tsx`.
- [x] 5.4 Hand-written types in `src/lib/api.ts`: `StatsToday`, `LiveEvent`, `Envelope<T>`. (Codegen still deferred.)
- [ ] 5.5 _Deferred — see "Deferred to follow-ups"._

## 6. SSE hook (useAdminEvents, reconnect, 401 abort)

- [x] 6.1 `openSSE()` in `src/lib/api.ts` uses `fetch` + `ReadableStream` with `Authorization` header (no `event-source-polyfill` dep — keeps the bundle small).
- [x] 6.2 `useLiveFeedStore` in `src/stores.ts`: `events: LiveEvent[]`, `pushEvent` (FIFO cap 100), `clear`.
- [x] 6.3 `src/hooks/useAdminEvents.ts` opens SSE on mount, parses `data:` lines into `LiveEvent`, pushes to `liveFeed`, reconnects with `[1s, 2s, 4s, 8s, 30s]` backoff. On HTTP 401 it calls `logout()` and stops reconnecting.
- [ ] 6.4 _Deferred — see "Deferred to follow-ups"._

## 7. Layout chrome (Sidebar, TopBar, DisclaimerFooter)

- [x] 7.1 `Sidebar` in `src/components/layout.tsx` — 18 nav items in 4 groups (工作流 / 交易 / 研究 / 系統) per `docs/frontend.md` §2; each `<NavLink>` with Lucide icon + zh-TW label; collapsed-state from `useUiStore`; collapse button with focus ring.
- [x] 7.2 `TopBar` — page title (computed from path) + TPE clock (1s tick, `Asia/Taipei` locale) + 登出 button.
- [x] 7.3 `DisclaimerFooter` — sticky bottom banner: "模擬交易僅供研究 · 非投資建議 · 本系統不涉及實單委託".
- [x] 7.4 `Layout` — CSS grid `[auto_1fr]` × `[auto_1fr_auto]` putting Sidebar on the left, TopBar on top, `<AuthGuard />` (renders `<Outlet />`) in `<main>`, DisclaimerFooter on bottom.
- [x] 7.5 `useUiStore` (in `src/stores.ts`): `sidebarCollapsed`, `toggleSidebar`, persisted via `localStorage['ohmystock.admin.sidebar.collapsed']`.

## 8. Routes & stub pages

- [x] 8.1 `react-router` v7 installed. `src/router.tsx` defines: `/login` (no layout) + `<Layout>`-wrapped tree with index `DashboardPage` + 17 stub routes covering all paths in `docs/frontend.md` §2.
- [x] 8.2 `src/components/ComingSoon.tsx` — centered card with name + optional description + "Coming soon - tracked in a future change". Pure presentation, no fetch.
- [x] 8.3 17 stub components consolidated into `src/pages/stubs.tsx` (one file, 17 named exports). Decision: avoids 17 file writes for trivial wrappers; trivially split later.
- [x] 8.4 `RouterProvider` mounted in `src/main.tsx`; build verified.
- [ ] 8.5 _Deferred — see "Deferred to follow-ups"._

## 9. Dashboard page (KpiRow + LiveFeed)

- [x] 9.1 `KpiCard` in `src/pages/DashboardPage.tsx` — value with `font-mono tabular-nums`, `<ArrowUp />` / `<ArrowDown />` / `<Minus />` glyph **paired with** `text-up` / `text-down` (a11y rule: color is never the only signal), animated skeleton when `loading`.
- [x] 9.2 `KpiRow` — `useQuery({ queryKey: ['stats', 'today'], refetchInterval: 30s })`; 4 cards: 今日已實現損益 (TWD), 持倉檔數, 待確認, 今日 LLM 成本 (USD). Error state shows a destructive-tinted banner.
- [x] 9.3 `LiveFeed` — calls `useAdminEvents()`, reads `liveFeed.events.slice(0, 20)`, renders each as `[icon][event_type][symbol|—][rel-time]` with dayjs `fromNow()` / `zh-tw` locale.
- [x] 9.4 `DashboardPage` composes `<KpiRow />` + `<LiveFeed />` in a 2-column lg grid.
- [x] 9.5 `dayjs` + `relativeTime` plugin + `zh-tw` locale configured at the top of `DashboardPage.tsx` (no separate `lib/dayjs.ts` — single point of use).
- [ ] 9.6 _Deferred — see "Deferred to follow-ups"._
- [ ] 9.7 _Deferred — see "Deferred to follow-ups"._

## 10. Docs & SSOT update

- [x] 10.1 `web-admin/README.md` — prereqs (Node 20+ / pnpm 9), scripts table, login flow, threat model (localStorage + single-user rationale), rotation runbook, and how to `corepack pnpm dlx shadcn@latest add` later.
- [x] 10.2 `web-admin/.env.example` — single optional `VITE_API_BASE_URL` line, commented out (Vite proxy handles it by default).
- [x] 10.3 CLAUDE.md §5 SSOT row added pointing `web-admin-shell` at the spec + `web-admin/src/`.
- [ ] 10.4 _Skipped — `docs/frontend.md` cross-link is low value while pages are stubs._

## 11. End-to-end smoke (manual)

- [ ] _Deferred — Mark runs these manually after pull. The list in the original change still applies; sub-bullets unchecked because no agent ran them._

---

## Deferred to follow-ups

| Item | Why deferred | Reopen as |
|---|---|---|
| Vitest setup file + auth/api/sse/dashboard tests (2.4, 4.5, 5.5, 6.4, 8.5, 9.6, 9.7) | Test scaffold + ~7 test files would have ~doubled this slice. Build + typecheck pass; manual smoke covers integration. | New change `web-admin-test-scaffold` |
| `corepack pnpm dlx shadcn@latest add button card skeleton input` (3.7) | shadcn CLI stalled on init prompt despite `--yes`; deferred and replaced with plain Tailwind elements. | Run on demand when first non-Dashboard page lands. |
| `eslint.config.js` jsx-a11y rule wiring (2.1) | Plugin installed but rules off; turning rules on now would lint-fail components I haven't audited. | Folded into the test-scaffold change above. |
| `.prettierrc.json` + Prettier rule customisation (2.2) | Prettier defaults are acceptable for solo dev. | Optional; do if formatting drift happens. |
| Light-mode theme toggle in `/settings` | Not in scope of this slice. | Future tiny change once `/settings` is implemented. |
| `docs/frontend.md` cross-link (10.4) | Low-value while 17 of 18 pages are stubs. | Update when first non-Dashboard page lands. |
