## Why

Phase 4.5 ("公網 web-public/ + Mask serializer + E2E 滲透測試") is the largest untouched
roadmap slice — `MaskedEventSerializer` / `SymbolMaskTable` / `/api/public/events` / the
`web-public/` app all live in design docs but have zero implementation. The system already
emits 9 of 16 EventBus event types to the admin SSE channel, so the mask + public channel
is the natural next layer. Shipping it first (before the pixel UI) lets us E2E-test the
SITC compliance guarantees (no `\b\d{4}\b`, no DENYLIST fields, no real company names) on
a tiny surface, then iterate the pixel rendering as a separate change without re-litigating
the mask contract.

## What Changes

- Add `MaskedEventSerializer` next to existing `AdminEventSerializer` in
  `src/ohmystock/eventbus/serializers.py` — applies `PUBLIC_WHITELIST` per `event_type`,
  drops `DENYLIST_FIELDS`, regex-strips 4-digit TWSE codes from `reasoning_summary`.
- Add `SymbolMaskTable` (in-memory, process-scoped, monotonic `STK-A..STK-Z..STK-AA..`
  labels; `industry_of(symbol) -> str`).
- Add `GET /api/public/events` SSE endpoint (no auth, public CORS, rate-limit per spec)
  that subscribes to the same `bus` and emits masked payloads.
- Add `web-public/` Vite + React 19 + TS + Tailwind v4 scaffold with: `index.html`,
  `App.tsx`, `MaskedEventsFeed.tsx` (plain `<ul>` of incoming events for now — **no Canvas,
  no sprites**), `DisclaimerBanner.tsx` (sticky, non-dismissable, zh-TW text per
  `docs/auth-and-mask.md` §4.3), `robots.txt` (Allow `/`, Disallow `/api/`), Vite dev proxy
  `/api` → `localhost:8000`.
- Add E2E test (Playwright) per `docs/auth-and-mask.md` §6.1 — 60 s SSE capture, assert
  no `\b\d{4}\b`, no DENYLIST field names, no top-50 TWSE company name.
- Add unit tests: every `PUBLIC_WHITELIST` key fed a fat payload → output contains zero
  `DENYLIST_FIELDS`; `SymbolMaskTable` labels stable in-session + reset across instances.

**Intentionally deferred to later changes:** Canvas 2D pixel office layout, 9 character
sprite sheets, BFS pathfinding, action queue, `AgentInfoSheet`, i18n (en locale),
`/api/public/recent_events` cold-load endpoint, Vercel/Cloudflare Pages production deploy
config, the remaining 7 unwired event emitters (those belong to their producing
capabilities, not Phase 4.5).

## Capabilities

### New Capabilities

- `eventbus-public-mask`: `MaskedEventSerializer` + `SymbolMaskTable` + `PUBLIC_WHITELIST`
  + `DENYLIST_FIELDS` + `TWSE_CODE_RE` reasoning strip. Pure-function serializer; no
  network, no DB, no auth. Sole authority on which payload fields cross the public
  boundary.
- `admin-public-events-endpoint`: `GET /api/public/events` SSE route. No auth, public
  CORS, subscribes to `bus`, serializes via `MaskedEventSerializer`. Sole authority on the
  public SSE contract (no PII headers, no admin token leak, EventSource-compatible
  framing).
- `web-public-shell`: Minimal `web-public/` Vite app — DisclaimerBanner + masked events
  feed (`<ul>` of last 50 events, oldest evicted on overflow) + robots.txt + 404 page. No
  Canvas. Sole authority on the public-app shell layout, disclaimer contract, and SSE
  consumer wiring.

### Modified Capabilities

(None — `eventbus-emitters` only ships `AdminEventSerializer`; the masked one is new
behaviour, not a requirement change to an existing capability.)

## Impact

- **New files** under `src/ohmystock/eventbus/` (`mask_table.py`, expand `serializers.py`)
  and `src/ohmystock/api/routes/public_events.py`; `web-public/` is a new top-level dir
  parallel to `web-admin/`.
- **`api/app.py`** wires the new public router and instantiates one process-scoped
  `SymbolMaskTable` (no env var needed; industry lookup loaded from existing
  `universe_daily` table at startup, fall back to `"其他"` on miss).
- **No DB schema change.** No new env vars (CORS origin can read existing
  `Settings()` if one already exists; otherwise hardcoded for dev).
- **CLAUDE.md §5 SSOT table** gets one new row after archive (covering all three
  capabilities together, per project convention).
- **No breaking change** to existing admin SSE / REST endpoints.
- **Bundle:** `web-public/` adds ~80 KB gzip (React + Tailwind + nothing else).
