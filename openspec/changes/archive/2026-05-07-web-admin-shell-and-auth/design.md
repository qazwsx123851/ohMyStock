## Context

Phase 4 backend ships four capabilities (`web-admin-bearer-auth`, `admin-read-endpoints`, `server-action-endpoints`, `eventbus-emitters`) that together expose ~10 REST endpoints under `/api/admin/*` plus an SSE stream at `/api/admin/events`. The user-facing surface for all of this is `docs/frontend.md` — an 18-page admin app, none of which exists yet.

Building all 18 pages in one change would balloon scope and likely require re-doing routing or auth halfway through. Instead this change builds **only the shell** — the scaffold, auth lifecycle, layout chrome, and routing — plus one real page (Dashboard) that exercises both REST and SSE end-to-end. Subsequent changes fill in pages one at a time.

**Constraints:**
- Single user; localhost or Cloudflare Tunnel only (per CLAUDE.md §1, decision #6)
- Must keep `web-admin/` bundle isolated from any future `web-public/` (decision #13) — i.e., no cross-imports
- `OHMYSTOCK_ADMIN_TOKEN` is the only auth credential; backend already enforces 401 on missing/invalid (`openspec/specs/web-admin-bearer-auth/spec.md`)
- zh-TW UI; Taiwan-stock convention **紅漲綠跌** (red = up, green = down — opposite of US/EU)
- Solo dev; no SSO, no audit-of-auth, no multi-tenant concerns

## Goals / Non-Goals

**Goals:**
- Ship a working `web-admin/` Vite + React 19 app that boots, authenticates, and proves end-to-end wiring on the Dashboard page
- Establish patterns (auth store, fetch client, SSE hook, route layout, design tokens) that all 17 future page changes can reuse without modification
- Keep the bundle small (target < 500 KB gzipped initial JS) and the dev loop fast (target < 1s HMR)

**Non-Goals:**
- Any of the 17 non-Dashboard pages — they remain stubs in this slice
- Charts, complex forms, markdown rendering — pulled in by future page changes when first needed
- Monorepo `packages/` extraction — premature until a second app (`web-public/`) actually consumes shared types
- Production deployment / CDN / Cloudflare Tunnel config — local `pnpm dev` against `localhost:8000` is enough for this slice
- Mobile-first responsive design — admin is desktop-only (Mark uses it on his workstation)
- Backend changes — all required endpoints already exist

## Decisions

### D1 — Token storage: `localStorage` (not cookie, not env var)

**Choice:** Store the Bearer token in `localStorage` under key `ohmystock.admin.token`, written by the login screen, read by the API client interceptor, cleared on logout or 401.

**Alternatives considered:**
- *HttpOnly cookie*: Standard for production SaaS, but requires backend `Set-Cookie` support (not in current spec); over-engineered for single-user localhost.
- *`VITE_ADMIN_TOKEN` env var* (as `docs/auth-and-mask.md` §2.2 suggests): Bakes token into bundle, requires rebuild to rotate. Acceptable per the doc but worse ergonomics — Mark would have to edit `.env.local` and restart Vite every rotation.
- *`sessionStorage`*: Loses token on browser close, forcing re-entry every session. Annoying for a tool used multiple times a day.

**Rationale:** `localStorage` fits the threat model — only Mark uses this app, only on his machine, and the bundle is never served to the public (per `docs/auth-and-mask.md` §5). XSS risk is negligible because we render no user-supplied HTML in the shell. Token rotation is one-click via the logout button.

### D2 — Routing: React Router v7 with a single auth guard at the layout level

**Choice:** One `<Layout>` component wraps all 18 routes; it reads the auth store and either renders `<Outlet />` (token present) or redirects to `/login`. Login page is at `/login` and renders without the layout.

**Alternatives considered:**
- *Per-route guard HOCs*: Boilerplate; easy to forget when adding a route.
- *Route loader-based auth check*: More idiomatic for v7 but adds complexity (loaders run before render, harder to redirect cleanly to login with return-URL state).

**Rationale:** Single guard = one place to get auth right, hard to bypass. Return-URL is preserved via `useLocation().pathname` and restored after login.

### D3 — SSE client: native `EventSource` with `Authorization` header polyfill

**Choice:** Use `event-source-polyfill` (or hand-rolled `fetch` + `ReadableStream`) so we can set the `Authorization: Bearer <token>` header. Native `EventSource` does not support custom headers.

**Alternatives considered:**
- *Token in query string* (`?token=...`): Trivial but logs the token to access logs, browser history, and any reverse proxy. Unacceptable.
- *WebSocket*: Backend currently emits SSE only; switching protocols is out of scope.
- *Long-poll fallback*: Premature; SSE works in all target browsers (Chrome / Firefox / Edge / Safari 17+).

**Rationale:** Polyfill is ~3 KB, well-maintained, and lets us keep the token out of URLs.

### D4 — State management: Zustand (client) + TanStack Query v5 (server cache)

**Choice:** Zustand for auth + UI state (sidebar collapsed, theme); TanStack Query for all `/api/admin/*` GET responses. SSE events stream into a small Zustand "live feed" slice (capped at 100 events).

**Alternatives considered:**
- *Redux Toolkit*: Overkill for the small client-state surface this app has.
- *Plain React Context*: Re-render storms once 18 pages share state.
- *Jotai / Valtio*: Equivalent to Zustand for our needs; Zustand wins on team familiarity (Vibe-Trading reference, per `docs/frontend.md` §1).

**Rationale:** Already prescribed by `docs/frontend.md` §1 — this change executes that decision rather than re-litigating it.

### D5 — UI design system: Dark mode default, shadcn/ui + Tailwind v4, zinc neutral, Taiwan-stock semantic colors

**Choice:** Dark mode is the default (light mode is a `/settings` toggle in a future change). Use shadcn/ui's `zinc` neutral scale. Add four semantic colors as **explicit Tailwind tokens** so charts and price cells stay readable when the theme changes:

| Token | Light hex | Dark hex | Use |
|---|---|---|---|
| `--up` | `#DC2626` (red-600) | `#EF4444` (red-500) | Price ↑, positive PnL — **紅漲** |
| `--down` | `#059669` (emerald-600) | `#10B981` (emerald-500) | Price ↓, negative PnL — **綠跌** |
| `--destructive` | `#991B1B` (red-800) | `#7F1D1D` (red-900) | Delete buttons, danger actions — distinct from `--up` |
| `--warning` | `#D97706` (amber-600) | `#F59E0B` (amber-500) | Risk-Off banners, breaker warnings |

**Typography (per ui-ux-pro-max query, adapted for zh-TW):**
- UI sans: **Inter** (Latin) + **Noto Sans TC** (zh-TW glyphs) — replaces Fira Sans which lacks CJK
- Numeric / code: **Fira Code** with `font-variant-numeric: tabular-nums` for aligned price columns
- Sizes: 14 px body, 12 px secondary, 16 px headings (admin = dense, not marketing)

**Layout pattern:**
- Persistent **left Sidebar** (240 px expanded, 56 px collapsed) — 18 nav items grouped per `docs/frontend.md` §2 (Workflow / Trading / Research / System)
- **TopBar** (48 px): breadcrumb + page title + relative-time clock (TPE) + logout button
- **Content** area: `max-w-7xl` container with `p-6` gutter, card-based grid
- **DisclaimerFooter**: sticky bottom banner per `docs/auth-and-mask.md` §3 — non-dismissible, shows "模擬交易僅供研究 / 非投資建議"

**Alternatives considered:**
- *Light mode default* (ui-ux-pro-max returned `#F8FAFC` background despite "Dark Mode" style): Rejected — Mark reviews trades late at night per CLAUDE.md context, and dark mode is what every Bloomberg / TradingView / 看盤軟體 user expects.
- *Top nav only (no sidebar)*: Doesn't scale to 18 pages.
- *Material UI / Mantine*: shadcn/ui is already prescribed (`docs/frontend.md` §1).

**Rationale:** Decisions match `docs/frontend.md` §1 prescriptions; semantic-color additions resolve a real ambiguity (red conflict between "up" and "destructive") that the doc didn't address.

### D6 — One real page (Dashboard), 17 stubs

**Choice:** `/` Dashboard renders:
- A `KpiRow` of 4 cards from `GET /api/admin/stats/today` (today P&L, open positions, pending confirms, today LLM cost)
- A `LiveFeed` panel subscribed to `/api/admin/events`, showing the last 20 events with type-icon + symbol + timestamp

Other 17 routes (`/chat`, `/swarm`, …) render a `<ComingSoon name="…" />` component that lists the change name expected to implement them (TBD-future). The sidebar is fully navigable so Mark can preview the IA.

**Rationale:** Dashboard is the smallest page that exercises both REST (TanStack Query) and SSE (Zustand live feed) — proving the end-to-end shell works. Stubs keep nav UX honest without blowing scope.

### D7 — Build/test/lint stack

- **Package manager:** `pnpm@9` (Node 20+) — fast, disk-efficient, plays well with monorepo if we ever add `packages/`
- **Test:** Vitest (unit + component via React Testing Library); Playwright deferred (no E2E in this slice)
- **Lint:** ESLint with `@typescript-eslint` + `eslint-plugin-react-hooks` + `eslint-plugin-jsx-a11y`
- **Format:** Prettier with the Tailwind plugin
- **Type-check:** `tsc --noEmit` in CI script; not blocking for this slice

## Risks / Trade-offs

- **[Risk]** SSE reconnect storm if backend restarts → **Mitigation**: exponential backoff in the SSE hook (1s → 2s → 4s → 8s, cap 30s); abort reconnect if 401 (token revoked).
- **[Risk]** `localStorage` token exfiltrated by browser extension or compromised dev-tools session → **Mitigation**: accepted risk per threat model (single-user, single-machine); token can be rotated by regenerating `OHMYSTOCK_ADMIN_TOKEN` and re-logging in. Document this in `web-admin/README.md`.
- **[Risk]** Dark-mode default produces poor contrast for some color-blind variants (deuteranopia: red ≈ green) — yet 紅漲綠跌 is exactly red vs green → **Mitigation**: pair color with `↑ / ↓` glyphs (Lucide `arrow-up` / `arrow-down`) in every price cell; never rely on color alone (a11y rule from ui-ux-pro-max checklist).
- **[Risk]** 18 stub pages mean the sidebar advertises capabilities the user can't actually use yet → **Mitigation**: each stub clearly displays "Coming soon"; no broken interactions, no confusing empty states.
- **[Trade-off]** No light mode in this slice means users with very bright environments must wait → accepted; theme toggle is a small future change.
- **[Trade-off]** `pnpm` adds a new toolchain alongside Python/uv; Mark must install Node 20+ → documented in README; one-time cost.

## Migration Plan

This is a greenfield additive change — no migration needed.

**Deploy steps:**
1. Land the `web-admin/` directory on `main`
2. Mark runs `cd web-admin && pnpm install && pnpm dev`
3. Backend on `localhost:8000` is reached via Vite dev proxy (`/api/*` → `http://localhost:8000`)
4. Mark logs in with the value of `OHMYSTOCK_ADMIN_TOKEN` from his local `.env`
5. Dashboard loads stats + live feed; success criterion = SSE event from a manual `POST /api/admin/screener.run` arrives in the live feed within 1s

**Rollback:** Delete `web-admin/`. No backend or DB state is touched.

## Open Questions

1. **Theme toggle** — defer light mode to a tiny follow-up change, or skip until someone asks? *Recommend: skip until asked.*
2. **i18n setup** — install `i18next` now (per `docs/frontend.md` §1) or hardcode zh-TW strings in this slice and wire i18n when the second locale matters? *Recommend: hardcode zh-TW; this is a single-user app; YAGNI.*
3. **CI** — add `pnpm build` + `pnpm test` job in this PR or after the second page change? *Recommend: defer; one shell + one Dashboard test suite isn't worth a workflow yet.*
4. **shadcn/ui component installation** — copy all 30+ components upfront via CLI, or only the ones Dashboard needs (Button, Card, Skeleton)? *Recommend: only what Dashboard needs; future page changes pull more on demand.*
