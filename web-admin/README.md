# ohMyStock - Web Admin

Phase 4 admin app. Bearer-authenticated React 19 + Vite + Tailwind v4 + shadcn (zinc).
Single-user, localhost-only by default.

## Prerequisites

- Node 20+ (.nvmrc pins 20)
- pnpm 9+ (corepack enable will provide it from the bundled Node)
- The Python backend running on http://localhost:8000 with a valid
  OHMYSTOCK_ADMIN_TOKEN (>= 32 chars) in its .env

## Scripts

```sh
corepack pnpm install          # one-time
corepack pnpm dev              # http://localhost:5173 (proxies /api -> :8000)
corepack pnpm build            # static bundle to dist/
corepack pnpm preview          # serve dist/ locally
corepack pnpm typecheck
corepack pnpm lint
corepack pnpm test
corepack pnpm format
```

## Login flow

1. Start backend.
2. corepack pnpm dev, open http://localhost:5173.
3. Browser redirects to /login.
4. Paste OHMYSTOCK_ADMIN_TOKEN (read from backend .env); click 登入.
5. Dashboard loads - KpiRow fetches /api/admin/stats/today, LiveFeed
   subscribes to /api/admin/events. New events appear within ~1s.

## Threat model

The token is stored in localStorage under ohmystock.admin.token.
This is acceptable because:
- Single user, single machine
- Bundle is never served to public (localhost / Cloudflare Tunnel only -
  see docs/auth-and-mask.md section 5)
- We render no user-supplied HTML in the shell, so XSS surface is minimal

To rotate: regenerate OHMYSTOCK_ADMIN_TOKEN in backend .env,
restart backend, click 登出 in the admin, paste new token.

## Remaining work

The 17 non-Dashboard routes are stubs (<ComingSoon />). Each gets its
own future change. Add shadcn components on demand:

```sh
corepack pnpm dlx shadcn@latest add button card input skeleton
```