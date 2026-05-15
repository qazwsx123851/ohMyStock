## Context

The admin SSE channel (`GET /api/admin/events`) is already wired in
`src/ohmystock/api/app.py:143–145`, fed by `EventBus` (`src/ohmystock/eventbus/bus.py`)
and serialized by `AdminEventSerializer` (`src/ohmystock/eventbus/serializers.py`). 9 of
16 event types are currently emitted by shipped capabilities (screener / decider /
confirm-gate / journal / auto-execute), and the admin web app consumes them today.

What does NOT exist yet:

- Any public-facing serializer; `serializers.py:6–10` explicitly notes the masked one is
  "a separate Phase 4.5 capability and not implemented here."
- Any `SymbolMaskTable` or industry lookup (no source file).
- Any `/api/public/*` route (only `/healthz` and `/api/admin/*` are registered).
- Any `web-public/` directory (only `web-admin/` exists at repo root).

Compliance / SITC context: `docs/auth-and-mask.md` §3.1 and §4.1–§4.2 spell out the
mask contract; this change is the first capability to put that contract into code, so
the test suite is the legal-defensibility surface. The single largest leak vector is
`reasoning` text containing `2330`-style 4-digit TWSE codes — caught by both whitelist
(`reasoning` → drop) and regex strip (`\b\d{4}\b` → `STK-?` in `reasoning_summary`).

Stakeholders: solo dev (Mark); zero external users. Goal is a defensible E2E test
+ deployable plumbing, not production traffic yet.

## Goals / Non-Goals

**Goals:**

- One source of truth for which fields cross the public boundary (`PUBLIC_WHITELIST`)
  and which never can (`DENYLIST_FIELDS`), enforced by the serializer + asserted by
  parametric tests covering every whitelisted `event_type`.
- A functioning `/api/public/events` SSE stream that the new `web-public/` app can
  consume in dev (`localhost:5173` → Vite proxy → `localhost:8000`).
- A minimal but real `web-public/` shell — proves the plumbing end-to-end and lets the
  Playwright E2E mask penetration test (`docs/auth-and-mask.md` §6.1) actually run.
- Same EventBus, same `bus.subscribe()` mechanism, same SSE framing as admin —
  no parallel infrastructure.

**Non-Goals:**

- Canvas 2D pixel rendering, 9-character sprite system, BFS pathfinding, action queue —
  these are a separate `web-public-pixel-office-mvp` change.
- Vercel / Cloudflare Pages production deploy (still localhost-only this change).
- The remaining 7 unwired event emitters (`pattern_detected`, `journal_queried`,
  `review_node_started`, `review_completed`, `proposal_created`, `wfa_started/
  passed/failed`) — those are on their producing capabilities, not Phase 4.5.
- i18n (en locale), `/api/public/recent_events` cold-load endpoint,
  `AgentInfoSheet`, `industry_hint` curated mapping beyond what `universe_daily`
  provides (fall back to `"其他"` is intentional v0 behaviour).
- Bearer-token-style auth for public routes — by definition no auth.

## Decisions

### D1 — Both serializers live in `serializers.py`, not separate files

The existing `AdminEventSerializer` is 12 LOC; the masked one is ~50 LOC; project
convention so far has been "one file per concept" not "one file per class". Splitting
into `serializers/admin.py` + `serializers/public.py` would require turning
`serializers.py` into a package (`serializers/__init__.py`) and updating the existing
import in `api/app.py:52` (`from ohmystock.eventbus import AdminEventSerializer`).

Decided: **keep one `serializers.py`**, add `MaskedEventSerializer` alongside
`AdminEventSerializer`. Export both from `ohmystock.eventbus.__init__`. The
docs/backend-eventbus.md §2.1 layout (`serializers/admin.py` + `serializers/public.py`)
is design-time guidance, not a hard contract — implementation freedom on file layout
is fine as long as the public API names match.

**Alternative considered:** split into a package. Rejected: extra churn in `app.py` +
`eventbus/__init__.py`; no benefit at current file size.

### D2 — `SymbolMaskTable` is a separate module (`mask_table.py`)

