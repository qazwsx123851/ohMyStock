## Why

Phase 4 backend is fully shipped — Bearer auth gate, read endpoints, write actions, and SSE eventbus are all live and tested. **But there is still no UI.** Without a shell, every backend feature can only be hit via `curl`, the 18-page admin from `docs/frontend.md` is blocked, and Phase 4.5 (public pixel demo) cannot start because it depends on a stable admin app to compare against.

This change ships the smallest viable React shell that proves end-to-end: token login → auth-protected routes → live SSE feed → real REST calls. It deliberately stubs all 18 pages with placeholders so later changes can fill them in one at a time without re-doing routing or auth.

## What Changes

- **NEW** `web-admin/` Vite + React 19 + TypeScript + Tailwind v4 + shadcn/ui scaffold (per `docs/frontend.md` §1)
- **NEW** Login screen — token entry, persisted in `localStorage`, with explicit logout
- **NEW** Bearer auth wiring — every `/api/admin/*` fetch carries `Authorization: Bearer <token>`; 401 responses redirect to login and clear the stored token
- **NEW** SSE client for `/api/admin/events` with `Authorization` header support and reconnect-on-close
- **NEW** App layout — `<Sidebar>` (18 nav items, only `/` Dashboard is non-stub at this stage), `<TopBar>` (project name + logout), `<DisclaimerFooter>` (per `docs/auth-and-mask.md` §3)
- **NEW** Stub pages for all 18 routes — each renders a "Coming soon" placeholder so the sidebar is fully navigable
- **NEW** Dashboard page — minimal real content: calls `GET /api/admin/stats/today` + subscribes to SSE feed and shows the last 20 events, to prove the wiring
- **NEW** Vite dev proxy → `http://localhost:8000` so `/api/*` works in dev without CORS
- **NEW** Zustand auth store + TanStack Query setup + React Router v7 nested routing
- **NEW** `web-admin/.env.example` documenting `VITE_API_BASE_URL` (defaults to `''` so the dev proxy handles it)
- **NEW** `web-admin/README.md` with `pnpm install` / `pnpm dev` / `pnpm build` / `pnpm test` instructions

**Out of scope** (deferred to later changes):
- Real implementations for the 17 non-Dashboard pages (Chat, Swarm, Backtest, Paper, Market, Skills, Memory, Sessions, Settings, Audit, etc.)
- Charts (KLineCharts / Recharts / Tremor / React Flow / ApexCharts)
- Forms beyond the token-entry login form
- `packages/` shared monorepo packages (`ui-tokens`, `api-types`, `event-types`, `api-client-public`) — added when first needed
- Public pixel app (`web-public/`) — its own Phase 4.5 change
- Backend changes — none required; all endpoints already exist

## Capabilities

### New Capabilities
- `web-admin-shell`: the React 19 admin app scaffold — auth lifecycle (login/logout/auto-401), protected routing primitives for the 18 pages, SSE subscriber wired to `/api/admin/events`, and the layout chrome (Sidebar / TopBar / DisclaimerFooter)

### Modified Capabilities
None. This change adds frontend code only. Backend specs (`web-admin-bearer-auth`, `admin-read-endpoints`, `server-action-endpoints`, `eventbus-emitters`) remain unchanged.

## Impact

- **New code:** `web-admin/` directory (Vite + React app, ~30-40 files)
- **No backend changes:** zero edits to `src/ohmystock/`
- **New dev dependency:** `pnpm` (Node 20+) — documented in `web-admin/README.md`
- **CI:** no change in this slice; a follow-up may add a `pnpm build` job once the shell is stable
- **CLAUDE.md §5 SSOT table:** add a row pointing to the new `web-admin-shell` spec and `web-admin/src/` as the implementation
- **Roadmap:** advances Phase 4 from "backend done, UI not started" to "UI shell live, page implementations queued"
