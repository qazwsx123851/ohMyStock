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

## Components

Per-page wireframes and visual contracts for all 18 routes live in
`docs/web-admin-page-designs.md` (the SSOT). Component implementations
live here under `src/components/`.

### shadcn primitives (third-party source) — `src/components/ui/`

| File | Used by |
|---|---|
| `button.tsx`   | `DataTable` pager, future per-page actions |
| `card.tsx`     | `KpiCard`, empty / error panels |
| `skeleton.tsx` | `KpiCard` loading, `DataTable` loading rows |
| `table.tsx`    | `DataTable` body |
| `badge.tsx`    | `StatusBadge` |

These files are copied from `https://github.com/shadcn-ui/ui` and treated
as **immutable third-party source** — customisation goes through wrapper
components in `src/components/`, never edits to `ui/`. Each file's JSDoc
header records the upstream URL + copy date.

### Composites — `src/components/`

| File | Purpose |
|---|---|
| `status-badge.tsx` | 7-status badge (`pending` / `approved` / `rejected` / `executed` / `expired` / `canceled` / `errored`); each pairs a colour token with a Lucide icon (color is never the only signal). |
| `kpi-card.tsx`     | Single KPI tile with `direction='up' \| 'down' \| 'neutral'` driving `--up` / `--down` colour + `<ArrowUp/>` / `<ArrowDown/>`. Exports a `directionOf(n)` helper. |
| `data-table.tsx`   | Generic `<DataTable<T>>` — pagination, sortable headers (asc → desc → unsorted, with `aria-sort`), keyboard activation (`Tab` + `Enter`), `density='compact' \| 'comfortable'`, loading skeleton, empty / error panels. |

### Adding the next primitive

1. Find the upstream file at
   `https://github.com/shadcn-ui/ui/blob/main/apps/www/registry/new-york-v4/ui/<name>.tsx`,
   copy its content verbatim into `src/components/ui/<name>.tsx`.
2. Add a JSDoc header with the upstream URL + today's date, and replace
   any `cn` import with `import { cn } from '@/lib/utils'`. Do **not**
   run `pnpm dlx shadcn add` (per
   `openspec/changes/web-admin-design-system-and-page-wireframes/design.md`
   D1 — we avoid lock-file churn and Radix-dep auto-injection).
3. If the primitive needs a Radix runtime peer (e.g.
   `@radix-ui/react-dialog`), add the dep manually with
   `corepack pnpm add @radix-ui/react-<name>`.

### Deferred composites

These are intentionally **not** built yet — they will land in the
per-page change that first needs them:

- `FilterBar` — generic filter chip / date-range / multi-select bar
- `ConfirmDialog` — twice-confirm dialog wrapping shadcn `Dialog`
- `useSseStream(path)` — generalisation of `useAdminEvents` for future
  per-stream endpoints (today's single `/api/admin/events` works fine)

## Remaining work

The 17 non-Dashboard routes are stubs (`<ComingSoon />`). Each gets its
own future change; the contract per page lives in
`docs/web-admin-page-designs.md` and the composites above are designed
to cover ~70% of those pages without further abstraction.