Unlike the serializer, `SymbolMaskTable` has runtime state (the `_map` dict + counter)
and needs an industry-lookup dependency injected at construction. Keeping it in its own
file makes it trivial to mock in serializer tests (pass a stub `mask_table`) without
importing the serializer module.

**Alternative considered:** nest as inner class of serializer. Rejected: harder to test
in isolation; the docs/backend-eventbus.md §4.3 spec also treats it as a peer.

### D3 — `SymbolMaskTable` industry lookup loads lazily from `universe_daily`, not eagerly at startup

`docs/backend-eventbus.md` §4.3 takes `industry_lookup: dict[str, str]` as a constructor
arg. Two options:

- (a) **Eager**: in `_lifespan`, `SELECT symbol, industry FROM universe_daily` once, pass
  the dict into the constructor.
- (b) **Lazy**: the table holds a `conn_factory` callable and runs `SELECT industry FROM
  universe_daily WHERE symbol = ? LIMIT 1` on first miss, caches in `_industry`.

Decided: **(a) eager**, but **fall through to `"其他"` on any miss**. Reasons:
- `universe_daily` is small (≤2000 rows); one SELECT at startup is cheap.
- Avoids a SQLite cursor on the hot SSE path.
- Idempotent across `_lifespan` restarts.
- Matches the `set_universe_closes_loader(build_universe_closes_loader(...))` pattern
  already in `_lifespan` (`api/app.py:76–78`).

Schema reality check: `universe_daily` may not have an `industry` column today. If it
doesn't, the eager load returns an empty dict and every symbol resolves to `"其他"` —
acceptable v0 behaviour because the mask test cares about correctness (industry hint
is whitelist-OK), not richness. A follow-up change can add the column + seeder.

### D4 — Public SSE route lives in `api/routes/public_events.py`, not inlined in `app.py`

Admin SSE is inlined in `app.py` (lines 95–112, 143–145) because it predates the
`api/routes/` convention. New routes have all gone into `api/routes/*.py` (see
`screener.py`, `swarm.py`, etc.). Keep that convention — add `public_events.py` with a
router, mount it in `app.py` alongside the others.

The handler is structurally identical to `_admin_event_stream` except:
- No `Depends(require_admin)`.
- Serializer is `MaskedEventSerializer` (module-level instance, constructed in
  `_lifespan` with the loaded industry dict).
- Same 15 s `: keepalive` strategy.

### D5 — `SymbolMaskTable` instance is module-level singleton, set during `_lifespan`

Need a process-scoped instance shared between the SSE handler and any future caller.
Constructed in `_lifespan` (after the industry-dict load), assigned to a module global
in `routes/public_events.py`. On shutdown, set to `None` to make late references fail
loudly (consistent with `reset_providers()` already in `_lifespan` `finally`).

**Alternative considered:** FastAPI dependency injection. Rejected: SSE generators
outlive request scope; DI doesn't fit.

### D6 — DENYLIST is enforced AFTER whitelist, as belt-and-suspenders

The whitelist alone should suffice (only listed keys are copied), but a future devhand
might accidentally add `"symbol"` to a whitelist. The post-pass `for f in DENYLIST_FIELDS:
out.pop(f, None)` is cheap (set membership), provably correct, and makes the test
`assert "symbol" not in out` a property of the implementation, not an accident.

### D7 — `web-public/` is a sibling of `web-admin/`, NOT a monorepo workspace yet

`docs/frontend-public-pixel.md` §10 references `packages/ui-tokens` and a monorepo
layout. We do **not** have a `packages/` directory today, and `web-admin/` is a
standalone Vite project (its own `package.json`, no workspace). Introducing pnpm
workspaces here would be ratholing.

Decided: `web-public/` is its own Vite project, standalone `package.json`, copies the
2–3 design tokens it needs from `web-admin/src/styles/` for now. When a third app or
shared component lands, do the monorepo refactor as its own change.

### D8 — DisclaimerBanner is a React component, NOT a server-rendered HTML banner

