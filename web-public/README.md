# web-public

Public-facing demo UI for ohMyStock. Subscribes to the masked SSE channel at
`/api/public/events` and renders incoming events as a feed. **No real symbol,
price, or P&L ever crosses this boundary** — see `docs/auth-and-mask.md` §3.

## Dev

```bash
# terminal 1: backend
uv run uvicorn ohmystock.api.app:create_app --factory --port 8000

# terminal 2: dev server (proxies /api → :8000)
cd web-public
npm install
npm run dev
# → http://localhost:5173
```

## Tests

```bash
npm test         # Vitest component tests (DisclaimerBanner, MaskedEventsFeed)
npm run build    # tsc + vite build (smoke)
```

## E2E (mask penetration)

Validates that 30 s of public SSE traffic contains no DENYLIST field, no raw
4-digit TWSE code, and no top-50 company name. **Not** in CI yet — run before
each public deploy.

```bash
# one-time, downloads ~200 MB browser binaries
npx playwright install chromium

# requires backend (port 8000) + dev server (port 5173) running
npm run e2e
```

The fixture `e2e/fixtures/twse_top50_names.json` is the public blacklist; add
names to it if you ever see a leak.

## Scope (v0 — change `web-public-shell-and-mask`)

- MaskedEventSerializer + SymbolMaskTable + `/api/public/events` SSE route
- DisclaimerBanner + MaskedEventsFeed + 404 + robots.txt
- Vitest unit tests + Playwright E2E scaffold
- Canvas 2D pixel office layout, Vercel/Cloudflare deploy, i18n, public-endpoint
  rate limiting are all deferred to follow-up changes.