Same React/Vite stack as `web-admin`. The text is the zh-TW string from
`docs/auth-and-mask.md` §4.3 (the en version is deferred to i18n). The component is
mounted at app root (`App.tsx`) above the Outlet, always visible, no dismiss button.
Property-based test: rendering `App` always finds the banner text.

### D9 — Public events feed is the world's most boring `<ul>` in v0

The visible UI is one `<ul>` of the last 50 events (most recent first), each `<li>`
showing `[timestamp] event_type — JSON.stringify(payload)`. **No** Canvas, **no**
sprites, **no** characters — those land in the next change. This v0 is enough to
verify the mask end-to-end and gives us a real surface for Playwright to scrape.

### D10 — CORS is wide-open on public routes for dev; tightened in the deploy change

`/api/public/events` needs CORS for `localhost:5173` (Vite dev). The production
domain isn't decided yet (Vercel vs Cloudflare Pages — `docs/auth-and-mask.md` §5
leaves it open). For this change, allow `localhost:5173` + `localhost:5174` (admin dev,
in case someone tests cross-app). The production CORS allowlist will be added with the
deploy change. Use FastAPI's `CORSMiddleware`, scope it to `/api/public/*` only via
path-aware middleware (mount only that prefix), so admin CORS behaviour is unchanged.

### D11 — Rate limit is deferred to a follow-up

`docs/backend-eventbus.md` §5.4 mentions "10 連線 / IP / 分鐘" for the public endpoint.
v0 has zero public traffic (localhost-only). Adding a rate limiter (slowapi, or
custom) for a localhost-only change is yak-shaving. Note it explicitly as deferred;
revisit when the deploy change lands.

## Risks / Trade-offs

- **[Risk] `universe_daily` has no `industry` column** → `industry_hint` is always
  `"其他"`. **Mitigation:** acceptable v0 (the whitelist + DENYLIST mask test doesn't
  depend on richness); flag in spec; follow-up change adds the column + seed from
  TWSE listed-industries CSV.
- **[Risk] `MaskedEventSerializer` reasoning regex `\b\d{4}\b` may strip non-stock
  4-digit numbers (e.g. year `2026` or `1000` shares)** → produces noise in
  `reasoning_summary`. **Mitigation:** acceptable noise — the legal compliance side
  is "no real symbol leaks", false positives just degrade readability not safety. Add
  an explicit test that confirms `2026` gets replaced too (so we document the
  behaviour rather than promise it doesn't happen).
- **[Risk] `SymbolMaskTable` `_counter` is monotonic across the process lifetime;
  long-lived dev sessions could push past `STK-Z` (26 symbols) into `STK-AA..`** →
  visually ugly but correct. **Mitigation:** `_next_label()` handles overflow already
  (base-26 walk); test it.
- **[Risk] Slow consumer on `/api/public/events` blocks producer** → existing `bus.emit`
  already drops on `QueueFull` (`bus.py:34–38`), so producer is unblocked; only that
  subscriber misses events. **Mitigation:** already handled at bus layer.
- **[Trade-off] Both serializers share one module** → if the file grows past ~200 LOC,
  revisit D1 and split. Not now.
- **[Trade-off] No production deploy in this change** → can't yet hit the SITC
  compliance surface from the public internet; E2E test runs against `localhost:8000`.
  Acceptable for a closed dev loop; the deploy change is a separate, smaller
  capability.

## Migration Plan

No migration — this is greenfield. Rollback: delete `web-public/`, revert
`api/app.py` router include, drop `routes/public_events.py` + `eventbus/mask_table.py`,
revert `serializers.py`. No DB rows written, no env vars, no schema changes.

## Open Questions

- Does `universe_daily` have an `industry` column today? (Cheap to check; if no, accept
  `"其他"` for all symbols in v0 and add the column in a follow-up.)
- Should `MaskedEventsFeed` deduplicate by `event_id` if the SSE auto-reconnect replays
  events? (Yes; trivial `Set` in `useState`. Decide in tasks.)
- Playwright config: reuse `web-admin/`'s if present, or scaffold `web-public/e2e/`
  fresh? (Confirm during task implementation.)
